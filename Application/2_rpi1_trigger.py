#pip install flask

from flask import Flask, request, jsonify
import subprocess
import config

app = Flask(__name__)

ROS2_COMMAND = "source /opt/ros/humble/setup.bash && source ~/ros2_ws/install/setup.bash && ros2 run my_pubsub publisher"

@app.route('/start_ros', methods=['POST'])
def start_ros_node():
    """
    接收來自 PC1 的觸發指令，啟動 ROS2 Publisher 節點
    """
    data = request.json
    cmd_type = data.get("cmd", "none")

    if cmd_type == "START":
        try:
            # 使用 Popen 非同步執行，避免 ROS2 節點卡住 Flask 伺服器
            # shell=True 允許執行 source 等 shell 內建指令
            process = subprocess.Popen(
                ROS2_COMMAND,
                shell=True,
                executable="/bin/bash",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            print(f" [RPi1] ROS2 Node 'publisher' triggered via 'my_pubsub' package.")
            return jsonify({
                "status": "success",
                "message": "ROS2 Publisher is now running on RPi1",
                "package": "my_pubsub",
                "node": "publisher"
            })
        except Exception as e:
            print(f" [RPi1] Error: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "error", "message": "Invalid command type"}), 400

@app.route('/status', methods=['GET'])
def get_status():
    """ 讓 PC1 可以檢查 RPi1 是否在線 """
    return jsonify({"status": "RPi1 is online", "device": "Trigger Node"})

if __name__ == '__main__':
    # 監聽 0.0.0.0，通訊埠使用 config.py 裡的定義
    app.run(host='0.0.0.0', port=config.AGENT_PORT, debug=True)