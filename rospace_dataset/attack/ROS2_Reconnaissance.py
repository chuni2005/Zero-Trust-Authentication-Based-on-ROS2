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


# 中斷處理
def signal_handler(sig, frame):
    print(color("\nCtrl+C pressed, exiting", fg="red"))
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


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
## 攻擊次數
parser.add_argument(
    "-c",
    "--count",
    metavar="NUMBER",
    type=int,
    required=False,
    help="the number of launches for each attack that "
    "doens't requires a RESET. Defaults to 1000.",
    default=1000,
)
## 需要重置的攻擊次數
parser.add_argument(
    "-cr",
    "--count-reset",
    metavar="NUMBER",
    type=int,
    required=False,
    help="the number of launches for each attack that requires a RESET. Defaults to the same value as count.",
    default=500,
)
## 埠掃描攻擊次數
parser.add_argument(
    "-cp",
    "--count-portscan",
    metavar="NUMBER",
    type=int,
    required=False,
    help="the number of launches for the portscan attack. Defaults to the same value as count.",
    default=500,
)
## 攻擊總輪數
parser.add_argument(
    "-C",
    "--total-count",
    metavar="NUMBER",
    type=int,
    required=False,
    help="the number of complete rounds during which all attacks are performed. Defaults to 1.",
    default=1,
)
## 指令延遲時間
parser.add_argument(
    "-d",
    "--delay",
    metavar="SECONDS",
    type=int,
    required=False,
    help="the delay in seconds before an attack is attempted "
    "after a previous attack (only used when --count > 1).\n"
    "Defaults to 0",
    default=0,
)
## 重置攻擊（同組間隔）之間的延遲時間
parser.add_argument(
    "-dr",
    "--delay-reset",
    metavar="SECONDS",
    type=int,
    required=False,
    help="the delay in seconds before an attack is attempted "
    "after a previous attack that required a RESET.\n"
    "Defaults to 90",
    default=90,
)
## 攻擊組合之間的延遲時間
parser.add_argument(
    "-r",
    "--starting-delay",
    metavar="SECONDS",
    type=int,
    required=False,
    help="the delay in seconds between groups of attacks." " Defaults to 0",
    default=0,
)
## SYN flood attack 持續時間
parser.add_argument(
    "-l",
    "--flood-duration",
    metavar="SECONDS",
    type=int,
    required=False,
    help="the duration in seconds of the SYN flood attack "
    "performed by Metasploit and RA flood attack performed by NMAP."
    "\nDefaults to 60",
    default=60,
)
## 目標的port
parser.add_argument(
    "-p",
    "--reset-port",
    metavar="NUMBER",
    type=int,
    required=False,
    default=65535,
    help="the port where to send the reset commands to ask the "
    "target to prepare for a new round of tests cleanly.\n"
    "Defaults to 65535",
)
## 網路錯誤時的等待時間
parser.add_argument(
    "-T",
    "--timeout",
    metavar="SECONDS",
    type=int,
    required=False,
    default=20,
    help="number of seconds to wait if a network error occurs before retrying.\n"
    "Defaults to 20",
)
## 網路錯誤時的那筆攻擊重發次數
parser.add_argument(
    "-R",
    "--retry-count",
    metavar="NUMBER",
    type=int,
    required=False,
    default=5,
    help="number of attempts to retry an attack if a network "
    "error occurs before passing to the next attack.\n"
    "Defaults to 5",
)
## log紀錄位置
parser.add_argument(
    "-f",
    "--log-file",
    metavar="PATH",
    type=str,
    help="the file to which timestamps of attacks start and "
    'endings will be saved.\nDefaults to "attacks_log.csv".\n'
    "File will be created if it not exist, "
    "and overwritten if it exist.",
    required=False,
    default="attacks_log.csv",
)
## 自訂 msfclient 密碼
parser.add_argument(
    "-P",
    "--msf-password",
    metavar="PASSWORD",
    type=str,
    help="the password to connect to the metasploit daemon.\n" 'Defaults to "pentest"',
    required=False,
    default="pentest",
)
## 只計算攻擊時間估算不執行攻擊
parser.add_argument(
    "-n",
    "--not-execute",
    action="store_true",
    default=False,
    help="doesn't perform any attack, but calculate only the "
    "duration estimate based on run counts and delays",
)

