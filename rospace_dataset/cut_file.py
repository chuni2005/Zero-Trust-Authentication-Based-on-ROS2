import pandas as pd
import os

# ==========================================
# 1. 直接在這裡貼上你的原始檔案絕對路徑
# ==========================================
# 注意：前面保留小寫的 'r' 可以防止 Windows 路徑斜線 (\) 造成錯誤
INPUT_CSV_PATH = r"C:\Users\yuyux\OneDrive\Desktop\專題\Zero-Trust-Authentication-Based-on-ROS2\rospace_dataset\3_complete_dataset\cleaned_merged-0512.csv"

# 設定產出的假資料要存在哪裡 (預設存在當前目錄)
OUTPUT_CSV_PATH = "fake_live_data.csv"

# ==========================================
# 2. 開始抽取資料
# ==========================================
if not os.path.exists(INPUT_CSV_PATH):
    print(f"❌ 找不到檔案！請檢查路徑是否正確:\n{INPUT_CSV_PATH}")
else:
    print(f"📥 正在讀取原始資料: {os.path.basename(INPUT_CSV_PATH)} (這可能需要一點時間...)")
    
    # 為了省記憶體，我們先只讀前 10 萬筆
    df_raw = pd.read_csv(INPUT_CSV_PATH, nrows=100000, low_memory=False)
    
    # 隨機抽出 5 筆「正常 (observe)」和 5 筆「攻擊」資料
    df_normal = df_raw[df_raw['attack'] == 'observe'].sample(n=5, random_state=42)
    
    # 把不是 'observe' 的都當作攻擊
    df_attack = df_raw[df_raw['attack'] != 'observe']
    
    # 確保有足夠的攻擊資料可以抽
    n_attack_samples = min(5, len(df_attack)) 
    if n_attack_samples > 0:
        df_attack = df_attack.sample(n=n_attack_samples, random_state=42)
    
    # 合併並打亂順序
    df_fake_live = pd.concat([df_normal, df_attack]).sample(frac=1, random_state=42)
    
    # 存檔
    df_fake_live.to_csv(OUTPUT_CSV_PATH, index=False)
    
    print(f"✅ 成功！已抽出 {len(df_fake_live)} 筆最原始的生資料。")
    print(f"💾 檔案已儲存為: {OUTPUT_CSV_PATH}")
    print("\n💡 現在你可以把這個檔案丟給 live_preprocessing.py 測試看看了！")