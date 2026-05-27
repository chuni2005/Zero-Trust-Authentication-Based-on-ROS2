# pip install requests
# pip install pandas

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import subprocess

class MonitorCollector(Node):
    def __init__(self):
        super().__init__('monitor_collector')

        # 訂閱來自 RPi 1 的控制通道
        self.subscription = self.create_subscription(
            String,
            'monitor/trigger',
            self.listener_callback,
            10)
        self.subscription  # 防止 Unused variable 警告

        self.get_logger().info('RPi 2 Monitor Collector Node Started.')
        self.get_logger().info('Listening for trigger command from RPi 1...\n')

    def listener_callback(self, msg):
        command_data = msg.data
        self.get_logger().info(f'Received from RPi 1: "{command_data}"')

        # 核心因果：一聽到關鍵字，立刻觸發前處理呼交器
        if 'Monitor wake up' in command_data:
            self.get_logger().info('====== [TRIGGER DETECTED] ======')
            self.get_logger().info('Calling external feature pipeline program...')

            try:
                subprocess.Popen(["python3", "6_feature_pipeline.py"])
                self.get_logger().info('Feature pipeline triggered successfully.')

            except Exception as e:
                self.get_logger().error(f'Failed to call feature pipeline: {str(e)}')

            self.get_logger().info('================================\n')

def main(args=None):
    rclpy.init(args=args)
    node = MonitorCollector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down RPi 2 Collector...')
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()