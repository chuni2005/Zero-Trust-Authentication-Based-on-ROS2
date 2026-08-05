tmux new-session -d -s ZTVFROS2 -n main
tmux send-keys -t ZTVFROS2:0.0 'cd monitor/OS/; sudo python3 linux_monitor.py' C-m

tmux split-window -h -t ZTVFROS2:0
tmux send-keys -t ZTVFROS2:0.1 'cd monitor/Tshark/; sudo tshark -i lo -w temp_capture.pcapng' C-m

tmux split-window -h -t ZTVFROS2:0.1
tmux send-keys -t ZTVFROS2:0.2 'cd monitor/ROSBags/; python3 ros2_monitor.py' C-m

tmux split-window -h -t ZTVFROS2:0.2
tmux send-keys -t ZTVFROS2:0.3 '
cd ros_workspace/src/
colcon build
source install/setup.bash
export ROS_MASTER_URI=http://192.168.0.108:11311
export ROS_HOSTNAME=192.168.0.101
ros2 run my_pubsub publisher
' C-m
tmux attach -t ZTVFROS2

#sudo ip -6 addr add 2002:c0a8:65::/16 dev wlan0