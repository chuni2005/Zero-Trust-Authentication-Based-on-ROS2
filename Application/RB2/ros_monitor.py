import rclpy
from rclpy.node import Node
import time
import threading
import requests
import config
from rosidl_runtime_py.utilities import get_message  # 🚀 動態載入 Message 型態的關鍵工具

PROCESS_IP = config.Process_IP
PROCESS_PORT = config.PROCESS_PORT
URL = f"http://{PROCESS_IP}:{PROCESS_PORT}/process"

# 🚀 完美的 7 個特徵（包含 timestamp）
ROS_FEATURES = ['msg_type', 'msg_data', 'src_topic', 'publisher_count', 'topic_name', 'subscribers_count']#, 'timestamp']

class Ros2TopologyMonitor(Node):
    def __init__(self):
        super().__init__('ros2_topology_monitor')
        print(f"[Monitor-ROS2] 啟動。負責監控特徵數: {len(ROS_FEATURES)} (含 Unix 時間戳)")
        self.latest_msg_data = {}
        self.http_session = requests.Session()
        self.report_thread = threading.Thread(target=self.report_loop, daemon=True)
        self.report_thread.start()

    def _msg_callback(self, topic_name, msg):
        """ 通用回呼函式：當任何被訂閱的 Topic 有新訊息進來時，更新 msg_data 暫存 """
        try:
            # 優先抓取標準欄位 .data (如 String, Int32, Float64 等)
            if hasattr(msg, 'data'):
                # 如果是字串，可以考慮轉成數字或直接傳遞；這裡直接保留原始資料
                self.latest_msg_data[topic_name] = msg.data
            else:
                # 處理複雜的自訂 Message 型態，可將其轉為字串或精簡表達
                self.latest_msg_data[topic_name] = str(msg)[:50]  # 限制長度避免 payload 過大
        except Exception:
            self.latest_msg_data[topic_name] = -1

    def update_dynamic_subscriptions(self, topic_names_and_types):
        """ 根據當前活耀的 Topic 清單，動態維護（新增/刪除）訂閱器 """
        current_topics = set()

        for topic_name, msg_types in topic_names_and_types:
            if not msg_types:
                continue

            # 過濾掉 ROS2 內部系統自身的 Topic，避免無意義監控與無窮解析
            if 'parameter_events' in topic_name or 'rosout' in topic_name:
                continue

            current_topics.add(topic_name)

            # 如果發現了新 Topic，動態建立訂閱
            if topic_name not in self.active_subs:
                try:
                    # 將字串（型態如 'std_msgs/msg/String'）動態轉換成 Python Class
                    msg_class = get_message(msg_types[0])

                    # 建立訂閱，利用 lambda 把 topic_name 當作參數傳給通用 callback
                    self.active_subs[topic_name] = self.create_subscription(
                        msg_class,
                        topic_name,
                        lambda msg, t=topic_name: self._msg_callback(t, msg),
                        10
                    )
                    self.latest_msg_data[topic_name] = 0  # 預設初始值
                except Exception:
                    pass

        # 如果某個 Topic 在系統中消失了，主動銷毀訂閱以釋放記憶體
        for dead_topic in list(self.active_subs.keys()):
            if dead_topic not in current_topics:
                try:
                    self.destroy_subscription(self.active_subs[dead_topic])
                    del self.active_subs[dead_topic]
                    if dead_topic in self.latest_msg_data:
                        del self.latest_msg_data[dead_topic]
                except Exception:
                    pass

    def get_current_topology_metrics(self):
        topology_list = []
        try:
            # 獲取當前生成這批資料的 Unix 時間戳 (秒級浮點數，含毫秒)
            #current_now_ts = time.time()
            
            topic_names_and_types = self.get_topic_names_and_types()
            for topic_name, msg_types in topic_names_and_types:
                pub_count = self.count_publishers(topic_name)
                sub_count = self.count_subscribers(topic_name)
                msg_data_val = self.latest_msg_data.get(topic_name, 0)
                
                # 🧬 嚴格對齊這 7 大欄位，直接帶上 timestamp
                metrics = {
                    "topic_name": topic_name,
                    "msg_type": msg_types[0] if msg_types else "-1",
                    "msg_data": msg_data_val,
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