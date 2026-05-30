#pip install flask

from flask import Flask, request, jsonify
import subprocess
import os
import config

app = Flask(__name__)

ATTACK_DIR = config.ATTACK_SCRIPTS_PATH
VM_IP = config.VM_IP
RPI2_IP = config.RPI2_IP

@app.route('/launch', methods=['POST'])
def launch_attack():
    data = request.json
    attack_type = data.get("type", "none")
    scripts = {
        "syn_flood": "NMAP_SYN_Flood.py",
        "nmap_scan": "NMAP_Scanning.py",
        "ros2_crash": "ROS2_Node_Crashing.py",
        "ros2_recon": "ROS2_Reconnaissance.py",
        "ros2_reflection": "ROS2_Reflection.py",
        "metasploit_syn": "Metasploit_SYN_Flood.py"
    }
    script_name = scripts.get(attack_type)

    if not script_name:
        return jsonify({"status": "error", "message": f"Unknown attack type: {attack_type}"}), 400

    script_path = os.path.join(ATTACK_DIR, script_name)

    if not os.path.exists(script_path):
        return jsonify({"status": "error", "message": f"File {script_name} not found"}), 404

    try:
        subprocess.Popen(["sudo", "python3", script_path,
                          "-s", VM_IP,
                          "-t", RPI2_IP
                          ])
        print(f" [VM] Attack Launched: {script_name}")
        return jsonify({
            "status": "success",
            "message": f"Launched {script_name} from VM",
            "type": attack_type
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def check_port(port=55553):
    try:
        result = subprocess.run(
            ["ss", "-tulnp"],
            capture_output=True,
            text=True
        )
        if str(port) in result.stdout:
            print(f"[INFO] Port {port} is LISTENING")
        else:
            print(f"[ERROR] Port {port} is NOT found, starting msfrpcd...")
    except Exception as e:
        print(f"[ERROR] Port check failed: {e}")

if __name__ == '__main__':
    check_port()
    app.run(host='0.0.0.0', port=config.AGENT_PORT, debug=True)
