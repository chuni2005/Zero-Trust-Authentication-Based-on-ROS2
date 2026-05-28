# pip install requests
# pip install pandas
import time
import requests
import os
import config
import csv
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import subprocess
Process_IP = config.Process_IP
Process_PORT = config.Process_PORT
PROCESS_URL = f"http://{Process_IP}:{Process_PORT}/process"

MONITOR_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "monitor"))
OS_CSV_PATH = os.path.join(MONITOR_BASE_DIR, "OS", "OS_monitor.csv")
ROS2_CSV_PATH = os.path.join(MONITOR_BASE_DIR, "ROSBags", "ros2_monitor.csv")
TSHARK_PCAP_PATH = os.path.join(MONITOR_BASE_DIR, "Tshark", "temp_capture.pcapng")
TSHARK_CSV_PATH = os.path.join(MONITOR_BASE_DIR, "Tshark", "tshark_monitor.csv")

N_MS = 500
class MonitorCollector(Node):
    def __init__(self, processor: MonitorProcessor):
        super().__init__('monitor_collector')
        self.processor = processor
        # 訂閱來自 RPi 1 的控制通道
        self.subscription = self.create_subscription(
            String,
            'monitor/trigger',
            self.listener_callback,
            10)
        self.pipeline_timer = self.create_timer(2.0, self.run_feature_pipeline)
        self.get_logger().info('RPi 2 Monitor Collector Node Started.')
        self.get_logger().info('Listening for trigger command from RPi 1...\n')

    def listener_callback(self, msg):
        command_data = msg.data
        self.get_logger().info(f'Received from RPi 1: "{command_data}"')

    def run_feature_pipeline(self):
        try:
            # 1. 執行耗時的 pcap 轉換
            pcap2csv()
        except Exception as e:
            self.get_logger().error(f"[Pipeline] Pcap 轉產物失敗: {e}")
            return

        # 2. 呼叫解耦後的處理器，獲取這 2 秒內切分好的所有 N ms 資料包
        raw_products = self.processor.process_and_merge()

        # 3. 傳送給前處理
        if raw_products:
            send_to_preprocess(raw_products)
            self.get_logger().info(
                f"[Pipeline] 成功處理並送出 {len(raw_products)} 筆 N_MS 區間數據。"
            )

