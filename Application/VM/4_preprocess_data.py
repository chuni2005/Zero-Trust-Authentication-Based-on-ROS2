import os
import requests
import config
import pandas as pd
from flask import Flask, request, jsonify
from live_preprocessing import LivePreprocessor
app = Flask(__name__)

PROCESS_PORT = config.Process_PORT
MODEL_IP = config.MODEL_IP
MODEL_PORT = config.MODEL_PORT
MODEL_URL = f"http://{MODEL_IP}:{MODEL_PORT}/predict"

SAVED_FEATURES_PATH = "usable_features_0512.npy"
if not os.path.exists(SAVED_FEATURES_PATH):
    print(f"❌ 警告：找不到特徵模具 {SAVED_FEATURES_PATH}，請確認檔案路徑！")
preprocessor = LivePreprocessor(SAVED_FEATURES_PATH)
def send_to_model_engine(features: dict):
    print(f"正在將特徵送往 Model Engine ({MODEL_URL})...")
    try:
        response = requests.post(MODEL_URL, json=features, timeout=1.5)
        if response.status_code == 200:
            print(f"已成功接收，回應: {response.json()}")
        else:
            print(f"發送成功但回傳錯誤: {response.status_code}")
    except requests.exceptions.Timeout:
        print("錯誤：連線模組超時！")
    except requests.exceptions.ConnectionError:
        print("錯誤：無法連線至模組。")
    except Exception as e:
        print(f"轉發給模組時發生未預期錯誤: {str(e)}")

@app.route("/process", methods=["POST"])
def receive_raw_data():
    try:
        raw_data = request.get_json()

        if not raw_data or not isinstance(raw_data, list):
            return jsonify({"status": "error", "message": "Invalid data format. Expected a list."}), 400

        raw_snapshot = raw_data[0]
        print(f"\nFlask 成功接收 Monitor 原始快照。Proto: {raw_snapshot.get('net_ip.proto')}, CPU: {raw_snapshot.get('os_cpu_usage')}")
        df_live = pd.DataFrame([raw_snapshot])

        X_input, final_columns = preprocessor.process(df_live)
        print(f"加工成功！輸出形狀 (Shape): {X_input.shape}")

        final_features = X_input.tolist()
        send_to_model_engine(final_features)

        return jsonify({"status": "success", "message": "Preprocess completed and forwarded to 4."}), 200

    except Exception as e:
        print(f"接收/處理 Rpi 數據時崩潰: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    print(f"[6號-Preprocess] 啟動 Flask 中，正在監聽 0.0.0.0:{PROCESS_PORT}/process ...")
    app.run(host="0.0.0.0", port=PROCESS_PORT)