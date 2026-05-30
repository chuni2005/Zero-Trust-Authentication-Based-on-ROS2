# pip install flask requests
from flask import Flask, render_template, request, jsonify
import requests
import config

WEB_IP = config.WEB_IP
RPI1_IP = config.RPI1_IP
PORT = config.AGENT_PORT

app = Flask(__name__)

# 全域即時系統狀態，初始設為無資料 (gray / 0.5)
system_status = {
    "prediction": "No Data (Waiting for Model...)",
    "color": "gray",
    "status_val": 0.5  # 直接用數值傳遞給前端，最精準
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cmd/start', methods=['POST'])
def start_monitor():
    print(f"[Web Console] Issuing START command to Remote Monitor Node ({RPI1_IP})...")
    try:
        resp = requests.post(f"http://{RPI1_IP}:{PORT}/start_ros", json={"cmd": "START"}, timeout=2)
        return jsonify({"msg": "Command sent to RPi 1", "status": resp.status_code})
    except Exception as e:
        print(f"[Web Console Error] Failed to contact monitor agent: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/cmd/attack', methods=['POST'])
def trigger_attack():
    data = request.json or {}
    attack_type = data.get("type", "none")

    print(f"[Web Console] Initiating simulated attack vector [{attack_type}] via Target VM...")
    try:
        resp = requests.post(f"http://{WEB_IP}:{PORT}/launch", json={"type": attack_type}, timeout=2)
        return jsonify({"msg": f"VM attacking with {attack_type}", "status": resp.status_code})
    except Exception as e:
        print(f"[Web Console Error] Attack simulation orchestration failed: {e}")
        return jsonify({"error": str(e)}), 500

# 核心接收端：接收來自 model_engine.py 的推論結果
@app.route('/api/report', methods=['POST'])
def update_ui():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Empty JSON payload"}), 400

        status_signal = data.get("status", "unknown")
        label_code = data.get("prediction", 0)
        
        print(f"[Telemetry Ingestion] Received report from Model Engine -> Status: {status_signal}, Prediction: {label_code}")

        # 1. 只要這 1 秒內有任何一次報告說是攻擊，就強制鎖定為攻擊狀態(1.0)
        if status_signal == "attack" or label_code == 1:
            system_status["prediction"] = "🚨 ATTACK DETECTED !!"
            system_status["color"] = "red"
            system_status["status_val"] = 1.0
        
        # 2. 如果是正常，且目前這 1 秒內還沒被其他攻擊報告鎖定，則設為正常(0.0)
        elif status_signal == "normal":
            if system_status["status_val"] != 1.0:
                system_status["prediction"] = "🟢 SYSTEM NORMAL"
                system_status["color"] = "green"
                system_status["status_val"] = 0.0
        else:
            if system_status["status_val"] != 1.0:
                system_status["prediction"] = f"Unknown state ({status_signal})"
                system_status["color"] = "orange"
                system_status["status_val"] = 0.0

        return jsonify({"status": "UI successfully updated", "current_color": system_status["color"]}), 200

    except Exception as e:
        print(f"[Web Console Crisis] Error processing real-time telemetry report: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 前端輪詢狀態的 API
@app.route('/api/get_status')
def get_status():
    # 複製一份當前累積的狀態準備回傳給網頁
    response_data = dict(system_status)
    
    # 【核心重置邏輯】：回傳給網頁之後，立刻把狀態洗回「沒收到模型回應 (0.5)」
    # 如果未來這 1 秒內模型沒有呼叫 /api/report，下一次前端來抓就會拿到 0.5
    system_status["prediction"] = "No Data (Waiting for Model...)"
    system_status["color"] = "gray"
    system_status["status_val"] = 0.5
        
    return jsonify(response_data)

if __name__ == '__main__':
    print(f"[Web Console] Launching console server platform, tracking host: 0.0.0.0:{config.WEB_PORT} ...")
    app.run(host='0.0.0.0', port=config.WEB_PORT, debug=True)
