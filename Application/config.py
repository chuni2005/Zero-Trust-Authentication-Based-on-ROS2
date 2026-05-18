# --- 設備 IP 設定 ---
PC1_IP = "192.168.1.100"  # Frontend
Model_IP = "192.168.1.100"# Model
RPI1_IP = "192.168.1.101" # Trigger ROS2
RPI2_IP = "192.168.1.102" # 收集特徵
VM_IP   = "192.168.1.200" # Attacker

# --- 端口 (Port) 設定 ---
WEB_PORT = 5000           # 1_pc1_main_web.py
MODEL_PORT = 5001         # 4_model_engine.py
AGENT_PORT = 5000         # RPi1, RPi2, VM 上運行的 Flask Port

# --- 攻擊腳本路徑 ---
ATTACK_SCRIPTS_PATH = "./"

# --- 其他全域設定 ---
PACKET_RATE_THRESHOLD = 500