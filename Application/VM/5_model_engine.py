import os
import requests
import config
import joblib
from flask import Flask, request, jsonify

app = Flask(__name__)

MODEL_PORT = config.MODEL_PORT
WEB_IP = config.WEB_IP
WEB_PORT = config.WEB_PORT
WEB_URL = f"http://{WEB_IP}:{WEB_PORT}/api/report"

MODEL_PATH = "xgboost_model.joblib"
#MODEL_PATH = "isolation_forest_model.joblib"
if os.path.exists(MODEL_PATH):
    print(f"正在載入模型: {MODEL_PATH} ...")
    model = joblib.load(MODEL_PATH)
    print("模型載入成功")
else:
    print(f"錯誤：找不到模型檔案 {MODEL_PATH}！")
    model = None

def send_to_web_console(prediction_result: int):
    print(f"正在將決策結果 [{prediction_result}] 送往 WEB ({WEB_URL})...")
    try:
        payload = {
            "status": "attack" if prediction_result == 1 else "normal",
            "label_code": prediction_result
        }
        response = requests.post(WEB_URL, json=payload, timeout=1.0)

        if response.status_code == 200:
            print(f"WEB 已成功接收響應。")
        else:
            print(f"發送成功，但 WEB 號回傳錯誤碼: {response.status_code}")
    except requests.exceptions.Timeout:
        print("錯誤：連線 WEB 超時！")
    except requests.exceptions.ConnectionError:
        print("錯誤：無法連線至 WEB")
    except Exception as e:
        print(f"轉發時發生未預期錯誤: {str(e)}")

@app.route("/predict", methods=["POST"])
def predict_status():
    if model is None:
        return jsonify({"status": "error", "message": "Model is not loaded."}), 500

    try:
        data = request.get_json()
        if not data or "features" not in data:
            return jsonify({"status": "error", "message": "Missing 'features' in payload."}), 400

        features_list = data["features"]
        print(f"\n成功接獲前處理特徵，特徵維度: {len(features_list[0])}")

        predictions = model.predict(features_list)

        final_result = int(predictions[0])
        status_text = "🚨 ATTACK DETECTED !!" if final_result == 1 else "🟢 NORMAL"
        print(f"AI 決策模型推論結果 -> {status_text}")

        send_to_web_console(final_result)

        return jsonify({
            "status": "success",
            "prediction": final_result,
            "message": "Prediction done and sent to 1."
        }), 200

    except Exception as e:
        print(f"推論或轉發流程崩潰: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    print(f"啟動 Flask 中，正在監聽 0.0.0.0:{MODEL_PORT}/predict ...")
    app.run(host="0.0.0.0", port=MODEL_PORT)
