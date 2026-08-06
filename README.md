# ZTABROS2 使用指南
![img](./README/struc.png)

## 0. Environment
請確保環境已在各自節點下安裝：
- ros2 (全部)
- tmux (ras01、ras02)
- msfrpcd (vm)
- mobaXterm (vm 選用)

### 安裝環境 ros2 指南
個人本地WSL原本是22.04，而 ROS2_Jazzy 只支援24.04，因此改用對應的 ROS2_Humble:

1. 請一定要先更新：`sudo apt update && sudo apt install curl gnupg lsb-release -y`
2. 加入 ROS 套件來源與金鑰：`sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg` & `echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null`
3. 安裝 ROS 2 Humble 桌面版：`sudo apt install ros-humble-desktop -y`
4. 設定環境變數：`echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc` & `source ~/.bashrc`
5. 執行目錄於 ros_workspace，創建 src：`mkdir src` & `cd src`
6. 在目前 src 資料夾中，自動創建 ros2 框架：`ros2 pkg create --build-type ament_python my_pubsub`

    目錄和檔案將會自動加入：
    ```
    ros_workspace/
    └── src/
        └── my_pubsub/
            ├── setup.py
            └── my_pubsub/
                ├── __init__.py
                ├── publisher.py
                └── subscriber.py
    ```
7. 請將指定的 `setup.py`、`publisher.py`、`subscriber.py` 根據需求替代或刪除
8. 編譯：`sudo apt install python3-colcon-common-extensions -y colcon build` & `colcon build`
9. 載入設定檔：`source install/setup.bash`
10. 啟動 publisher：`ros2 run my_pubsub publisher`
11. 啟動 subscriber：`ros2 run my_pubsub subscriber`

### 也許你會用到的 tmux 快捷鍵
- Ctrl + D: 關閉當前分頁
- Ctrl + B + O: 切換分頁

## 1. Data Collection
raspberry01 作為 ros2 publisher 發送訊息至 raspberrry01，raspberry02 作為 ros2 subscriber 接收來自 raspberrry01 的訊息，vm 作為 attacker 攻擊 subscriber。

### raspberry01
> 按照[建構 ros2 環境](#安裝環境-ros2-指南)的步驟執行，第七點將以 `./Data Collection/publisher/ros2` 內的檔案替換，並將 `./Data Collection/publisher/tmux_start.sh` 和 `./Data Collection/publisher/monitor` 放於同樣的相對路徑下。

1. 直接執行：`source ./Data Collection/publisher/tmux_start.sh` 以啟動 monitors 和 publisher
2. tmux 操作請見[也許你會用到的 tmux 快捷鍵](#也許你會用到的-tmux-快捷鍵)

### raspberry02
> 按照[建構 ros2 環境](#安裝環境-ros2-指南)的步驟執行，第七點將以 `./Data Collection/subscriber/ros2` 內的檔案替換，並將 `./Data Collection/subscriber/tmux_start.sh` 和 `./Data Collection/subscriber/monitor` 放於同樣的相對路徑下。

1. 直接執行：`source ./Data Collection/subscriber/tmux_start.sh` 以啟動 monitors 和 subscriber
2. tmux 操作請見[也許你會用到的 tmux 快捷鍵](#也許你會用到的-tmux-快捷鍵)

### virtual machine
> 加入 `./Data Collection/attacker` 的所有檔案。

1. 啟動 msf 後台：`msfrpcd -P pentest -n -f`
2. 執行攻擊：`sudo python3 attack.py -s {SOURCE_IP} -t {SUBSCRIBER_IP} -c 2 -cr 2 -cp 2 -l 5` (可自行更改參數)
3. 待到攻擊結束，即可將所有節點的程式中斷

## 2. Data Preprocessing

1. 將 subscriber 中 monitors 所產生的檔案 `OS_monitor.csv`、`ros2_monitor.csv`、`temp_capture.pcapng` 複製至此
2. 將 attacker 攻擊後所產生的 `attack.log` 複製至此
3. 依照 `./Model Training/main.ipynb` 流程執行 (記得修改路徑)
    - `./Model Training/rospace_dataset/1_processing/custom_pcapng2csv.py`: 將 `temp_capture.pcapng` 攤平成 csv 格式
    - `./Model Training/rospace_dataset/1_processing/csv_merging_parallel.py`: 將剛剛轉換的 csv 與 `OS_monitor.csv`、`ros2_monitor.csv` 合併並依據 `attack.log` 進行 label
    - `./Model Training/rospace_dataset/2_labeling/label`: 在資料量過大，buffer 不夠時，在 merge 後使用

4. 執行 `./Model Training/rospace_dataset/3_complete_dataset/complete_dataset_composition.ipynb`: 檢查數據、數據清理
5. 執行 `./Model Training/rospace_dataset/4_reduced_and_noperiodicity_dataset/reduced_dataset_composition.ipynb`: 刪除不重要的欄位
6. 執行 `./Model Training/rospace_dataset/4_reduced_and_noperiodicity_dataset/no_periodicity_dataset.ipynb`: 隨機裁切連續時間序並重塑時間軸以消除週期性

## 3. Model Training
執行 `./Model Training/rospace_dataset/5_usage_notes/usage_note_A_detection_shuffled.ipynb`: 訓練模型並輸出 npy 和 pkl 檔案

## 4. Application
> **請一定要先將 `./Application/config.txt` 設定好，各個節點都需要。**

### raspberry01
> 按照[建構 ros2 環境](#安裝環境-ros2-指南)的步驟執行，第七點將以 `./Application/ras01/ros2` 內的檔案替換，**並將 `./Application/config.py` 放入與 `./Application/ras01/ros2/publisher.py 同層的地方`**。

1. 按照[建構 ros2 環境](#安裝環境-ros2-指南)執行：`ros2 run Application publisher` 以啟動

### raspberry02
> 按照[建構 ros2 環境](#安裝環境-ros2-指南)的步驟執行，第七點將以 `./Application/ras02/ros2` 內的檔案替換，並將 `./Application/ras02/app_tmux.sh`、`./Application/ras02/.*monitor.py` 和 **`./Application/config.py`** 放於同樣的相對路徑下。

1. 直接執行：`./Application/ras02/app_tmux.sh` 以啟動 monitors 和 subscriber
2. tmux 操作請見[也許你會用到的 tmux 快捷鍵](#也許你會用到的-tmux-快捷鍵)

### virtual machine
> 加入 `./Application/vm/` 的所有檔案，**並將`./Application/config.py` 放於同樣的相對路徑下**。

1. 啟動 msf 後台：`msfrpcd -P pentest -n -f`
2. 在 VM 分別執行：
- `python3 main_web.py`：主要網頁呈現，透過按鈕互動
- `attacker.py`：透過按鈕互動，觸發各種攻擊
- `process_data.py`：接收來自 raspberry02 的所有 monitor 資料後處理
- `model_engine.py`：接收處理完的資料後給模型預測，將結果傳給網頁