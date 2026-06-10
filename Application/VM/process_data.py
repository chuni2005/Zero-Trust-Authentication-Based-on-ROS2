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
last_known_os_state = {}
last_known_ros_state = {}

# 🛡️ 核心對齊互斥鎖與快取儲存區
alignment_lock = threading.Lock()
current_window_bucket = {}
window_timer = None  # 控制 100ms 倒數計時的 Timer 物件

def update_sliding_window(current_time):
    """ 清除超過 1 秒鐘的舊封包歷史紀錄 """
    while packet_window and (current_time - packet_window[0][0] > 1.0):
        packet_window.popleft()

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

    def process(self, merged_df, recent_packets, recent_syn_ratio):
        # 複製 DataFrame 避免改動原始數據
        df = merged_df.copy()
        df.columns = [str(c).strip() for c in df.columns]

        # 先處理特定的 Payload 欄位字串裁剪（保留你原本的邏輯）
        for col in self.payload_cols:
            if col in df.columns:
                raw_val = df[col].iloc[0]
                if pd.isna(raw_val) or str(raw_val).strip() in ['-1', '-1.0']:
                    df[col] = 0
                else:
                    val_str = str(raw_val).strip()
                    df[col] = f"{val_str[:11]}_{len(val_str)}"

        # -------------------------------------------------------------
        # 🛠️ 核心前處理改造：int 優先 -> 轉 int 優先 -> Dict 查表 -> 殘留 -1
        # -------------------------------------------------------------
        for col in df.columns:
            if col in ['recent_packets_in_1s', 'recent_syn_ratio_in_1s', 'forward_packets']:
                continue
                
            raw_val = df[col].iloc[0]

            # 優先過濾掉 pandas 產生的缺失值 (NaN) 或空字串
            if pd.isna(raw_val) or str(raw_val).strip() in ['', 'nan', 'NaN']:
                df[col] = -1
                continue

            # 🛠️ 1. 如果資料本身就是 int 或是 NumPy 的整數
            if isinstance(raw_val, (int, np.integer)):
                df[col] = int(raw_val)
                continue

            # 🛠️ 2. 嘗試硬轉成 int（能轉的就轉 int，包含數字字串、浮點數）
            try:
                # 透過 float 再轉 int 確保能完美消化像 "64.0" 這類的數值字串
                df[col] = int(float(raw_val))
                continue
            except (ValueError, TypeError):
                # 如果報錯代表包含字母、冒號（如 Hex 碼或 Payload），無法直接轉 int
                pass

            # 🛠️ 3. 不能直接轉 int 的，比照 Dict 字典進行查表對應
            val_str = str(raw_val).strip()
            if col in self.config_dict and val_str in self.config_dict[col]:
                try:
                    df[col] = int(self.config_dict[col][val_str])
                except (ValueError, TypeError):
                    df[col] = self.config_dict[col][val_str]  # 若字典對應值為文字則依字典原樣填入
            else:
                # 🛠️ 4. 字典裡也沒有對應關係的，通通填入 -1
                df[col] = -1

        # -------------------------------------------------------------
        # 🛠️ 填入即時統計特徵
        # -------------------------------------------------------------
        if 'recent_packets_in_1s' in self.features: df['recent_packets_in_1s'] = int(recent_packets)
        if 'recent_syn_ratio_in_1s' in self.features: df['recent_syn_ratio_in_1s'] = float(recent_syn_ratio)

        # -------------------------------------------------------------
        # 🛠️ 重新索引與最終結構校準
        # -------------------------------------------------------------
        # 依照訓練模具強制對齊順序
        processed_df = df.reindex(columns=self.features)
        
        # 處理極端無限大值，並將所有未捕獲到的殘留空欄位統一填補為 -1
        processed_df = processed_df.replace([np.inf, -np.inf], np.nan)
        processed_df = processed_df.fillna(-1)
        
        # 轉換為 XGBoost 期待的 2D NumPy Array
        model_input_array = processed_df.values 
        
        return model_input_array, "READY"

preprocessor = LivePreprocessor(SAVED_FEATURES_PATH)


