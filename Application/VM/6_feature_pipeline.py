import time
import requests
import pandas as pd
import glob
import os
import config

PC1_IP = config.PC1_IP
PC1_PORT = config.WEB_PORT
Model_URL = f"http://{config.Model_IP}:{config.MODEL_PORT}/predict"

MONITOR_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "monitor"))
OS_CSV_PATH = os.path.join(MONITOR_BASE_DIR, "OS", "OS_monitor.csv")
ROS2_CSV_PATH = os.path.join(MONITOR_BASE_DIR, "ROSBags", "ros2_monitor.csv")
TSHARK_PCAP_PATH = os.path.join(MONITOR_BASE_DIR, "Tshark", "temp_capture.pcapng")

def find_monitor_products():
    """
    TODO:
    get monitor csv
    """

def preprocess_and_merge(raw_data):
    """
    TODO:
    串接前處理
    """

def send_to_model_engine(features):
    print(f"[Pipeline] 正在將特徵送往 MODEL ({MODEL_API_URL})...")
    try:
        response = requests.post(MODEL_API_URL, json=features, timeout=1.5)

        if response.status_code == 200:
            print(f"[Pipeline] 成功接收來自 Model Engine 的預測結果: {response.json()}")
        else:
            print(f"[Pipeline] 發送成功，但 Model 噴出錯誤代碼: {response.status_code}")
    except requests.exceptions.Timeout:
        print("[Pipeline] 錯誤：傳送超時！可能沒有啟動或網路太卡")
    except requests.exceptions.ConnectionError:
        print("[Pipeline] 錯誤：連線失敗！請檢查連線是否中斷。")
    except Exception as e:
        print(f"[Pipeline] 發生未預期的錯誤: {str(e)}")

def main():
    start_time = time.time()

    # 1. 撈取監視器產物
    raw_products = find_monitor_products()

    # 2. 前處理與融合出 480 個特徵
    final_features = preprocess_and_merge(raw_products)

    # 3. 直送 PC1 Model
    send_to_model_engine(final_features)

    end_time = time.time()
    print(f"[Pipeline] 本次流水線執行完畢。耗時: {end_time - start_time:.4f} 秒。\n")

if __name__ == "__main__":
    main()