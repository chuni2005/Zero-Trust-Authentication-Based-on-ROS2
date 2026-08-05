import psutil
import os
import csv
import time

def get_system_metrics():
    # --- 0. 獲取目前時間戳記 (毫秒) ---
    current_ms = int(time.time() * 1000)

    # --- 1. 從 /proc/vmstat 獲取核心分頁與檔案快取指標 ---
    vmstat = {}
    with open('/proc/vmstat', 'r') as f:
        for line in f:
            name, val = line.split()
            vmstat[name] = int(val)

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

    # --- 2. 記憶體相關指標 (psutil.virtual_memory) ---
    mem = psutil.virtual_memory()
    MemFree = mem.free
    Active = mem.active
    Inactive = mem.inactive
    Buffers = mem.buffers
    Cached = mem.cached
    
    swap = psutil.swap_memory()
    SwapFree = swap.free

    # --- 3. 網路 I/O 與 TCP 連線狀態 ---
    net_io = psutil.net_io_counters()
    Net_Sent = net_io.bytes_sent
    Net_Received = net_io.bytes_recv

    # 統計 TCP 各種狀態的連線數
    conns = psutil.net_connections(kind='tcp')
    Tcp_Established = len([c for c in conns if c.status == 'ESTABLISHED'])
    Tcp_Listen = len([c for c in conns if c.status == 'LISTEN'])
    Tcp_TimeWait = len([c for c in conns if c.status == 'TIME_WAIT'])
    Tcp_Close = len([c for c in conns if c.status == 'CLOSE'])
    Tcp_Syn = len([c for c in conns if c.status in ('SYN_SENT', 'SYN_RECV')])

    # --- 4. 磁碟 I/O ---
    disk_io = psutil.disk_io_counters()
    Disk_Read = disk_io.read_bytes
    Disk_Write = disk_io.write_bytes

    return {
        'ms': current_ms,
        'Net_Sent': Net_Sent, 'pgpgin': pgpgin, 'pgactivate': pgactivate, 
        'Disk_Read': Disk_Read, 'pgfault': pgfault, 'Net_Received': Net_Received, 
        'MemFree': MemFree, 'Inactive': Inactive, 'pgdeactivate': pgdeactivate, 
        'Tcp_Close': Tcp_Close, 'pgfree': pgfree, 'nr_active_file': nr_active_file, 
        'Cached': Cached, 'nr_inactive_file': nr_inactive_file, 'Disk_Write': Disk_Write, 
        'pgpgout': pgpgout, 'Tcp_Syn': Tcp_Syn, 'Buffers': Buffers, 
        'Tcp_TimeWait': Tcp_TimeWait, 'Tcp_Listen': Tcp_Listen, 
        'Tcp_Established': Tcp_Established, 'Active': Active, 
        'pgalloc_dma': pgalloc_dma, 'pgmajfault': pgmajfault, 'SwapFree': SwapFree
    }

def Write_csv(writer, data):
    writer.writerow(data)
    print("Data row is written: ", data.get('ms'))  # 印出目前寫入的時間戳記

#main
file_name = 'OS_monitor.csv'
field_names = [
    'ms',  # 毫秒級時間戳記
    'MemFree', 'Buffers', 'Cached', 'Active', 'Inactive', 'SwapFree', # 記憶體狀態
    'pgpgin', 'pgpgout', 'pgalloc_dma', 'pgfree', # 核心分頁機制
    'pgactivate', 'pgdeactivate', 'pgfault', 'pgmajfault',
    'Disk_Read', 'Disk_Write', # 磁碟 I/O
    'Net_Sent', 'Net_Received', 'Tcp_Listen', # 網路與連線狀態
    'Tcp_Established', 'Tcp_Syn', 'Tcp_TimeWait', 'Tcp_Close',
    'nr_active_file', 'nr_inactive_file' # 檔案快取
]

if os.path.exists(file_name):
    os.remove(file_name)

with open(file_name, mode='a', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=field_names)
    writer.writeheader()

    while True:
        data = get_system_metrics()
        Write_csv(writer, data)
        time.sleep(0.2)