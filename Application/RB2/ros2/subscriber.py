import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class MinimalSubscriber(Node):
    def __init__(self):
        super().__init__('monitor_collector')
        self.subscription = self.create_subscription(
            String,
            'monitor/trigger',
            self.listener_callback,
            10)

    def listener_callback(self, msg):
        self.get_logger().info(f'Received: "{msg.data}"')

        if 'Monitor wake up' in msg.data:
            self.get_logger().info('Trigger detected! Starting feature collection...')

def main(args=None):
    rclpy.init(args=args)
    node = MinimalSubscriber()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('KeyboardInterrupt received. Shutting down...')
    finally:
        node.destroy_node()
        rclpy.shutdown()