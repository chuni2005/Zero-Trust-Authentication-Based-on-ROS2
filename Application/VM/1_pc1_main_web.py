#pip install flask requests

from flask import Flask, render_template, request, jsonify
import requests
import config

VM_IP = config.VM_IP
RPI1_IP = config.RPI1_IP

app = Flask(__name__)

PORT = config.AGENT_PORT

system_status = {
    "prediction": "Waiting for data...",
    "color": "gray",
    "last_features": "None"
}

@app.route('/')
def index():
    return render_template('index.html')
@app.route('/cmd/start', methods=['POST'])
def start_monitor():
    try:
        resp = requests.post(f"http://{RPI1_IP}:{PORT}/start_ros", json={"cmd": "START"}, timeout=2)
        return jsonify({"msg": "Command sent to RPi 1", "status": resp.status_code})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cmd/attack', methods=['POST'])
def trigger_attack():
    data = request.json
    attack_type = data.get("type", "none")

    print(f"Executing {attack_type} on VM...")
    try:
        resp = requests.post(f"http://{VM_IP}:{PORT}/launch", json={"type": attack_type}, timeout=2)
        return jsonify({"msg": f"VM attacking with {attack_type}", "status": resp.status_code})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/update_web_status', methods=['POST'])
def update_ui():
    data = request.json
    result_text = data["result"]
    system_status["prediction"] = result_text

    if "normal" in result_text.lower() or "0" in result_text:
        system_status["color"] = "#2ecc71"  # 綠色
    else:
        system_status["color"] = "#e74c3c"  # 紅色

    return jsonify({"status": "UI updated"})

@app.route('/api/get_status')
def get_status():
    return jsonify(system_status)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config.WEB_PORT, debug=True)
