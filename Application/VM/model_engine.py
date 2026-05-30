import os
import requests
import config
import joblib
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# Initialize thread pool to handle high-frequency forwarding asynchronously
executor = ThreadPoolExecutor(max_workers=4)

MODEL_PORT = config.MODEL_PORT
WEB_IP = config.WEB_IP
WEB_PORT = config.WEB_PORT
WEB_URL = f"http://{WEB_IP}:{WEB_PORT}/api/report"

MODEL_PATH = "xgboost_model.joblib"

if os.path.exists(MODEL_PATH):
    print(f"[Model Engine] Loading model from: {MODEL_PATH} ...")
    model = joblib.load(MODEL_PATH)
    print("[Model Engine] Model loaded successfully.")
else:
    print(f"[Model Engine] Critical Error: Model file NOT found at {MODEL_PATH}!")
    model = None

def send_to_web_console(prediction_result: int):
    """Executes inside the background thread pool to prevent blocking the Flask main thread"""
    print(f"[Forwarder] Sending decision result [{prediction_result}] to WEB Console ({WEB_URL})...")
    try:
        payload = {
            "status": "attack" if prediction_result == 1 else "normal",
            "label_code": prediction_result
        }
        # Short timeout enforced due to the 200ms processing cycle requirement
        response = requests.post(WEB_URL, json=payload, timeout=0.15)

        if response.status_code == 200:
            pass # Suppressed high-frequency successful logs to maintain clean console
        else:
            print(f"[Forwarder] Transmission completed but received abnormal status code: {response.status_code}")
    except requests.exceptions.Timeout:
        print("[Forwarder Error] Connection to WEB Console timed out! (Web service might be too slow)")
    except requests.exceptions.ConnectionError:
        print("[Forwarder Error] Connection failed. Please check if the WEB Console service is running!")
    except Exception as e:
        print(f"[Forwarder Error] Unexpected error during console forwarding: {str(e)}")

@app.route("/predict", methods=["POST"])
def predict_status():
    if model is None:
        return jsonify({"status": "error", "message": "Model is not loaded on this server."}), 500

    try:
        data = request.get_json()
        
        # Validation for the expected aligned key from process_data.py
        if not data or "features" not in data:
            return jsonify({"status": "error", "message": "Missing 'features' in payload."}), 400

        features_list = data["features"]
        print(f"\n[Model Engine] Features received. Batch dimension shape: {len(features_list)}x{len(features_list[0])}")

        # Run AI inference
        predictions = model.predict(features_list)

        # Extraction of the core prediction result
        final_result = int(predictions[0])
        status_text = "🚨 ATTACK DETECTED !!" if final_result == 1 else "🟢 NORMAL"
        print(f"[Model Engine] AI Decision System Inference -> {status_text}")

        # Non-blocking async dispatch to the web interface via the thread pool
        executor.submit(send_to_web_console, final_result)

        return jsonify({
            "status": "success",
            "prediction": final_result,
            "message": "Prediction executed and queued for web forwarding."
        }), 200

    except Exception as e:
        print(f"[Model Engine Crisis] Pipeline crashed during inference/forwarding: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    print(f"[Model Engine] Starting Flask application server, listening on 0.0.0.0:{MODEL_PORT}/predict ...")
    app.run(host="0.0.0.0", port=MODEL_PORT)
