#!/usr/bin/env python3
from ROS.attacks import *
import argparse
import socket
from datetime import datetime as dt
from datetime import timedelta
from subprocess import run
from shlex import split
from time import sleep
import signal
import threading

#parser 輸入參數設定
parser = argparse.ArgumentParser(
    description="Launches attacks on SPaCe. " "May need root privileges to run"
)
## 攻擊目標
parser.add_argument(
    "-t",
    "--target",         # 短選項 -t 與長選項 --target
    metavar="ADDRESS",  # 在 --help 中顯示的參數名稱
    type=validate_ip,   # 輸入值會先經過 validate_ip 函式檢查
    help="the IP address of the target of the attacks. "
    "It's required unless -n|--not-execute is passed.",
)
## 攻擊來源
parser.add_argument(
    "-s",
    "--source",
    metavar="ADDRESS",
    type=validate_ip,
    help="the IP address to be used as the source address of "
    "sent packets. It's required unless -n|--not-execute is passed.",
)
args = parser.parse_args()

def kill_process(proc):
    print("\n[*] Time is over.")
    proc.terminate()

try:
        # ================================
        # NMAP Discovery (作業系統偵測)
        # ================================
        # --privileged   ：指定以「特權模式」執行，通常需要 root 權限，讓 Nmap 可以使用原始封包功能。
        # -O             ：啟用 OS detection（作業系統偵測），Nmap 會嘗試判斷目標主機的作業系統。
        # --osscan-guess ：如果 Nmap 無法精確判斷 OS，會嘗試「猜測」最接近的結果。
        # {dst}          ：目標主機的 IP 或網域名稱，透過變數插入。
        # --exclude-ports {args.reset_port} ：排除特定埠口，不讓 Nmap 掃描這些埠。
        # args.reset_port：程式中由使用者輸入的參數，代表要排除的埠號。
    command = f"nmap --privileged -O --osscan-guess {args.target}"# aggressively tries to guess OS
    proc = subprocess.Popen(split(command))
    timer = threading.Timer(seconds, kill_process, [proc])
    timer.start()
    proc.wait()
    timer.cancel()
    
except KeyboardInterrupt:
    print("\n[!] 測試已被使用者中斷。")
except Exception as e:
    print(f"\n[-] 發生非預期錯誤: {e}")
