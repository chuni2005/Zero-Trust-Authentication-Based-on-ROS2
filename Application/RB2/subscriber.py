# pip install pyshark requests psutil rclpy
import time
import requests
import os
from application import config
import importlib
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import pyshark
import threading
import psutil

Process_IP = config.Process_IP
Process_PORT = config.PROCESS_PORT
PROCESS_URL = f"http://{Process_IP}:{Process_PORT}/process"

INTERFACE_NAME = "wlan0" 

# Global configuration for 200ms streaming interval
N_MS = 200
INTERVAL_SEC = 0.2 

class MonitorProcessor:
 
    def __init__(self):
        self.live_network_buffer = []
        self.buffer_lock = threading.Lock()
        
        self.latest_os_snapshot = {}
        self.os_lock = threading.Lock()
        
        self.latest_ros2_snapshot = {}
        self.ros2_lock = threading.Lock()

        # ?? 規格固化：完美 62 個不重複的純特徵欄位順序（完全對齊訓練集，已剔除末尾重複的 publishers_count）
        self.target_fields = [
            'layers.dns.dns.flags_tree.dns.flags.authoritative', 'layers.dns.dns.response_to', 'Disk_Write', 'Active',
            'layers.icmp.udp.udp.checksum', 'Inactive', 'layers.dns.dns.flags_tree.dns.flags.recdesired',
            'layers.dns.dns.flags_tree.dns.flags.response', 'Tcp_Established', 'Buffers', 'MemFree', 'pgfree',
            'layers.rtps.rtps.version', 'layers.ip.ip.checksum', 'pgalloc_dma', 'Net_Received', 'pgpgin',
            'layers.ip.ip.ttl', 'layers.rtps.rtps.magic', 'layers.rtps.rtps.version_tree.rtps.version.minor',
            'publishers_count', 'pgactivate', 'Tcp_Close', 'layers.udp.udp.checksum', 'src_topic', 'Tcp_TimeWait',
            'msg_data', 'SwapFree', 'nr_inactive_file', 'nr_active_file',
            'layers.rtps.rtps.version_tree.rtps.version.major', 'pgmajfault', 'layers.dns.dns.count.answers', 'Cached',
            'layers.dns.dns.flags_tree.dns.flags.opcode', 'layers.udp.udp.stream', 'layers.icmp.ip.ip.checksum',
            'subscribers_count', 'layers.dns.dns.count.add_rr', 'layers.dns.dns.flags_tree.dns.flags.ad',
            'layers.icmp.icmp.checksum', 'Tcp_Syn', 'layers.dns.dns.flags_tree.dns.flags.recavail',
            'layers.dns.dns.flags_tree.dns.flags.z', 'pgfault', 'layers.dns.dns.count.queries', 'msg_type',
            'layers.udp.udp.payload', 'pgdeactivate', 'layers.ip.ip.ttl_tree._ws.expert._ws.expert.severity',
            'layers.ip.ip.ttl_tree._ws.expert._ws.expert.group', 'layers.dns.dns.flags_tree.dns.flags.truncated',
            'layers.udp.udp.stream.pnum', 'pgpgout', 'layers.dns.dns.flags', 'layers.rtps.rtps.vendorId',
            'layers.ip.ip.stream', 'Tcp_Listen', 'topic_name', 'Net_Sent', 'Disk_Read'
        ]

        # 定義 ROS2 欄位集合，優化合併時的型態安全
        self.ros2_fields = {'publishers_count', 'subscribers_count', 'topic_name', 'src_topic', 'msg_type', 'msg_data'}

    def sample_linux_metrics_loop(self):
        print("[Linux Monitor] Real-time memory-based OS monitoring thread started.")
        while True:
            try:
                vmstat = {}
                with open('/proc/vmstat', 'r') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) == 2:
                            vmstat[parts[0]] = int(parts[1])

                mem = psutil.virtual_memory()
                swap = psutil.swap_memory()
                net_io = psutil.net_io_counters()
                disk_io = psutil.disk_io_counters()
                conns = psutil.net_connections(kind='tcp')

                metrics_dict = {
                    'Disk_Write': disk_io.write_bytes,
                    'Active': mem.active,
                    'Inactive': mem.inactive,
                    'Tcp_Established': len([c for c in conns if c.status == 'ESTABLISHED']),
                    'Buffers': mem.buffers,
                    'MemFree': mem.free,
                    'pgfree': vmstat.get('pgfree', 0),
                    'pgalloc_dma': vmstat.get('pgalloc_dma', 0),
                    'Net_Received': net_io.bytes_recv,
                    'pgpgin': vmstat.get('pgpgin', 0),
                    'pgactivate': vmstat.get('pgactivate', 0),
                    'Tcp_Close': len([c for c in conns if c.status == 'CLOSE']),
                    'SwapFree': swap.free,
                    'nr_inactive_file': vmstat.get('nr_inactive_file', 0),
                    'nr_active_file': vmstat.get('nr_active_file', 0),
                    'pgmajfault': vmstat.get('pgmajfault', 0),
                    'Cached': mem.cached,
                    'Tcp_Syn': len([c for c in conns if c.status in ('SYN_SENT', 'SYN_RECV')]),
                    'pgfault': vmstat.get('pgfault', 0),
                    'pgdeactivate': vmstat.get('pgdeactivate', 0),
                    'pgpgout': vmstat.get('pgpgout', 0),
                    'Tcp_Listen': len([c for c in conns if c.status == 'LISTEN']),
                    'Net_Sent': net_io.bytes_sent,
                    'Disk_Read': disk_io.read_bytes
                }

                with self.os_lock:
                    self.latest_os_snapshot = metrics_dict
            except Exception as e:
                print(f"[Error] Linux Monitor sampling exception: {e}")
            
            time.sleep(INTERVAL_SEC)

    def add_live_packet(self, pkt):
        try:
            net_dict = {}
            ts_epoch = float(pkt.sniff_timestamp)
            net_dict["_internal_ts_ms"] = int(ts_epoch * 1000)

            if 'IP' in pkt:
                net_dict['layers.ip.ip.checksum'] = getattr(pkt.ip, 'checksum', "")
                net_dict['layers.ip.ip.ttl'] = int(getattr(pkt.ip, 'ttl', 0))
                net_dict['layers.ip.ip.stream'] = getattr(pkt.ip, 'stream', "")
                net_dict['layers.ip.ip.ttl_tree._ws.expert._ws.expert.severity'] = ""
                net_dict['layers.ip.ip.ttl_tree._ws.expert._ws.expert.group'] = ""

            if 'UDP' in pkt:
                net_dict['layers.udp.udp.checksum'] = getattr(pkt.udp, 'checksum', "")
                net_dict['layers.udp.udp.stream'] = getattr(pkt.udp, 'stream', "")
                net_dict['layers.udp.udp.payload'] = getattr(pkt.udp, 'payload', "")
                net_dict['layers.udp.udp.stream.pnum'] = getattr(pkt.udp, 'stream.pnum', "")
            
            if 'ICMP' in pkt:
                net_dict['layers.icmp.udp.udp.checksum'] = "" 
                net_dict['layers.icmp.ip.ip.checksum'] = getattr(pkt.icmp, 'checksum', "")
                net_dict['layers.icmp.icmp.checksum'] = getattr(pkt.icmp, 'checksum', "")

            if 'DNS' in pkt:
                net_dict['layers.dns.dns.flags_tree.dns.flags.authoritative'] = getattr(pkt.dns, 'flags_authoritative', "")
                net_dict['layers.dns.dns.response_to'] = getattr(pkt.dns, 'response_to', "")
                net_dict['layers.dns.dns.flags_tree.dns.flags.recdesired'] = getattr(pkt.dns, 'flags_recdesired', "")
                net_dict['layers.dns.dns.flags_tree.dns.flags.response'] = getattr(pkt.dns, 'flags_response', "")
                net_dict['layers.dns.dns.count.answers'] = getattr(pkt.dns, 'count_answers', "")
                net_dict['layers.dns.dns.flags_tree.dns.flags.opcode'] = getattr(pkt.dns, 'flags_opcode', "")
                net_dict['layers.dns.dns.count.add_rr'] = getattr(pkt.dns, 'count_add_rr', "")
                net_dict['layers.dns.dns.flags_tree.dns.flags.ad'] = getattr(pkt.dns, 'flags_ad', "")
                net_dict['layers.dns.dns.flags_tree.dns.flags.recavail'] = getattr(pkt.dns, 'flags_recavail', "")
                net_dict['layers.dns.dns.flags_tree.dns.flags.z'] = getattr(pkt.dns, 'flags_z', "")
                net_dict['layers.dns.dns.count.queries'] = getattr(pkt.dns, 'count_queries', "")
                net_dict['layers.dns.dns.flags_tree.dns.flags.truncated'] = getattr(pkt.dns, 'flags_truncated', "")
                net_dict['layers.dns.dns.flags'] = getattr(pkt.dns, 'flags', "")

            if 'RTPS' in pkt:
                net_dict['layers.rtps.rtps.version'] = getattr(pkt.rtps, 'version', "")
                net_dict['layers.rtps.rtps.magic'] = getattr(pkt.rtps, 'magic', "")
                net_dict['layers.rtps.rtps.version_tree.rtps.version.minor'] = getattr(pkt.rtps, 'version_minor', "")
                net_dict['layers.rtps.rtps.version_tree.rtps.version.major'] = getattr(pkt.rtps, 'version_major', "")
                net_dict['layers.rtps.rtps.vendorId'] = getattr(pkt.rtps, 'vendorId', "")

            with self.buffer_lock:
                self.live_network_buffer.append(net_dict)
        except Exception:
            pass

    def process_and_merge(self) -> list:
        with self.buffer_lock:
            tshark_news = list(self.live_network_buffer)
            self.live_network_buffer.clear()

        with self.os_lock:
            current_os_data = dict(self.latest_os_snapshot) if self.latest_os_snapshot else {}

        with self.ros2_lock:
            current_ros2_data = dict(self.latest_ros2_snapshot) if self.latest_ros2_snapshot else {}

        if not tshark_news:
            current_time_ms = int(time.time() * 1000)
            bucket = (current_time_ms // N_MS) * N_MS
            tshark_buckets = {bucket: {}}
        else:
            tshark_buckets = {}
            for row in tshark_news:
                try:
                    ts_ms = row.get("_internal_ts_ms", 0)
                    bucket = (ts_ms // N_MS) * N_MS
                    tshark_buckets[bucket] = row
                except Exception:
                    continue

        merged_products = []
        for bucket in sorted(tshark_buckets.keys()):
            net_row = tshark_buckets[bucket]
            final_record = {}
            
            # ?? 欄位型態消毒合併邏輯
            for field in self.target_fields:
                if field.startswith('layers.'):
                    final_record[field] = net_row.get(field, "")
                elif field in self.ros2_fields:
                    # 修正：即使當下暫時沒採集到 ROS 數據，數值型態欄位也給予 0 而非空字串，確保特徵不變異
                    default_val = 0 if 'count' in field else "Waiting..."
                    final_record[field] = current_ros2_data.get(field, default_val)
                else:
                    final_record[field] = current_os_data.get(field, 0)

            final_record['attack'] = 0
            final_record['timestamp'] = int(bucket)

            merged_products.append(final_record)

        return merged_products
        
class CombinedMonitorCollector(Node):

    def __init__(self, processor: MonitorProcessor):
        super().__init__('monitor_collector_node')
        self.processor = processor
        self.dynamic_subs = {}
        self.latest_msg_data = {}
        
        self.ros2_timer = self.create_timer(INTERVAL_SEC, self.monitor_ros2_cycle)
        self.pipeline_timer = self.create_timer(INTERVAL_SEC, self.run_feature_pipeline)
        
        self.get_logger().info(f"? ROSPaCe Integrated Monitor Node started. Merging and streaming features every {N_MS}ms...")

        self.capture_thread = threading.Thread(target=self.start_live_capture, daemon=True)
        self.capture_thread.start()
        self.os_thread = threading.Thread(target=self.processor.sample_linux_metrics_loop, daemon=True)
        self.os_thread.start()

    def get_message_class(self, msg_type_str):
        try:
            parts = msg_type_str.split('/')
            if len(parts) == 3:
                pkg_name, _, class_name = parts
                module = importlib.import_module(f"{pkg_name}.msg")
                return getattr(module, class_name)
        except Exception:
            pass
        return None

    def create_dynamic_callback(self, topic_name):
        def callback(msg):
            if hasattr(msg, 'header'):
                header_info = f"frame_id:{msg.header.frame_id}, stamp:{msg.header.stamp.sec}"
            else:
                header_info = str(msg)[:30].replace('\n', ' ')
            self.latest_msg_data[topic_name] = header_info
        return callback

    def monitor_ros2_cycle(self):
        try:
            topic_names_and_types = self.get_topic_names_and_types()
            
            for topic_name, topic_types in topic_names_and_types:
                if not topic_types or topic_name in ['/parameter_events', '/rosout']:
                    continue
                msg_type_str = topic_types[0]
                
                if topic_name not in self.dynamic_subs:
                    msg_class = self.get_message_class(msg_type_str)
                    if msg_class:
                        cb = self.create_dynamic_callback(topic_name)
                        self.dynamic_subs[topic_name] = self.create_subscription(msg_class, topic_name, cb, 10)
                        self.get_logger().info(f"[ROS2 Monitor] Successfully dynamically subscribed to topic: {topic_name}")
                
                pub_count = self.count_publishers(topic_name)
                sub_count = self.count_subscribers(topic_name)
                
                if pub_count > 0 or sub_count > 0:
                    publishers_info = self.get_publishers_info_by_topic(topic_name)
                    src_nodes = [info.node_name for info in publishers_info]
                    src_topic_str = "|".join(src_nodes) if src_nodes else "Unknown"
                    msg_data_str = self.latest_msg_data.get(topic_name, "Waiting...")

                    ros2_dict = {
                        'publishers_count': pub_count,
                        'subscribers_count': sub_count,
                        'topic_name': topic_name,
                        'src_topic': src_topic_str,
                        'msg_type': msg_type_str,
                        'msg_data': msg_data_str
                    }
                    with self.processor.ros2_lock:
                        self.processor.latest_ros2_snapshot = ros2_dict
                    
        except Exception as e:
            self.get_logger().error(f"[ROS2 Monitor] Sampling cycle exception: {e}")

    def start_live_capture(self):
        self.get_logger().info(f"[Live Mode] Starting PyShark Live Capture on network interface: {INTERFACE_NAME}...")
        capture = pyshark.LiveCapture(interface=INTERFACE_NAME, bpf_filter="ip")
        try:
            capture.apply_on_packets(self.processor.add_live_packet)
        except Exception as e:
            self.get_logger().error(f"[Live Capture Error] Capture thread crashed: {e}")

    def run_feature_pipeline(self):
        raw_products = self.processor.process_and_merge()
        if raw_products:
            send_to_preprocess(raw_products)

def send_to_preprocess(raw_data: list):
    try:
        response = requests.post(PROCESS_URL, json=raw_data, timeout=0.5)
        if response.status_code == 200:
            pass 
        else:
            print(f"[Pipeline] Transmission successful but received abnormal status code: {response.status_code}")
    except requests.exceptions.Timeout:
        print("[Error] Connection to Preprocess back-end timed out!")
    except requests.exceptions.ConnectionError:
        print("[Error] Connection failed. Please check if the Preprocess service on PC1 is running!")
    except Exception as e:
        print(f"[Error] Unexpected error during transmission pipeline: {str(e)}")

def main(args=None):
    rclpy.init(args=args)
    processor = MonitorProcessor()
    node = CombinedMonitorCollector(processor=processor)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Interrupt signal received. Shutting down Integrated Collector...")
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()