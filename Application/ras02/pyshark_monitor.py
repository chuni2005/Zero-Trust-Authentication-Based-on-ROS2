import pyshark
import time
import threading
import requests
import config

PROCESS_IP = config.Process_IP
PROCESS_PORT = config.PROCESS_PORT
URL = f"http://{PROCESS_IP}:{PROCESS_PORT}/process"

# 🚀 從 62 特徵清單中精準過濾出的 30 個 PyShark 網路特徵
NET_FEATURES = [
    'layers.icmp.udp.udp.stream', 'layers.dns.dns.flags_tree.dns.flags.recdesired',
    'layers.ip.ip.stream', 'layers.icmp.udp.udp.checksum', 'layers.ip.ip.proto',
    'layers.rtps.rtps.version_tree.rtps.version.minor', 'layers.dns.dns.count.queries',
    'layers.dns.dns.count.answers', 'layers.icmp.udp.udp.payload',
    'layers.ip.ip.ttl_tree._ws.expert._ws.expert.severity',
    'layers.dns.dns.flags_tree.dns.flags.truncated', 'layers.dns.dns.flags_tree.dns.flags.checkdisable',
    'layers.dns.dns.flags', 'layers.icmp.icmp.checksum', 'layers.ip.ip.ttl',
    'layers.ip.ip.ttl_tree._ws.expert._ws.expert.message', 'layers.dns.dns.flags_tree.dns.flags.rcode',
    'layers.dns.dns.flags_tree.dns.flags.z', 'layers.udp.udp.stream', 'layers.udp.udp.checksum',
    'layers.dns.dns.count.add_rr', 'layers.dns.dns.flags_tree.dns.flags.ad', 'layers.udp.udp.payload',
    'layers.dns.dns.flags_tree.dns.flags.response', 'layers.dns.dns.response_to',
    'layers.dns.dns.flags_tree.dns.flags.authoritative', 'layers.icmp.ip.ip.checksum', 'layers.rtps.rtps.vendorId'
]

packet_buffer = []
buffer_lock = threading.Lock()
http_session = requests.Session()