# =========================================================================
# 🚀 絕對傳輸保障發送端
# =========================================================================
def send_to_model_engine(features_matrix):
    try:
        if features_matrix.shape != (1, preprocessor.expected_dim):
            print(f"❌ [傳传输攔截] 維度 {features_matrix.shape} 錯誤，非預期 (1, {preprocessor.expected_dim})！已拋棄。")
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
# ⏱️ 100ms 剛性時間窗到期：強制打包發送與清洗器
# =========================================================================
def flush_window_callback():
    """ 這是當 100ms 倒數計時結束時，自動觸發的發送核心 """
    global current_window_bucket, window_timer, last_known_os_state, last_known_ros_state
    
    with alignment_lock:
        pyshark_payloads = current_window_bucket.get("pyshark_monitor", [])
        
        # 🛡️ 鋼鐵防線一：如果 100ms 到了，快取裡面「根本沒有網路資訊」
        if not pyshark_payloads:
            print("🗑️ [100ms 檢查] 判定真空：此輪完全沒有網路資訊，直接物理刪除，拒絕發送！")
            current_window_bucket.clear()
            window_timer = None
            return 
            
        # 🛡️ 鋼鐵防線二：過濾掉全被填成 -1 且沒有真實流量的偽網路封包
        if len(pyshark_payloads) == 1 and pyshark_payloads[0].get("layers.ip.ip.proto", -1) == -1:
            print("🗑️ [100ms 檢查] 判定偽包：網路特徵皆為 -1.0，直接物理刪除，拒絕發送！")
            current_window_bucket.clear()
            window_timer = None
            return

        os_payloads = current_window_bucket.get("os_monitor", [])
        ros_payloads = current_window_bucket.get("ros_monitor", [])
        
        # [ 1. 更新 OS 快取狀態 ]
        if os_payloads:
            for k, v in os_payloads[0].items():
                if v != -1: last_known_os_state[k] = v

        # [ 2. 更新 ROS2 快取狀態 ]
        if ros_payloads:
            for k, v in ros_payloads[0].items():
                if k == 'publishers_count':
                    last_known_ros_state['publisher_count'] = v
                elif v != -1:
                    last_known_ros_state[k] = v

        # [ 3. 計算 1 秒鐘網路滑動視窗 ]
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

        # [ 4. 組裝特徵列 ]
        flattened_data = {}
        flattened_data.update(last_known_os_state)  
        flattened_data.update(last_known_ros_state) 
        flattened_data.update(pyshark_payloads[0])   

        if 'forward_packets' in preprocessor.features:
            flattened_data['forward_packets'] = int(recent_packets_in_1s)

        # [ 5. 前處理並寄送模型 ]
        df_live = pd.DataFrame([flattened_data])
        X_input, status = preprocessor.process(df_live, recent_packets_in_1s, recent_syn_ratio_in_1s)
        
        if X_input is not None and status == "READY":
            print(f"⏱️ [100ms 視窗到期] ✅ 驗證通過！網路驅動強制送出！(OS={len(os_payloads)>0}, ROS2={len(ros_payloads)>0})")
            executor.submit(send_to_model_engine, X_input)

        # 🔄 清空狀態，迎接下一輪
        current_window_bucket.clear()
        window_timer = None


# =========================================================================
# 🎛️ 新版非同步事件驅動型 Consumer Worker
# =========================================================================
def alignment_consumer_worker():
    global current_window_bucket, window_timer
    print("⏳ [Alignment Worker] 網路事件主驅動 & 100ms 剛性限時對齊管線啟動...")
    
    while True:
        try:
            try:
                data_packet = data_queue.get(timeout=0.01)
            except queue.Empty:
                continue

            source = data_packet.get("data_source")
            raw_payload_list = data_packet.get("payload_list", [])

            if not raw_payload_list:
                data_queue.task_done()
                continue
            
            with alignment_lock:
                if source == "pyshark_monitor":
                    current_window_bucket[source] = raw_payload_list
                    
                    if window_timer is None:
                        window_timer = threading.Timer(0.100, flush_window_callback)
                        window_timer.start()
                        
                elif source in ["os_monitor", "ros_monitor"]:
                    if window_timer is not None:
                        current_window_bucket[source] = raw_payload_list
                    else:
                        pass

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
    print(f"🚀 [6號-Preprocess] 網路事件驅動自適應對齊核心啟動...")
    print(f"📡 監聽埠口: 0.0.0.0:{PROCESS_PORT} ...")
    app.run(host="0.0.0.0", port=PROCESS_PORT, debug=False, threaded=True)
