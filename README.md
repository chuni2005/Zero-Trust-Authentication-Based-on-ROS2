# Zero Trust Authentication Based on ROS2
本專題以公開的 [ROSpace: Intrusion Detection Dataset for a ROS2-Based Cyber-Physical System](https://arxiv.org/abs/2402.08468) 為基礎，並參考其作者提供的程式碼庫 [rospace_dataset](https://github.com/TommasoPuccetti/rospace_dataset) 。我們的目標是復刻並簡化原始流程，建立一個可操作的版本，透過資料集訓練異常檢測模型，進一步驗證 Zero Trust 架構在 ROS2 環境下的可行性。

> This project is based on the publicly available [ROSpace: Intrusion Detection Dataset for a ROS2-Based Cyber-Physical System](https://arxiv.org/abs/2402.08468) and references the code repository [rospace_dataset](https://github.com/TommasoPuccetti/rospace_dataset) provided by its authors. Our goal is to replicate and simplify the original process, build a workable version, train an anomaly detection model using the dataset, and further verify the feasibility of the Zero Trust architecture in a ROS2 environment.

![](./struc.png)

整個流程我們將其拆分成 Data Collection、Data Preprcessing、Model Training、Application 做簡單的區分。

### 1. Data Collection
架構可以參考 [Simple Architecture Image](README/architecture.png)，主要的攻擊流程涵蓋了作業系統、網路層與 ROS2 服務層，分為「探索型 (Discovery)」與「阻斷服務 (DoS)」兩大類別 ：

##### (1) NMAP Discovery / Port Scanning
屬於**探索型 (Discovery) 攻擊**。攻擊者使用 Nmap 工具（版本 7.93）針對底層 Linux 作業系統進行網路掃描與漏洞探勘，試圖收集系統開放的埠口與潛在的網路弱點 。

##### (2) ROS2 Reconnaissance
同樣為**探索型攻擊**，但目標不同於傳統 OS。此攻擊專門針對 ROS2 (機器人作業系統) 架構進行偵察，試圖解析並探勘 ROS2 網路中的節點 (Nodes)、主題 (Topics) 與通訊結構 。

##### (3) NMAP SYN Flood (IPv6 RA Flood)
屬於針對網路層級的**阻斷服務 (DoS) 攻擊**。攻擊者透過 Nmap 發動泛洪攻擊 (Flooding)，利用大量偽造或惡意的網路請求塞滿頻寬與系統資源，阻礙正常的網路連線 。

##### (4) ROS2 Reflection
這是一種專門針對 ROS2 底層通訊協定 DDS (Data Distribution Service) 漏洞所發動的 **DoS 攻擊**。攻擊者透過惡意修改位址 (Reflection) 的方式，嚴重干擾並消耗 ROS2 的正常通訊資源 。

##### (5) ROS2 Node Crashing
同樣針對 ROS2 DDS 的已知漏洞發動攻擊。攻擊者利用封包溢位 (Overflow) 等技術手法，直接導致關鍵的 ROS2 節點發生異常崩潰 (Crash)，進而癱瘓機器人系統的部分或全部功能 。

##### (6) Metasploit SYN Flood
屬於針對常見網路層級的 **DoS 攻擊**。有別於 Nmap，此手法利用更強大的滲透測試框架 Metasploit (PyMetasploit) 發動高強度的 SYN 泛洪攻擊，以測試系統在極端負載下的承受極限 。

### 2. Data Preprocessing

```py
import os
import subprocess
import pandas as pd

print("< Path Setting >")
date_val = input("input code of collected data (e.g. 0507, 0509): ")

# get root path
current_dir = os.getcwd()
project_name = "Zero-Trust-Authentication-Based-on-ROS2"
if project_name in current_dir:
    root_dir = current_dir[:current_dir.find(project_name) + len(project_name)]
else:
    root_dir = current_dir

# path combinations
processing_dir = os.path.join(root_dir, "rospace_dataset", "1_processing")
labeling_dir = os.path.join(root_dir, "rospace_dataset", "2_labeling")

pcapng_path = os.path.join(root_dir, "raspberry_subscriber", f"monitor_{date_val}", "Tshark", "temp_capture.pcapng")
os_path = os.path.join(root_dir, "raspberry_subscriber", f"monitor_{date_val}", "OS", "OS_monitor.csv")
ros_path = os.path.join(root_dir, "raspberry_subscriber", f"monitor_{date_val}", "ROSBags", "ros2_monitor.csv")
attack_path = os.path.join(root_dir, "rospace_dataset", "attack", f"attacks_log_{date_val}.csv")

print("< PCAPNG to CSV Conversion >")
try:
    result = subprocess.run(
        ["python", "custom_pcapng2csv.py", pcapng_path],
        cwd=processing_dir,
        check=True,
        capture_output=True
    )
    print("Done.")

except subprocess.CalledProcessError as e:
    print("Exception Code:", e.returncode)
    print("Error Input:", e.cmd)
    print("Output Message:", e.output)
    print("Error Message:", e.stderr)
# ...詳情參照 main.ipynb
```

`依序執行下列檔案：`

- `3_complete_dataset\complete_dataset_composition.ipynb`

- `4_reduced_and_noperiodicity_dataset\reduced_dataset_composition.ipynb`

- `4_reduced_and_noperiodicity_dataset\no_periodicity_dataset.ipynb
`


### 3. Model Training

在資料前處理完成後，本專案主要探討並訓練兩種不同特性的機器學習演算法，以驗證在 ROS2 環境下的入侵偵測成效：

* **Isolation Forest (孤立森林)：** 作為非監督式學習模型，其優勢在於不需要事先標記攻擊類型，僅透過學習系統的「正常行為輪廓」來抓出異常，適合用來防範未知的零時差攻擊。
* **XGBoost (極限梯度提升)：** 作為監督式分類器，針對資料庫中已標記的攻擊特徵進行精準學習。

**訓練情境設計：**
為了全面評估模型，我們將訓練分為兩個層次：
1.  **情境 A (靜態檢測)：** 移除時間戳記並將資料打亂 (Shuffled)，以 60/40 的比例劃分訓練與測試集，專注於評估模型對「單一數據點」的絕對分類準確率。
2.  **情境 B (時序預警)：** 為了貼近真實的連續攻擊場景，我們將數據按時間順序打包成「區塊 (Blocks)」（包含 30 秒正常狀態與後續攻擊），訓練模型在時間序列中動態決策的能力。

**模型評估指標：**
我們採用以下標準量化模型表現：
* **Accuracy (準確率)：** 預測正確的比例。
* **ROC 曲線 (Receiver Operating Characteristic)：** 觀察假警報率 (FPR) 與真警報率/召回率 (TPR) 的權衡關係。
* **PR 曲線 (Precision-Recall Curve)：** 針對資安數據極端不平衡的特性，嚴格檢視警報的精準度 (Precision) 與召回率 (Recall)。

`執行 5_usage_notes\usage_note_A_detection_shuffled.ipynb`

### 4. Application

將訓練好的模型落地應用於 ROS2 資訊物理系統 (CPS) 時，防禦系統的「反應速度」與「穩定性」是關鍵。根據實驗驗證與模型比較，我們得出以下應用結論：

**1. 演算法效能對比**
在實際測試中，**XGBoost 的表現壓倒性地優於 Isolation Forest**。XGBoost 能達到 0.996 的極高準確率，且假警報率 (FPR) 僅有 0.0018；相較之下，Isolation Forest 準確率為 0.875，且 FPR 高達 0.057。這證明了在有明確標記的環境下，XGBoost 是更可靠的防禦主力。

**2. 偵測延遲與攻擊型態分析**
在連續時間序列的應用中，不同的攻擊手法會面臨不同的偵測難度：
* **高偵測、低延遲：** 針對網路層的 Flooding Nmap 攻擊，模型能夠在極短的時間內迅速觸發警報，具備極高的即時阻斷價值。
* **高偵測、高延遲：** Nmap Discovery 雖然最終偵測率同樣高達 0.99，但系統需要收集更長的時間序列特徵才能確認攻擊，導致偵測延遲較高。
* **ROS2 專屬漏洞挑戰：** 實驗發現，針對 ROS2 節點 (如 Node Crashing) 的某些攻擊，由於監視器本身可能因攻擊而故障，導致偵測能力下降，這是未來系統架構需強化的重點。

透過這些分析，本專案成功驗證了 AI 機器學習技術在 ROS2 零信任架構中取代傳統規則化 (Rule-based) 防禦的巨大潛力。

`依序執行以下步驟：`
- `raspberry02 running three monitor`
- `raspberry01 and raspberry02 ROS2 script`
- `vm run msf backend`
- `vm run main_web, attacker, data_process, model_engine scripts`