import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from flask import Flask, request, jsonify
import threading
from application import config

app = Flask(__name__)
node = None
publisher = None

@app.route('/start_ros', methods=['POST'])
def start_ros_node():

    data = request.json
    cmd_type = data.get("cmd", "none")

    if cmd_type == "START":
        try:
            msg = String()
            msg.data = "Triggered packet from HTTP"
            publisher.publish(msg)
            print(" [RPi1] pkg is already send via ROS2 Publisher.")
            return jsonify({
                "status": "success",
                "message": "ROS2 Publisher sent packet",
                "topic": "application_topic",
                "data": msg.data
            })
        except Exception as e:
            print(f" [RPi1] Error: {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "error", "message": "Invalid command type"}), 400

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({"status": "RPi1 is online", "device": "Trigger Node"})

def main():
    global node, publisher
    rclpy.init()
    node = Node('http_trigger_node')
    publisher = node.create_publisher(String, 'application_topic', 10)

    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=config.AGENT_PORT, debug=False)).start()

    rclpy.spin(node)

if __name__ == '__main__':
    main()
