import rclpy
from rclpy.node import Node
import time
import threading
import requests
import config

PROCESS_IP = config.Process_IP
PROCESS_PORT = config.PROCESS_PORT
URL = f"http://{PROCESS_IP}:{PROCESS_PORT}/process"

# 🚀 完美的 7 個特徵（包含 timestamp）
ROS_FEATURES = ['msg_type', 'msg_data', 'src_topic', 'publisher_count', 'topic_name', 'subscribers_count']#, 'timestamp']

class Ros2TopologyMonitor(Node):
    def __init__(self):
        super().__init__('ros2_topology_monitor')
        print(f"[Monitor-ROS2] 啟動。負責監控特徵數: {len(ROS_FEATURES)} (含 Unix 時間戳)")
        self.http_session = requests.Session()
        self.report_thread = threading.Thread(target=self.report_loop, daemon=True)
        self.report_thread.start()

    def get_current_topology_metrics(self):
        topology_list = []
        try:
            # 獲取當前生成這批資料的 Unix 時間戳 (秒級浮點數，含毫秒)
            current_now_ts = time.time()
            
            topic_names_and_types = self.get_topic_names_and_types()
            for topic_name, msg_types in topic_names_and_types:
                pub_count = self.count_publishers(topic_name)
                sub_count = self.count_subscribers(topic_name)
                
                # 🧬 嚴格對齊這 7 大欄位，直接帶上 timestamp
                metrics = {
                    "topic_name": topic_name,
                    "msg_type": msg_types[0] if msg_types else "-1",
                    "msg_data": 0, 
                    "src_topic": topic_name, 
                    "publisher_count": pub_count,   
                    "subscribers_count": sub_count
#                    "timestamp": current_now_ts  # 🚀 在這裡直接寫入！
                }
                topology_list.append(metrics)
        except Exception: pass
            
        # 防禦機制：若當前沒任何 ROS2 通訊，仍必須吐出帶有時間戳的模具
        if not topology_list:
            topology_list.append({
                "topic_name": "-1", "msg_type": "-1", "msg_data": -1,
                "src_topic": "-1", "publisher_count": -1, "subscribers_count": -1
#                "timestamp": time.time()
            })
            
        return topology_list

    def report_loop(self):
        while rclpy.ok():
            try:
                payload = {"data_source": "ros_monitor", "topology": self.get_current_topology_metrics()}
                self.http_session.post(URL, json=payload, timeout=0.15)
            except Exception: pass
            time.sleep(0.1)

def main(args=None):
    rclpy.init(args=args)
    node = Ros2TopologyMonitor()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()