import time
import requests
import config

PROCESS_IP = config.Process_IP
PROCESS_PORT = config.PROCESS_PORT
URL = f"http://{PROCESS_IP}:{PROCESS_PORT}/process"

def get_fast_metrics():
    current_ms = int(time.time() * 1000)

    # 1. 一次性讀取 /proc/vmstat
    vmstat = {}
    try:
        with open('/proc/vmstat', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2:
                    vmstat[parts[0]] = int(parts[1])
    except FileNotFoundError:
        pass

    # 2. 一次性讀取 /proc/meminfo
    meminfo = {}
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(':')] = int(parts[1]) * 1024 # 轉成 bytes
    except FileNotFoundError:
        pass

    # 若抓不到則填 -1 (使用 .get(key, -1) 處理，若有欄位但計算出來是 None 也填 -1)
    mem_free = meminfo.get('MemFree', -1)
    buffers = meminfo.get('Buffers', -1)

    # Linux 真正的 Cache 算量包含 SReclaimable
    if 'Cached' in meminfo or 'SReclaimable' in meminfo:
        cached = meminfo.get('Cached', 0) + meminfo.get('SReclaimable', 0)
    else:
        cached = -1

    active = meminfo.get('Active', -1)
    inactive = meminfo.get('Inactive', -1)
    swap_free = meminfo.get('SwapFree', -1)

    # 3. 讀取 /proc/net/dev 獲取網路 I/O
    net_sent, net_recv = -1, -1
    try:
        with open('/proc/net/dev', 'r') as f:
            lines = f.readlines()
            if len(lines) > 2:
                net_sent, net_recv = 0, 0 # 檔案存在且有資料，初始化為 0 開始累加
                for line in lines[2:]:
                    parts = line.split()
                    if len(parts) >= 10:
                        net_recv += int(parts[1])
                        net_sent += int(parts[9])
    except FileNotFoundError:
        pass

    # 4. 讀取 /proc/net/sockstat 獲取 TCP 狀態統計
    tcp_established = -1
    tcp_tw = -1
    tcp_listen = -1
    try:
        with open('/proc/net/sockstat', 'r') as f:
            for line in f:
                if line.startswith('TCP:'):
                    parts = line.split()
                    kv = {parts[i]: int(parts[i+1]) for i in range(1, len(parts), 2)}
                    tcp_established = kv.get('inuse', -1)
                    tcp_tw = kv.get('TW', -1)

                    if 'alloc' in kv and 'inuse' in kv:
                        tcp_listen = kv['alloc'] - kv['inuse']
                    break
    except FileNotFoundError:
        pass

    # 5. 讀取 /proc/diskstats 獲取磁碟 I/O
    disk_read, disk_write = -1, -1
    try:
        with open('/proc/diskstats', 'r') as f:
            has_disk_data = False
            for line in f:
                parts = line.split()
                if len(parts) >= 14:
                    dev_name = parts[2]
                    if dev_name.startswith(('sd', 'nvme', 'vd')):
                        if not has_disk_data:
                            disk_read, disk_write = 0, 0 # 發現實體磁碟，初始化為 0
                            has_disk_data = True
                        disk_read += int(parts[5]) * 512
                        disk_write += int(parts[9]) * 512
    except FileNotFoundError:
        pass

    return {
        'ms': current_ms,
        'MemFree': mem_free,
        'Buffers': buffers,
        'Cached': cached,
        'Active': active,
        'Inactive': inactive,
        'SwapFree': swap_free,
        'pgpgin': vmstat.get('pgpgin', -1),
        'pgpgout': vmstat.get('pgpgout', -1),
        'pgalloc_dma': vmstat.get('pgalloc_dma', -1),
        'pgfree': vmstat.get('pgfree', -1),
        'pgactivate': vmstat.get('pgactivate', -1),
        'pgdeactivate': vmstat.get('pgdeactivate', -1),
        'pgfault': vmstat.get('pgfault', -1),
        'pgmajfault': vmstat.get('pgmajfault', -1),
        'Disk_Read': disk_read,
        'Disk_Write': disk_write,
        'Net_Sent': net_sent,
        'Net_Received': net_recv,
        'Tcp_Listen': tcp_listen,
        'Tcp_Established': tcp_established,
        'Tcp_Syn': -1,       # sockstat 未直接提供，固定填 -1
        'Tcp_TimeWait': tcp_tw,
        'Tcp_Close': -1,     # sockstat 未直接提供，固定填 -1
        'nr_active_file': vmstat.get('nr_active_file', -1),
        'nr_inactive_file': vmstat.get('nr_inactive_file', -1)
    }


def send_metrics(session, metrics, timeout=2.0, max_retries=2):
    """
    將單筆指標以 JSON 透過 HTTP POST 傳送到遠端伺服器。
    失敗時會重試 max_retries 次，全部失敗則回傳 False（呼叫端可自行決定要不要記 log / 丟棄）。
    """
    payload = {"data_source": "fast_monitor", "metrics": metrics}
    for attempt in range(max_retries + 1):
        try:
            resp = session.post(URL, json=payload, timeout=timeout)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            if attempt < max_retries:
                time.sleep(0.05)  # 短暫等待後重試，避免瞬斷造成整批遺失
            else:
                print(f"[警告] 傳送失敗 (ms={metrics.get('ms')})：{e}")
                return False


# --- Main 區塊 ---
print("開始高速監控系統指標，並即時遠端傳輸... 按 Ctrl+C 可以安全停止。")
session = requests.Session()

try:
    while True:
        t0 = time.time()

        data = get_fast_metrics()
        ok = send_metrics(session, data)

        status = "已傳送" if ok else "傳送失敗"
        print(f"Data row {status}: {data.get('ms')}")

        # 動態精準扣除執行時間，穩定維持 0.2 秒採樣
        delay = 0.2 - (time.time() - t0)
        if delay > 0:
            time.sleep(delay)
        else:
            time.sleep(0.01) # 若極端狀況下超時，給予 10ms 緩衝避免卡死 CPU

except KeyboardInterrupt:
    print("\n監控已由使用者手動停止。")
finally:
    session.close()