args = parser.parse_args()
dst = args.target
src = args.source
port = args.reset_port
# 參數輸入判斷，違反規則則使用預設值
_delay = 0
if args.count > 1:
    _delay = args.delay

if args.count_reset < 0:
    args.count_reset = args.count

if args.count_portscan < 0:
    args.count_portscan = args.count

_delay_reset = 0
if args.delay_reset > 0:
    _delay_reset = args.delay_reset

## Nmap 埠掃描手動預估時間（秒）
scanning_manual_estimate = 120
## 估算使用 Nmap 探測 (discovery) 的執行時間：發送 ICMP Echo 封包（類似 ping 指令）至所有子網subnet（同個ip區段）的主機若回應則表示主機存活
nmap_discovery = (3 + args.delay) * args.count
## 估算 Nmap 掃描 port 的時間：使用 TCP null scan、TCP ACK scan、UDP scan，藉由傳輸不同的方式，掃描目標主機對應開放的 port
nmap_port_scaning = (scanning_manual_estimate + args.delay) * args.count_portscan
## 估算 ROS2 偵察 (reconnaissance) 的時間：發送偵察封包至目標，每次重複 count 次，每次間隔 delay 秒
ros2_recon = (3 + args.delay) * args.count
## 估算 ROS2 節點當機 (node crashing) 的時間
ros2_node_crash = (3 + _delay_reset) * args.count_reset
## 估算 ROS2 反射攻擊 (reflection) 的時間：利用目標節點反射大量封包，需要重置狀態，每次間隔 delay_reset 秒
ros2_reflection = (3 + _delay_reset) * args.count_reset
## 估算 Nmap 洪水攻擊 (flooding) 的時間
nmap_flooding = (args.flood_duration + _delay_reset) * args.count_reset
## 估算 Metasploit 洪水攻擊 (flooding) 的時間
metasploit_flooding = 0

## 總攻擊時間估算
time_estimate = (
    nmap_discovery
    + nmap_port_scaning
    + ros2_recon
    + ros2_node_crash
    + ros2_reflection
    + nmap_flooding
    + metasploit_flooding
) * args.total_count

# 如果只要求時間估算則印出估算結果後結束程式
if args.not_execute:
    print(
        color(
            f"\nEstimated campaign duration: {timedelta(seconds=time_estimate)}",
            fg="yellow",
        )
    )
    print("divided in (in order of execution):")
    print(
        f"  NMAP DISCOVERY\t{args.count} times with {_delay} seconds delay\t-> {timedelta(seconds=nmap_discovery)}"
    )
    print(
        f"  NMAP PORT SCANNING\t{args.count_portscan} times with {_delay} seconds delay\t-> {timedelta(seconds=nmap_port_scaning)}"
    )
    print(
        f"  ROS2 RECONNAISSANCE\t{args.count} times with {_delay} seconds delay\t-> {timedelta(seconds=ros2_recon)}"
    )
    print(
        f"  ROS2 NODE CRASHING\t{args.count_reset} times with {_delay_reset} seconds delay\t-> {timedelta(seconds=ros2_node_crash)}"
    )
    print(
        f"  ROS2 REFLECTION\t{args.count_reset} times with {_delay_reset} seconds delay\t-> {timedelta(seconds=ros2_reflection)}"
    )
    print(
        f"  NMAP FLOODING\t\t{args.count_reset} times with {_delay_reset} seconds delay\t-> {timedelta(seconds=nmap_flooding)}"
    )
    print(
        f"  METASPLOIT FLOODING\t{args.count_reset} times with {_delay_reset} seconds delay\t-> {timedelta(seconds=metasploit_flooding)}"
    )
    print(f"  with a flooding duration of {args.flood_duration} seconds")
    print(
        color(
            "just a duration estimate was requested, exiting without performing any attack",
            fg="yellow",
        )
    )
    sys.exit(0)
else:
    if not (args.target and args.source):
        parser.error(
            "you must specify both target and source IP addresses when not passing -n|--not-execute option"
        )

####################正式攻擊區塊####################
print(
    color(
        f"\nEstimated campaign duration: {timedelta(seconds=time_estimate)}",
        fg="yellow",
    )
)

