import os
import sys
import time
import queue
import threading
import requests
import config
import json
import numpy as np
import pandas as pd
import warnings
from collections import deque
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

app = Flask(__name__)

# 配置高頻執行緒池與 HTTP Session 持續連接
executor = ThreadPoolExecutor(max_workers=20)
http_session = requests.Session()

PROCESS_PORT = config.PROCESS_PORT
MODEL_IP = config.MODEL_IP
MODEL_PORT = config.MODEL_PORT
MODEL_URL = f"http://{MODEL_IP}:{MODEL_PORT}/predict"

SAVED_FEATURES_PATH = "feature_names.npy"
data_queue = queue.Queue()

# =========================================================================
# ⏱️ 狀態記憶與 1 秒鐘滑動時間窗（Stateful Buffers）与全局对齐状态
# =========================================================================
packet_window = deque()

# 🛡️ 核心對齊互斥鎖與快取儲存區
alignment_lock = threading.Lock()

# 💡 本地最新狀態快取（由 OS/ROS2 定時刷新，被 Pyshark 讀取）
last_known_os_state = {}
last_known_ros_state = {}

def update_sliding_window(current_time):
    """ 清除超過 1 秒鐘的舊封包歷史紀錄 """
    while packet_window and (current_time - packet_window[0][0] > 1.0):
        packet_window.popleft()

def is_convertible_to_numeric(val):
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False

# =========================================================================
# 🛠️ 鋼鐵維度前處理器 (LivePreprocessor)
# =========================================================================

class LivePreprocessor:
    def __init__(self, saved_features_path):
        self.file_lock = threading.Lock()
        print(f"🧩 [初始化] 正在由 {saved_features_path} 載入模型特徵模具...")
        if os.path.exists(saved_features_path):
            self.features = np.load(saved_features_path, allow_pickle=True).tolist()
        else:
            print(f"❌ 找不到 {saved_features_path}！請確認檔案位置。")
            sys.exit(1)
            
        if 'attack' in self.features: self.features.remove('attack')
        if 'label' in self.features: self.features.remove('label')
            
        self.features = [str(f).strip() for f in self.features]

        try:
            with open('dataset_mapping_info.json', 'r', encoding='utf-8') as f:
                self.config_dict = json.load(f)
                self.json_path = 'dataset_mapping_info.json'
                print(self.config_dict)
        except FileNotFoundError:
            print("❌ 找不到 dataset_mapping_info.json！請檢查檔案路徑。")
            sys.exit(1)

        self.payload_cols = [
            'layers.udp.udp.payload',
            'layers.icmp.udp.udp.payload',
            'layers.icmp.tcp.tcp.payload',
            'layers.icmp.ssh.ssh.encrypted_packet'
        ]

        self.expected_dim = len(self.features)
        print(f"🎯 [模具校準完畢] 模型期待的總數為: {self.expected_dim} 維")

    def ensure_json_fields(self, feature, feature_value, default_value=-1):
        val_str = str(feature_value).strip()
        if feature not in self.config_dict:
            return feature_value

        if val_str in self.config_dict[feature]:
            return self.config_dict[feature][val_str]
        else:
            max_val = max(self.config_dict[feature].values())
            self.config_dict[feature][val_str] = max_val + 1
        return self.config_dict[feature][val_str]

    def process(self, merged_df, recent_packets, recent_syn_ratio):
        df = merged_df.copy()
        df.columns = [str(c).strip() for c in df.columns]

        for col in self.payload_cols:
            if col in df.columns:
                raw_val = df[col].iloc[0]
                if pd.isna(raw_val) or str(raw_val).strip() in ['-1', '-1.0']:
                    df[col] = 0
                else:
                    val_str = str(raw_val).strip()
                    df[col] = f"{val_str[:11]}_{len(val_str)}"

        for col in df.columns:
            if col in ['recent_packets_in_1s', 'recent_syn_ratio_in_1s']:
                continue
                
            raw_val = df[col].iloc[0]

            val_str = str(raw_val).strip()

            df[col] = self.ensure_json_fields(col, val_str)
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 把 NaN 補成 -1
            df[col] = df[col].fillna(-1)
            
        if 'recent_packets_in_1s' in self.features: df['recent_packets_in_1s'] = int(recent_packets)
        if 'recent_syn_ratio_in_1s' in self.features: df['recent_syn_ratio_in_1s'] = float(recent_syn_ratio)

        processed_df = df.reindex(columns=self.features)
        processed_df = processed_df.replace([np.inf, -np.inf], np.nan)
        processed_df = processed_df.fillna(-1)
        
        model_input_array = processed_df.values 
        return model_input_array, "READY"