def parse_packet_to_dict(pkt):
    """將 pyshark 封包物件嚴格解構並打平成模型對齊的字典（純數字不轉 int）"""
    pkt_dict = {feat: -1 for feat in NET_FEATURES}
    try:
        # ---- 1. IP 層 ----
        if 'IP' in pkt:
            # 🟢 不用轉 int：直接讓自身數值（字串形式）進去，前處理器會用 is_numeric 抓 float
            pkt_dict['layers.ip.ip.proto'] = pkt.ip.proto if hasattr(pkt.ip, 'proto') else -1
            pkt_dict['layers.ip.ip.ttl'] = pkt.ip.ttl if hasattr(pkt.ip, 'ttl') else -1
            if hasattr(pkt.ip, 'stream'): 
                pkt_dict['layers.ip.ip.stream'] = pkt.ip.stream

        # ---- 2. UDP 層 ----
        if 'UDP' in pkt:
            if hasattr(pkt.udp, 'stream'): 
                pkt_dict['layers.udp.udp.stream'] = pkt.udp.stream
            if hasattr(pkt.udp, 'payload'): 
                pkt_dict['layers.udp.udp.payload'] = pkt.udp.payload
            if hasattr(pkt.udp, 'stream_pnum'):
                pkt_dict['layers.udp.udp.stream.pnum'] = pkt.udp.stream_pnum
            elif hasattr(pkt.udp, 'stream_pcap_num'):
                pkt_dict['layers.udp.udp.stream.pnum'] = pkt.udp.stream_pcap_num

            # ⚠️ 必須轉 16 進位：因為這是 Checksum 雜湊，不轉會帶有 0x 導致前處理端認錯
            if hasattr(pkt.udp, 'checksum'): 
                pkt_dict['layers.udp.udp.checksum'] = int(pkt.udp.checksum, 16)

        # ---- 3. DNS 層 ----
        if 'DNS' in pkt:
            # 🟢 不用轉 int 的純十進位計數
            if hasattr(pkt.dns, 'count_queries'): 
                pkt_dict['layers.dns.dns.count.queries'] = pkt.dns.count_queries
            if hasattr(pkt.dns, 'count_answers'): 
                pkt_dict['layers.dns.dns.count.answers'] = pkt.dns.count_answers
            if hasattr(pkt.dns, 'count_add_rr'): 
                pkt_dict['layers.dns.dns.count.add_rr'] = pkt.dns.count_add_rr
            if hasattr(pkt.dns, 'response_to'):
                pkt_dict['layers.dns.dns.response_to'] = pkt.dns.response_to

            # ⚠️ 必須轉 16 進位：這些是 Flags 旗標代碼（如 0x0100）
            if hasattr(pkt.dns, 'flags'): 
                pkt_dict['layers.dns.dns.flags'] = int(pkt.dns.flags, 16)
            if hasattr(pkt.dns, 'flags_response'):
                pkt_dict['layers.dns.dns.flags_tree.dns.flags.response'] = int(pkt.dns.flags_response, 16)
            if hasattr(pkt.dns, 'flags_recdesired'):
                pkt_dict['layers.dns.dns.flags_tree.dns.flags.recdesired'] = int(pkt.dns.flags_recdesired, 16)
            if hasattr(pkt.dns, 'flags_truncated'):
                pkt_dict['layers.dns.dns.flags_tree.dns.flags.truncated'] = int(pkt.dns.flags_truncated, 16)
            if hasattr(pkt.dns, 'flags_checkdisable'):
                pkt_dict['layers.dns.dns.flags_tree.dns.flags.checkdisable'] = int(pkt.dns.flags_checkdisable, 16)
            if hasattr(pkt.dns, 'flags_rcode'):
                pkt_dict['layers.dns.dns.flags_tree.dns.flags.rcode'] = int(pkt.dns.flags_rcode, 16)

        # ---- 4. ICMP 層 ----
        if 'ICMP' in pkt:
            # 🟢 不用轉 int
            if hasattr(pkt.icmp, 'udp_stream'):
                pkt_dict['layers.icmp.udp.udp.stream'] = pkt.icmp.udp_stream

            # ⚠️ 必須轉 16 進位
            if hasattr(pkt.icmp, 'checksum'): 
                pkt_dict['layers.icmp.icmp.checksum'] = int(pkt.icmp.checksum, 16)
            if hasattr(pkt.icmp, 'udp_checksum'):
                pkt_dict['layers.icmp.udp.udp.checksum'] = int(pkt.icmp.udp_checksum, 16)

        # ---- 5. RTPS 工控層 ----
        if 'RTPS' in pkt:
            # 🟢 不用轉 int
            if hasattr(pkt.rtps, 'version_minor'):
                pkt_dict['layers.rtps.rtps.version_tree.rtps.version.minor'] = pkt.rtps.version_minor

            # ⚠️ 必須轉 16 進位：工控設備 Vendor ID 都是 Hex（例如 0x0102）
            if hasattr(pkt.rtps, 'vendorid'):
                try:
                    pkt_dict['layers.rtps.rtps.vendorId'] = int(pkt.rtps.vendorid, 16)
                except ValueError:
                    pkt_dict['layers.rtps.rtps.vendorId'] = pkt.rtps.vendorid
            elif hasattr(pkt.rtps, 'vendor_id'):
                try:
                    pkt_dict['layers.rtps.rtps.vendorId'] = int(pkt.rtps.vendor_id, 16)
                except ValueError:
                    pkt_dict['layers.rtps.rtps.vendorId'] = pkt.rtps.vendor_id

    except Exception: 
        pass
    return pkt_dict

def network_sniff_thread_worker():
    """專職嗅探的執行緒工作者"""
    IGNORE_PORTS = [config.PROCESS_PORT, 22]
    if hasattr(config, 'WEB_PORT'):
        IGNORE_PORTS.append(config.WEB_PORT)
        
    filter_string = " and ".join([f"not tcp.port == {p}" for p in IGNORE_PORTS])
    
    print(f"🛡️ [Monitor-PyShark] 啟動防自我嗅探過濾機制...")
    print(f"🎯 過濾規則: {filter_string}")
    
    capture = pyshark.LiveCapture(
        interface='wlan0', 
        include_raw=False, 
        use_json=True, 
        display_filter=filter_string
    )
    
    print(f"[Monitor-PyShark] 網路流量高速監聽引擎已就位...")
    
    for pkt in capture.sniff_continuously():
        pkt_data = parse_packet_to_dict(pkt)
        with buffer_lock:
            packet_buffer.append(pkt_data)

def report_loop():
    """定時回報主循環"""
    consecutive_failures = 0
    while True:
        time.sleep(0.1)
        with buffer_lock:
            if packet_buffer:
                current_batch = list(packet_buffer)
                packet_buffer.clear()
            else:
                current_batch = [{feat: -1 for feat in NET_FEATURES}]
        try:
            payload = {
                "data_source": "pyshark_monitor",
                "packets": current_batch
            }
            response = http_session.post(URL, json=payload, timeout=0.15)
            if response.status_code == 200:
                consecutive_failures = 0
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
            consecutive_failures += 1
            time.sleep(0.3)
        except Exception:
            pass

if __name__ == "__main__":
    sniff_thread = threading.Thread(target=network_sniff_thread_worker, daemon=True)
    sniff_thread.start()
    try:
        report_loop()
    except KeyboardInterrupt:
        print("\n[Monitor-PyShark] 服務手動終止。")