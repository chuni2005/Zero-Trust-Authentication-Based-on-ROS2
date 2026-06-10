import time
import requests
import config

PROCESS_IP = config.Process_IP
PROCESS_PORT = config.PROCESS_PORT
URL = f"http://{PROCESS_IP}:{PROCESS_PORT}/process"

# 🚀 精準從 62 特徵清單中抽出的 25 個 OS 特徵
OS_FEATURES = [
    'nr_active_file', 'pgfree', 'Tcp_Established', 'Net_Received', 'Tcp_Syn',
    'pgpgin', 'pgpgout', 'pgfault', 'Tcp_Close', 'Buffers', 'pgalloc_dma',
    'Net_Sent', 'Inactive', 'Cached', 'Active', 'SwapFree', 'pgactivate',
    'Disk_Read', 'Tcp_TimeWait', 'Disk_Write', 'MemFree', 'Tcp_Listen',
    'nr_inactive_file', 'pgmajfault', 'pgdeactivate'
]

def get_os_metrics():
    metrics = {feat: -1 for feat in OS_FEATURES}  # 預填 -1 確保維度與防禦

    pgpgin = vmstat.get('pgpgin')
    pgpgout = vmstat.get('pgpgout')
    pgactivate = vmstat.get('pgactivate')
    pgdeactivate = vmstat.get('pgdeactivate')
    pgfault = vmstat.get('pgfault')
    pgmajfault = vmstat.get('pgmajfault')
    pgfree = vmstat.get('pgfree')
    pgalloc_dma = vmstat.get('pgalloc_dma', 0) # 部分核心版本可能在不同位置
    nr_active_file = vmstat.get('nr_active_file')
    nr_inactive_file = vmstat.get('nr_inactive_file')

    metrics['MemFree'] = mem.free
    metrics['Active'] = mem.active
    metrics['Inactive'] = mem.inactive
    metrics['Buffers'] = mem.buffers
    metrics['Cached'] = mem.cached
    metrics['SwapFree'] = swap.free
    
    metrics['Net_Sent'] = net_io.bytes_sent
    metrics['Net_Received'] = net_io.bytes_recv

    conns = psutil.net_connections(kind='tcp')
    metrics['Tcp_Established'] = len([c for c in conns if c.status == 'ESTABLISHED'])
    metrics['Tcp_Listen'] = len([c for c in conns if c.status == 'LISTEN'])
    metrics['Tcp_TimeWait'] = len([c for c in conns if c.status == 'TIME_WAIT'])
    metrics['Tcp_Close'] = len([c for c in conns if c.status == 'CLOSE'])
    metrics['Tcp_Syn'] = len([c for c in conns if c.status in ('SYN_SENT', 'SYN_RECV')])

    metrics['Disk_Read'] = disk_io.read_bytes
    metrics['Disk_Write'] = disk_io.write_bytes
   
    return metrics

if __name__ == "__main__":
    print(f"[Monitor-OS] 啟動。負責監控特徵數: {len(OS_FEATURES)}")
    session = requests.Session()
    while True:
        try:
            payload = {"data_source": "os_monitor", "metrics": get_os_metrics()}
            session.post(URL, json=payload, timeout=0.1)
        except Exception: pass
        time.sleep(0.1)