preprocessor = LivePreprocessor(SAVED_FEATURES_PATH)


# =========================================================================
# 🚀 絕對傳輸保障發送端
# =========================================================================
def send_to_model_engine(features_matrix):
    try:
        if features_matrix.shape != (1, preprocessor.expected_dim):
            print(f"❌ [傳輸攔截] 維度 {features_matrix.shape} 錯誤，非預期 (1, {preprocessor.expected_dim})！已拋棄。")
            return

        payload = {"features": features_matrix.tolist()}
        response = http_session.post(MODEL_URL, json=payload, timeout=0.2)
        
        if response.status_code == 200:
            res_json = response.json()
            attack_score = res_json.get("attack_score", 0.0)
            prediction = res_json.get("prediction", 0)
            score_percentage = attack_score * 100
            if score_percentage > 50.0 or prediction == 1:
                print(f"🚨 [IDS 警報] 偵測到惡意工控攻擊！ 攻擊機率: {score_percentage:.2f}% | 判定狀態: {prediction}")
            elif score_percentage > 5.0:
                print(f"⚠️ [敏感觀測] 分數產生浮動。 攻擊機率: {score_percentage:.2f}%")
            else:
                print(f"🟢 [安全運作] 系統環境純淨。 攻擊機率: {score_percentage:.2f}%")
                
    except requests.exceptions.Timeout:
        print("❌ [網路超時] Model Engine 推論超時。")
    except Exception as e:
        print(f"❌ [傳輸失敗] 轉發模型端發生異常: {str(e)}")


