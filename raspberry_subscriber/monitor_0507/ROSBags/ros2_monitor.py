import rclpy
from rclpy.node import Node
import csv
import time
import importlib

OUTPUT_FILENAME = "ros2_monitor.csv"

class ROSPaCeMonitorNode(Node):
    def __init__(self):
        super().__init__('ros2_monitor_node')
        
        # 加入時間戳與話題名稱以利後續合併，並保留論文 Table 3 的 5 個特徵
        self.fieldnames = [
            'ms',                 # 新增：用於與 OS / Tshark 資料對齊
            'topic_name',         # 新增：紀錄話題名稱
            'src_topic',          # 來源節點 (論文描述為 Indicates the source node)
            'subscribers_count',  # 訂閱者數量
            'publisher_count',    # 發布者數量
            'msg_type',           # 訊息類型
            'msg_data'            # 訊息標頭 (Header)
        ]
        
        self.init_csv()
        
        # 存放動態建立的訂閱者與最新收到的訊息數據
        self.dynamic_subs = {}
        self.latest_msg_data = {}
        
        # 依照論文設定，以 200 毫秒 (0.2 秒) 的週期執行監控
        self.timer = self.create_timer(0.2, self.monitor_cycle)
        self.get_logger().info("🕵️ ROSPaCe Monitor Node 已啟動，每 200ms 進行一次採集...")

    def init_csv(self):
        with open(OUTPUT_FILENAME, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.fieldnames)
            writer.writeheader()

    def get_message_class(self, msg_type_str):
        """動態載入 ROS2 訊息類別"""
        try:
            parts = msg_type_str.split('/')
            if len(parts) == 3:
                pkg_name, _, class_name = parts
                module = importlib.import_module(f"{pkg_name}.msg")
                return getattr(module, class_name)
        except Exception as e:
            self.get_logger().debug(f"無法載入訊息類別 {msg_type_str}: {e}")
        return None

    def create_dynamic_callback(self, topic_name):
        """產生一個專屬於該 topic 的 callback 函式，用來擷取 msg_data (Header)"""
        def callback(msg):
            # 依照論文擷取 Header
            if hasattr(msg, 'header'):
                # 如果有標準的 std_msgs/Header，擷取 frame_id 與時間戳
                header_info = f"frame_id:{msg.header.frame_id}, stamp:{msg.header.stamp.sec}.{msg.header.stamp.nanosec}"
            else:
                # 若無 Header，取資料的前 30 個字元作為特徵替代
                header_info = str(msg)[:30].replace('\n', ' ')
            
            self.latest_msg_data[topic_name] = header_info
            
        return callback

    def monitor_cycle(self):
        """每 200ms 執行的主迴圈"""
        # 獲取當前所有的 topic 與其 type
        topic_names_and_types = self.get_topic_names_and_types()
        
        data_rows = []
        current_ms = int(time.time() * 1000)  # 獲取當下的 Unix 時間戳，對齊其他 CSV
        
        for topic_name, topic_types in topic_names_and_types:
            if not topic_types:
                continue
                
            msg_type_str = topic_types[0] # 通常一個 topic 只有一種 type
            
            # 1. 如果是新出現的 topic，嘗試動態訂閱它以獲取 msg_data
            if topic_name not in self.dynamic_subs:
                msg_class = self.get_message_class(msg_type_str)
                if msg_class:
                    cb = self.create_dynamic_callback(topic_name)
                    # 建立訂閱者
                    sub = self.create_subscription(msg_class, topic_name, cb, 10)
                    self.dynamic_subs[topic_name] = sub
                    self.latest_msg_data[topic_name] = "Waiting for data..."
            
            # 2. 獲取 Table 3 需要的統計數據
            pub_count = self.count_publishers(topic_name)
            sub_count = self.count_subscribers(topic_name)
            
            # 獲取來源節點 (src_topic: Indicates the source node)
            publishers_info = self.get_publishers_info_by_topic(topic_name)
            src_nodes = [info.node_name for info in publishers_info]
            src_topic_str = "|".join(src_nodes) if src_nodes else "Unknown"
            
            # 獲取最新訊息標頭 (若尚未收到則為預設字串)
            msg_data_str = self.latest_msg_data.get(topic_name, "No data")
            
            # 忽略完全沒有活動的閒置 topic
            if pub_count == 0 and sub_count == 0:
                continue

            # 3. 組合這一行的資料
            row = {
                'ms': current_ms,
                'topic_name': topic_name,
                'src_topic': src_topic_str,
                'subscribers_count': sub_count,
                'publisher_count': pub_count,
                'msg_type': msg_type_str,
                'msg_data': msg_data_str
            }
            data_rows.append(row)

        # 將此週期的資料寫入 CSV
        if data_rows:
            with open(OUTPUT_FILENAME, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.fieldnames)
                writer.writerows(data_rows)

def main(args=None):
    rclpy.init(args=args)
    monitor_node = ROSPaCeMonitorNode()
    
    try:
        rclpy.spin(monitor_node)
    except KeyboardInterrupt:
        monitor_node.get_logger().info("接收到中斷訊號，正在關閉監控節點...")
    finally:
        monitor_node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()