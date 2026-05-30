import os
import sys
import requests
import config
import numpy as np
import pandas as pd
import warnings
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor  # 引入執行緒池進行非同步轉發

warnings.filterwarnings('ignore')

app = Flask(__name__)

# 💡 優化 1：將 max_workers 提升至 20，確保高頻 200ms 下背景執行緒充足，不堵塞 Flask
executor = ThreadPoolExecutor(max_workers=20)

# 💡 優化 2：初始化全域 Session 物件，啟用 HTTP Keep-Alive，避免高頻重複建立 TCP 連線導致塞車
http_session = requests.Session()

PROCESS_PORT = config.PROCESS_PORT
MODEL_IP = config.MODEL_IP
MODEL_PORT = config.MODEL_PORT
MODEL_URL = f"http://{MODEL_IP}:{MODEL_PORT}/predict"

SAVED_FEATURES_PATH = "usable_feature_0512.npy"


# =========================================================================
# [整合自 live_preprocessing.py] 1. 定義前處理器 (LivePreprocessor)
# =========================================================================
class LivePreprocessor:
    def __init__(self, saved_features_path):
        print(f"🧩 初始化前處理器，載入模具: {saved_features_path}")
        self.features = np.load(saved_features_path, allow_pickle=True).tolist()
        
        # 確保推論時沒有 attack 標籤
        if 'attack' in self.features:
            self.features.remove('attack')
            
    def process(self, raw_packet_df):
        # 任務 1 & 2：強制對齊順序、缺少補 -1、填補空值
        processed_df = raw_packet_df.reindex(columns=self.features, fill_value=-1)
        processed_df = processed_df.replace([np.inf, -np.inf], -1).fillna(-1)
        
        # 任務 3：型態消毒 (強制轉數字)
        processed_df = processed_df.apply(pd.to_numeric, errors='coerce').fillna(-1)
        
        # 任務 4：維度轉換 (轉成 2D Numpy Array)
        model_input_array = processed_df.values 
        
        return model_input_array, processed_df.columns.tolist()


# =========================================================================
# 2. 初始化檢查與服務啟動準備
# =========================================================================
if not os.path.exists(SAVED_FEATURES_PATH):
    print(f"❌ 嚴重錯誤：找不到特徵模具 {SAVED_FEATURES_PATH}，請確認檔案路徑！服務終止。")
    sys.exit(1)

preprocessor = LivePreprocessor(SAVED_FEATURES_PATH)


def send_to_model_engine(features_list: list):
    """在背景執行緒運作的模型轉發任務，避免阻塞 Flask"""
    try:
        payload = {"features": features_list}
        
        # 💡 優化 3：使用 http_session 複用連線，並將 timeout 從 1.5s 縮短到 0.2s (200ms)
        # 既然是 200ms 串流，超時過長的連線直接放棄，才不會拖垮後續的排隊封包
        response = http_session.post(MODEL_URL, json=payload, timeout=0.2)
        
        if response.status_code == 200:
            pass # 抑制高頻成功 Log，維持主控台乾淨乾淨，降低 I/O 阻塞
        else:
            print(f"⚠️ 發送成功但模型端回傳錯誤碼: {response.status_code}")
    except requests.exceptions.Timeout:
        print("❌ [延遲警報] 連線 Model Engine 超時！(模型端推論太慢，封包已自動拋棄)")
    except requests.exceptions.ConnectionError:
        print("❌ 錯誤：無法連線至 Model Engine 模組。")
    except Exception as e:
        print(f"❌ 轉發給模組時發生未預期錯誤: {str(e)}")


# =========================================================================
# 3. Flask API 路由
# =========================================================================
@app.route("/process", methods=["POST"])
def receive_raw_data():
    try:
        raw_data = request.get_json()

        if not raw_data or not isinstance(raw_data, list):
            return jsonify({"status": "error", "message": "Invalid data format. Expected a list."}), 400

        # 為了防止高頻下終端機 I/O 成為瓶頸，僅在有大量批次或異常時詳細列印，平常簡短輸出
        df_live = pd.DataFrame(raw_data)

        # 呼叫整合進來的預處理器
        X_input, final_columns = preprocessor.process(df_live)

        final_features = X_input.tolist()
        
        # 非同步優化：丟進加大後的執行緒池，立刻釋放 Flask 主執行緒
        executor.submit(send_to_model_engine, final_features)

        return jsonify({
            "status": "success", 
            "message": "Processed successfully"
        }), 200

    except Exception as e:
        print(f"💥 接收/處理 Rpi 數據時崩潰: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print(f"[6號-Preprocess] 啟動高速版 Flask 中，正在監聽 0.0.0.0:{PROCESS_PORT}/process ...")
    # 💡 優化 4：若要徹底解鎖效能，生產環境建議關閉 debug，或者使用 gunicorn，這裡先保持原生啟動
    app.run(host="0.0.0.0", port=PROCESS_PORT, debug=False)
