import os
import csv
import time
import datetime
import requests
import config
import joblib
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# 初始化執行緒池，異步轉發至網頁端
executor = ThreadPoolExecutor(max_workers=4)

MODEL_PORT = config.MODEL_PORT
WEB_IP = config.WEB_IP
WEB_PORT = config.WEB_PORT
WEB_URL = f"http://{WEB_IP}:{WEB_PORT}/api/report"

MODEL_PATH = "xgb_model.pkl"
SAVED_FEATURES_PATH = "feature_names.npy"
CSV_LOG_FILE = "inference_logs.csv"

# 1. 載入 XGBoost 模型
if os.path.exists(MODEL_PATH):
    print(f"[Model Engine] Loading model from: {MODEL_PATH} ...")
    model = joblib.load(MODEL_PATH)
    print("[Model Engine] Model loaded successfully.")
else:
    print(f"[Model Engine] Critical Error: Model file NOT found at {MODEL_PATH}!")
    model = None

# 2. 自動載入特徵名稱模具（供 CSV 紀錄的標題檔頭使用）
if os.path.exists(SAVED_FEATURES_PATH):
    feature_names = np.load(SAVED_FEATURES_PATH, allow_pickle=True).tolist()
    print(f"[Model Engine] 特徵模具載入成功，總計: {len(feature_names)} 維。")
else:
    print(f"⚠️ 警告：未找到 {SAVED_FEATURES_PATH}，CSV 標題將以自動索引代號 (f0, f1...) 替代。")
    feature_names = None


def log_inference_to_csv(features_list, attack_prob, prediction):
    """【除錯核心】將當前推論的特徵數據與分數結果即時 append 寫入 CSV 檔案"""
    try:
        # 攤平成一維清單
        feat_array = np.array(features_list).flatten().tolist()
        
        # 建立 CSV 欄位名稱
        if feature_names and len(feature_names) == len(feat_array):
            cols = feature_names
        else:
            cols = [f"f{i}" for i in range(len(feat_array))]
            
        headers = ["log_time", "predicted_prob", "final_prediction"] + cols
        file_exists = os.path.exists(CSV_LOG_FILE)
        
        # 準備寫入的內容
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        row_data = [current_time, f"{attack_prob:.4f}", prediction] + feat_array
        
        # 以 Append 模式寫入
        with open(CSV_LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(headers)  # 第一次建立檔案時寫入標題
            writer.writerow(row_data)
            
    except Exception as e:
        print(f"[CSV Error] 紀錄推論資料至 CSV 失敗: {str(e)}")


def send_to_web_console(prediction_result: int, attack_prob: float):
    """在背景執行緒池中轉發決策結果與分數給網頁控制台"""
    print(f"[Forwarder] Sending result [{prediction_result}] (Score: {attack_prob*100:.2f}%) to WEB Console...")
    try:
        payload = {
            "status": "attack" if prediction_result == 1 else "normal",
            "label_code": prediction_result,
            "attack_score": attack_prob  # 同步轉發分數給網頁端展示
        }
        response = requests.post(WEB_URL, json=payload, timeout=0.15)
        if response.status_code != 200:
            print(f"[Forwarder] Transmission Completed, abnormal status code: {response.status_code}")
    except requests.exceptions.Timeout:
        print("[Forwarder Error] Connection to WEB Console timed out!")
    except requests.exceptions.ConnectionError:
        print("[Forwarder Error] Connection failed. Please check WEB Console service status!")
    except Exception as e:
        print(f"[Forwarder Error] Unexpected error during forwarding: {str(e)}")


@app.route("/predict", methods=["POST"])
def predict_status():
    if model is None:
        return jsonify({"status": "error", "message": "Model is not loaded on this server."}), 500

    try:
        data = request.get_json()
        if not data or "features" not in data:
            return jsonify({"status": "error", "message": "Missing 'features' in payload."}), 400

        features_list = data["features"]
        
        # 🛡️ 防禦性維度消毒：確保 input_data 絕對是 2D NumPy 陣列形態
        input_data = np.array(features_list)
        if input_data.ndim == 1:
            input_data = input_data.reshape(1, -1)

        # 🚀 1. 改用 predict_proba 提取攻擊機率 (取 NumPy [0, 1] 寫法避免 subscriptable 報錯)
        probabilities = model.predict_proba(input_data)
        attack_prob = float(probabilities[0, 1])
        
        # 2. 以 0.5 為標準判定門檻（除錯期間如需調整，可在此微調）
        predictions = 1 if attack_prob > 0.5 else 0
        
        # 🚀 3. 異步將本次特徵與分數寫入實時 CSV 紀錄檔
        log_inference_to_csv(features_list, attack_prob, predictions)

        # 4. 印出視覺日誌
        status_text = f"🚨 ATTACK DETECTED !! ({attack_prob*100:.2f}%)" if predictions == 1 else f"🟢 NORMAL ({attack_prob*100:.2f}%)"
        print(f"[Model Engine] AI Inference Result -> {status_text}")

        # 5. 異步轉發網頁控制台
        executor.submit(send_to_web_console, predictions, attack_prob)

        # 6. 回傳包含分數的 JSON 給前處理端（process.py）
        return jsonify({
            "status": "success",
            "prediction": predictions,
            "attack_score": attack_prob,  # 🚀 回傳分數
            "message": "Prediction executed, logged to CSV, and queued for web forwarding."
        }), 200

    except Exception as e:
        print(f"[Model Engine Crisis] Pipeline crashed during inference: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print(f"[Model Engine] Starting Flask application server, listening on 0.0.0.0:{MODEL_PORT}/predict ...")
    app.run(host="0.0.0.0", port=MODEL_PORT)