class MonitorProcessor:

    def __init__(self, os_csv, ros2_csv, tshark_csv):
        self.csv_paths = {
            "os": os_csv,
            "ros2": ros2_csv,
            "tshark": tshark_csv,
        }
        # 增量讀取指針
        self.pointers = {"os": 0, "ros2": 0, "tshark": 0}
    def _get_new_rows(self, key: str) -> list:
        path = self.csv_paths[key]
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            self.pointers[key] = 0
            return []
        new_rows = []
        last_idx = self.pointers[key]

        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader)  # 讀取標頭

                # 跳過上一次已經讀過的行數
                for _ in range(last_idx):
                    next(reader, None)

                # 讀取全新的資料
                current_idx = last_idx
                for row in reader:
                    current_idx += 1
                    if len(row) == len(headers):
                        new_rows.append(dict(zip(headers, row)))

                # 更新指針紀錄
                self.pointers[key] = current_idx
        except Exception as e:
            print(f"讀取 {path} 新資料時出錯: {e}")
        return new_rows
    def process_and_merge(self) -> list:
        os_news = self._get_new_rows("os")
        ros2_news = self._get_new_rows("ros2")
        tshark_news = self._get_new_rows("tshark")

        if not tshark_news:
            print("警告: 目前沒有最新的 Tshark 流量資料。")
            return []

        os_buckets = {}
        for row in os_news:
            try:
                os_time_col = "ms" if "ms" in row else "timestamp"
                ts = int(row.get(os_time_col, 0))
                bucket = (ts // N_MS) * N_MS
                os_buckets[bucket] = row  # 同區間內，後面的（新的）覆蓋前面的
            except ValueError:
                continue
        ros2_buckets = {}
        for row in ros2_news:
            try:
                ros2_time_col = "ms" if "ms" in row else "timestamp"
                ts = int(row.get(ros2_time_col, 0))
                bucket = (ts // N_MS) * N_MS
                ros2_buckets[bucket] = row
            except ValueError:
                continue
        tshark_buckets = {}
        for row in tshark_news:
            try:
                epoch_str = row.get("frame.time_epoch") or "0"
                ts_ms = int(float(epoch_str) * 1000)
                bucket = (ts_ms // N_MS) * N_MS

                # 加工 Tshark 特徵
                row["frame.len"] = int(row.get("frame.len") or 0)
                row["ip.proto"] = int(row.get("ip.proto") or 0)

                udp_src = int(row.get("udp.srcport") or 0)
                tcp_src = int(row.get("tcp.srcport") or 0)
                row["src_port"] = udp_src + tcp_src
                udp_dst = int(row.get("udp.dstport") or 0)
                tcp_dst = int(row.get("tcp.dstport") or 0)
                row["dst_port"] = udp_dst + tcp_dst

                tshark_buckets[bucket] = row
            except Exception as e:
                print(f"加工 Tshark 特徵時發生錯誤: {e}")
                continue

        merged_products = []
        for bucket in sorted(tshark_buckets.keys()):
            tshark_row = tshark_buckets[bucket]
            os_row = os_buckets.get(bucket, {})
            ros2_row = ros2_buckets.get(bucket, {})

            merged_status = {}
            if os_row:
                merged_status.update({f"os_{k}": v for k, v in os_row.items()})
            if ros2_row:
                merged_status.update({f"ros2_{k}": v for k, v in ros2_row.items()})
            merged_status.update({f"net_{k}": v for k, v in tshark_row.items()})
            merged_status["merged_bucket_ms"] = bucket
            merged_products.append(merged_status)

        return merged_products

def pcap2csv(pcap_path: str = TSHARK_PCAP_PATH, output_csv_path: str = TSHARK_CSV_PATH):
    if not os.path.exists(pcap_path):
        raise FileNotFoundError(f"找不到來源 pcap 檔案: {pcap_path}")

    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

    fields = [
        "_ws.col.No",           # 封包編號
        "frame.time_epoch",     # Epoch 時間戳記（精確到微秒，適合時間序列分析）
        "frame.len",            # 封包長度 (Bytes)
        "ip.src",               # 來源 IP
        "ip.dst",               # 目的 IP
        "ip.proto",             # 傳輸層協定代碼 (例如 17=UDP, 6=TCP)
        "udp.srcport",          # UDP 來源連接埠
        "udp.dstport",          # UDP 目的連接埠
        "tcp.srcport",          # TCP 來源連接埠
        "tcp.dstport"           # TCP 目的連接埠
    ]

    cmd = ["tshark", "-r", pcap_path, "-T", "fields"]
    for field in fields:
        cmd.extend(["-e", field])

    cmd.extend([
        "-E", "separator=,",
        "-E", "header=y",
        "-E", "occurrence=f"
    ])
    print(f"正在轉換 {pcap_path} -> {output_csv_path}...")

    try:
        with open(output_csv_path, "w", newline="", encoding="utf-8") as csv_file:
            subprocess.run(cmd, stdout=csv_file, stderr=subprocess.PIPE, check=True, text=True)
        print("轉換完成！")

    except subprocess.CalledProcessError as e:
        print(f"Tshark 執行失敗！錯誤訊息：\n{e.stderr}")
        raise e
    except FileNotFoundError:
        print("系統未安裝 Tshark 或未將其加入環境變數（PATH）。")
        raise

def send_to_preprocess(raw_data: list):
    if not raw_data:
        print("[Pipeline] 原始數據為空，取消發送給 Process。")
        return
    print(f"[Pipeline] 正在將原始監控快照送往後端 Process 程序 ({PROCESS_URL})...")
    try:
        # 將原始的 list 包含的綜合字典直接以 JSON 格式 POST 給 Process
        response = requests.post(PROCESS_URL, json=raw_data, timeout=1.5)

        if response.status_code == 200:
            print(f"[Pipeline] Process 成功接收原始資料，響應: {response.json()}")
        else:
            print(f"[Pipeline] 發送成功，但 Process 回傳錯誤代碼: {response.status_code}")
    except requests.exceptions.Timeout:
        print("[Pipeline] 錯誤：連線 Process 超時！")
    except requests.exceptions.ConnectionError:
        print("[Pipeline] 錯誤：連線失敗！請檢查後端 Process 程序是否啟動。")
    except Exception as e:
        print(f"[Pipeline] 發送至 Process 時發生未預期錯誤: {str(e)}")

def main(args=None):
    rclpy.init(args=args)
    processor = MonitorProcessor(
        os_csv=OS_CSV_PATH,
        ros2_csv=ROS2_CSV_PATH,
        tshark_csv=TSHARK_CSV_PATH,
    )
    node = MonitorCollector(processor=processor)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down RPi 2 Collector...')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()