# =========================================================================
# 🎛️ 事件驅動型 Consumer Worker（核心邏輯改造）
# =========================================================================
def alignment_consumer_worker():
    global last_known_os_state, last_known_ros_state
    print("⚡ [Alignment Worker] 網路事件即時驅動管線啟動...")
    
    while True:
        try:
            try:
                # 提高吞吐響應，降低 timeout
                data_packet = data_queue.get(timeout=0.005)
            except queue.Empty:
                continue

            source = data_packet.get("data_source")
            raw_payload_list = data_packet.get("payload_list")

            if not raw_payload_list:
                data_queue.task_done()
                continue
            
            with alignment_lock:
                # ---------------------------------------------------------
                # 情況 A：收到 OS 或 ROS2 資訊 -> 立即更新本地快取，不觸發發送
                # ---------------------------------------------------------
                if source == "os_monitor":
                    if raw_payload_list and isinstance(raw_payload_list[0], dict):
                        for k, v in raw_payload_list[0].items():
                            if v != -1: 
                                last_known_os_state[k] = v
                    data_queue.task_done()
                    continue

                elif source == "ros_monitor":
                    if raw_payload_list and isinstance(raw_payload_list[0], dict):
                        for k, v in raw_payload_list[0].items():
                            if k == 'publisher_count':
                                last_known_ros_state['publisher_count'] = v
                            elif v != -1:
                                last_known_ros_state[k] = v
                    data_queue.task_done()
                    continue

                # ---------------------------------------------------------
                # 情況 B：收到 Pyshark 網路資訊 -> 【核心觸發發動機】
                # ---------------------------------------------------------
                elif source == "pyshark_monitor":
                    pyshark_payloads = raw_payload_list
                    
                    # 🛡️ 鋼鐵防線：過濾偽包
                    if len(pyshark_payloads) == 1 and pyshark_payloads[0].get("layers.ip.ip.proto", -1) == -1:
                        data_queue.task_done()
                        continue

                    # 1. 計算 1 秒鐘網路滑動視窗統計特徵
                    current_time = time.time()
                    for pkt in pyshark_payloads:
                        is_tcp = 1 if pkt.get("layers.ip.ip.proto") in [6, '6'] else 0
                        tcp_flags = str(pkt.get("layers.tcp.tcp.flags", "0")).strip()
                        is_syn = 1 if is_tcp and tcp_flags in ["0x0002", "0x02", "2", 2] else 0
                        packet_window.append((current_time, is_syn, is_tcp))
                    
                    update_sliding_window(current_time)
                    
                    recent_packets_in_1s = len(packet_window)
                    total_tcp_1s = sum(1 for x in packet_window if x[2] == 1)
                    total_syn_1s = sum(1 for x in packet_window if x[1] == 1)
                    recent_syn_ratio_in_1s = (total_syn_1s / total_tcp_1s) if total_tcp_1s > 0 else 0.0

                    # 2. 物理打包：融合本地最新的 OS、ROS 狀態以及剛抵達的 Pyshark 數據
                    flattened_data = {}
                    flattened_data.update(last_known_os_state)   # 載入當前本地最新 OS 欄位
                    flattened_data.update(last_known_ros_state)  # 載入當前本地最新 ROS2 欄位
                    flattened_data.update(pyshark_payloads[0])    # 載入當前觸發的 Pyshark 欄位

                    if 'forward_packets' in preprocessor.features:
                        flattened_data['forward_packets'] = int(recent_packets_in_1s)

                    # 3. 前處理與非同步派發模型端
                    df_live = pd.DataFrame([flattened_data])
                    X_input, status = preprocessor.process(df_live, recent_packets_in_1s, recent_syn_ratio_in_1s)
                    
                    if X_input is not None and status == "READY":
                        print(f"⚡ [Pyshark 驅動] 即時打包送出！(快取狀態: OS_cols={len(last_known_os_state)}, ROS2_cols={len(last_known_ros_state)})")
                        executor.submit(send_to_model_engine, X_input)

            data_queue.task_done()
        except Exception as e:
            print(f"💥 [背景核心異常] 合併管線發生崩潰: {str(e)}")

# 啟動背景處理執行緒
threading.Thread(target=alignment_consumer_worker, daemon=True).start()


# =========================================================================
# 5. Flask 接收路由
# =========================================================================
@app.route("/process", methods=["POST"])
def receive_raw_data():
    try:
        raw_data = request.get_json()
        if not raw_data or not isinstance(raw_data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON format"}), 400

        source = raw_data.get("data_source")
        if source not in ["os_monitor", "pyshark_monitor", "ros_monitor"]:
            return jsonify({"status": "ignored", "message": "Unknown source"}), 200

        if source == "os_monitor":
            metrics_field = raw_data.get("metrics", {})
            actual_payload_list = [metrics_field] if isinstance(metrics_field, dict) else metrics_field
        elif source == "pyshark_monitor":
            packets_field = raw_data.get("packets", [])
            actual_payload_list = packets_field if isinstance(packets_field, list) else [packets_field]
        else:
            topo_field = raw_data.get("topology", [])
            actual_payload_list = topo_field if isinstance(topo_field, list) else [topo_field]
            
        data_queue.put({
            "data_source": source,
            "arrival_ts": time.time(),
            "payload_list": actual_payload_list
        })

        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print(f"🚀 [6號-Preprocess] Pyshark 事件驅動即時對齊核心啟動...")
    print(f"📡 監聽埠口: 0.0.0.0:{PROCESS_PORT} ...")
    app.run(host="0.0.0.0", port=PROCESS_PORT, debug=False, threaded=True)
