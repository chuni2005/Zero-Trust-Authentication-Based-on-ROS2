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

class MonitorCollector(Node):
    def __init__(self):
        super().__init__('monitor_collector')

        # 訂閱來自 RPi 1 的控制通道
        self.subscription = self.create_subscription(
            String,
            'monitor/trigger',
            self.listener_callback,
            10)

        self.get_logger().info('RPi 2 Monitor Collector Node Started.')
        self.get_logger().info('Listening for trigger command from RPi 1...\n')

    def listener_callback(self, msg):
        command_data = msg.data
        self.get_logger().info(f'Received from RPi 1: "{command_data}"')

        # 核心因果：一聽到關鍵字，立刻觸發前處理呼交器
        if 'Monitor wake up' in command_data:
            self.get_logger().info('====== [TRIGGER DETECTED] ======')
            self.get_logger().info('Calling external feature pipeline program...')

            try:
                run_feature_pipeline()
                self.get_logger().info('Feature pipeline triggered successfully.')

            except Exception as e:
                self.get_logger().error(f'Failed to call feature pipeline: {str(e)}')

            self.get_logger().info('================================\n')

def get_last_row_from_csv(csv_path: str) -> dict:
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return {}
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            # 使用 csv.DictReader 讀取，並直接轉成 list 提取最後一行
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows[-1] if rows else {}
    except Exception as e:
        print(f"讀取 {csv_path} 最後一行時出錯: {e}")
        return {}

def find_monitor_products_and_merge():
    os_last = get_last_row_from_csv(OS_CSV_PATH)
    ros2_last = get_last_row_from_csv(ROS2_CSV_PATH)
    tshark_last = get_last_row_from_csv(TSHARK_CSV_PATH)
    if not tshark_last:
        print("警告: 目前沒有最新的 Tshark 流量資料。")
        return []
    try:
        tshark_last["frame.len"] = int(tshark_last.get("frame.len") or 0)
        tshark_last["ip.proto"] = int(tshark_last.get("ip.proto") or 0)

        udp_src = int(tshark_last.get("udp.srcport") or 0)
        tcp_src = int(tshark_last.get("tcp.srcport") or 0)
        tshark_last["src_port"] = udp_src + tcp_src

        udp_dst = int(tshark_last.get("udp.dstport") or 0)
        tcp_dst = int(tshark_last.get("tcp.dstport") or 0)
        tshark_last["dst_port"] = udp_dst + tcp_dst
    except Exception as e:
        print(f"加工 Tshark 特徵時發生非預期錯誤: {e}")
    merged_status = {}
    merged_status.update({f"os_{k}": v for k, v in os_last.items()})
    merged_status.update({f"ros2_{k}": v for k, v in ros2_last.items()})
    merged_status.update({f"net_{k}": v for k, v in tshark_last.items()})
    return [merged_status] if merged_status else []

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

def run_feature_pipeline():
    start_time = time.time()
    try:
        pcap2csv()
    except Exception as e:
        print(f"[Pipeline] 中止本次流水線，原因：Pcap 轉產物失敗 -> {e}")
        return

    raw_products = find_monitor_products_and_merge()
    send_to_preprocess(raw_products)

    end_time = time.time()
    print(f"[Pipeline] 本次流水線執行完畢。耗時: {end_time - start_time:.4f} 秒。\n")

def main(args=None):
    rclpy.init(args=args)
    node = MonitorCollector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down RPi 2 Collector...')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()