##建立 socket：AF_INET->IPv4，SOCK_DGRAM->UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
## 打開 log 檔案並寫入
log = open(args.log_file, "w+")
log.write("timestamp,attack,event\n")
log.write(f"{dt.now().strftime('%a %b %d %H:%M:%S CEST 2023')},campaign,start\n")


def convert_ip(ipv4):
    if ipv4 == "127.0.0.1":
        return "::1"
    return "2002:{:02x}{:02x}:{:02x}{:02x}::".format(*map(int, ipv4.split(".")))


def send_wrapper(msg):
    handle_network_errors(lambda: sock.sendto(msg.encode(), (dst, args.reset_port)))


def start_attack(atk_id):
    global attack_id
    attack_id = atk_id
    print(f"starting {attack_id}")
    log.write(f"{dt.now().strftime('%a %b %d %H:%M:%S CEST 2023')},{attack_id},start\n")


def end_attack():
    log.write(f"{dt.now().strftime('%a %b %d %H:%M:%S CEST 2023')},{attack_id},end\n")
    print(f"{attack_id} ended")


def end_campaign():
    send_wrapper("END")
    # log.write(f"{dt.now().strftime('%a %b %d %H:%M:%S CEST 2023')},{attack_id},end\n")
    log.write(f"{dt.now().strftime('%a %b %d %H:%M:%S CEST 2023')},campaign,end\n")
    print(f"campaign ended")


def ensure_madness_writes():
    send_wrapper("FLUSH")
    log.write(
        f"{dt.now().strftime('%a %b %d %H:%M:%S CEST 2023')},restart madness and flush output signal,sent\n"
    )
    print(f"sent signal FLUSH to restart madness experiment and flush output")


def launch(name, command, reset=False, count=None):
    sleep(args.starting_delay)
    delay = _delay_reset if reset else _delay
    _count = args.count_reset if reset else args.count
    _count = _count if count is None else count
    for _ in range(_count):
        sleep(delay)
        start_attack(name)
        handle_network_errors(command)
        end_attack()
        if reset:
            send_wrapper("RESET")
    if _count > 0:
        ensure_madness_writes()


def launch_portscan():
    sleep(args.starting_delay)
    for _ in range(args.count_portscan):
        sleep(_delay)
        start_attack("nmap port scanning")
        command = f"nmap --privileged -sNV {dst} --exclude-ports {args.reset_port}"  # TCP null scan & version detection
        handle_network_errors(lambda: run(split(command)))
        command = f"nmap --privileged -sA {dst} --exclude-ports {args.reset_port}"  # TCP ACK scann
        handle_network_errors(lambda: run(split(command)))
        command = f"nmap --privileged -sU {dst} -p 7400-7500"  # UDP scan
        handle_network_errors(lambda: run(split(command)))
        end_attack()
    if args.count_portscan > 0:
        ensure_madness_writes()


def handle_network_errors(command):
    done = False
    retry = args.retry_count
    while not done and retry > 0:
        try:
            command()
            done = True
        except OSError as e:
            print(e)
            log.write(
                f"{dt.now().strftime('%a %b %d %H:%M:%S CEST 2023')},network error,{str(e)}\n"
            )
            done = False
            retry -= 1
            sleep(args.timeout)



try:
    for _ in range(args.total_count):

        try:
            # ================================
            # ROS2 Reconnaissance (偵察)
            # ================================
            # 使用 sr1() 發送封包，透過 get_footprint() 收集 ROS2 節點資訊。
            # retry=0 表示不重試，timeout=10 表示等待 10 秒。
            launch(
                "ros2 reconnaissance",
                lambda: sr1(get_footprint(src, dst), retry=0, timeout=10),
            )

        except PermissionError:
            # ================================
            # 權限不足錯誤處理
            # ================================
            # 如果沒有 root 權限，無法綁定網路介面或使用保留埠。
            print(
                color(
                    "unable to perform attacks operation due to lack of permissions!",
                    fg="red",
                ),
                file=sys.stderr,
            )
            print(
                "This script needs permission to bind to network interfaces to capture"
                " packets and to bind to reserved ports."
            )
            print("One way to achieve this is by running it as root (with sudo).")

    # ================================
    # 結束整個攻擊流程
    # ================================
    end_campaign()

finally:
    # ================================
    # 資源釋放
    # ================================
    sock.close()  # 關閉 socket
    log.close()   # 關閉 log 檔案
