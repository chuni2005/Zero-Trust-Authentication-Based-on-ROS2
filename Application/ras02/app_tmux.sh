tmux new-session -d -s ZTVFROS2 -n main
tmux send-keys -t ZTVFROS2:0.0 'sudo python3 os_monitor.py' C-m

tmux split-window -h -t ZTVFROS2:0
tmux send-keys -t ZTVFROS2:0.1 'sudo python3 pyshark_monitor.py' C-m

tmux split-window -h -t ZTVFROS2:0.1
tmux send-keys -t ZTVFROS2:0.2 'python3 ros_monitor.py' C-m

tmux split-window -h -t ZTVFROS2:0.2
tmux send-keys -t ZTVFROS2:0.3 '
cd ../ros_workspace/src/
colcon build
source install/setup.bash
ros2 run application subscriber
' C-m
tmux attach -t ZTVFROS2