import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')

# ==========================================
# 1. 定義我們剛剛寫好的前處理器 (LivePreprocessor)
# ==========================================
class LivePreprocessor:
    def __init__(self, saved_features_path):
        print(f"🧩 初始化前處理器，載入模具: {saved_features_path}")
        self.features = np.load(saved_features_path, allow_pickle=True).tolist()
        
        # 確保推論時沒有 attack 標籤
        if 'attack' in self.features:
            self.features.remove('attack')
            
    def process(self, raw_packet_df):
        # 任務 1 & 2：強制對齊順序、缺少補 -1、填補空值
        processed_df = raw_packet_df.reindex(columns=self.features, fill_value=-1)
        processed_df = processed_df.replace([np.inf, -np.inf], -1).fillna(-1)
        
        # 任務 3：型態消毒 (強制轉數字)
        processed_df = processed_df.apply(pd.to_numeric, errors='coerce').fillna(-1)
        
        # 任務 4：維度轉換 (轉成 2D Numpy Array)
        model_input_array = processed_df.values 
        
        return model_input_array, processed_df.columns.tolist()

# ==========================================
# 2. 測試流程啟動
# ==========================================
if __name__ == "__main__":
    print("🕵️ 啟動 Live Pipeline 局部測試...\n")

    # --- 路徑設定 (請確認這兩個檔案都在同一個資料夾) ---
    # 你剛剛抽出來的假生資料
    MOCK_LIVE_DATA_PATH = "fake_live_data.csv" 
    
    # 你訓練時存下來的特徵名單 (請換成你實際的 npy 檔名)
    # 例如："../rospace_dataset/4_reduced_and_noperiodicity_dataset/usable_features_0512.npy"
    SAVED_FEATURES_PATH = "usable_features_0512.npy" 

    # --- A. 檢查檔案是否存在 ---
    if not os.path.exists(MOCK_LIVE_DATA_PATH):
        print(f"❌ 找不到測試資料: {MOCK_LIVE_DATA_PATH}，請先執行抽取腳本！")
        exit()
    if not os.path.exists(SAVED_FEATURES_PATH):
        print(f"❌ 找不到特徵模具: {SAVED_FEATURES_PATH}，請確認檔名與路徑！")
        exit()

    # --- B. 初始化處理器 ---
    preprocessor = LivePreprocessor(SAVED_FEATURES_PATH)
    expected_features_count = len(preprocessor.features)
    print(f"   - 模型預期接收 {expected_features_count} 個特徵")

    # --- C. 模擬上游傳來資料 ---
    print(f"\n📥 模擬接收實機封包 (從 {MOCK_LIVE_DATA_PATH} 讀取)")
    df_live = pd.read_csv(MOCK_LIVE_DATA_PATH, low_memory=False)
    print(f"   - 收到 {len(df_live)} 筆原始封包資料")
    print(f"   - 原始資料包含 {len(df_live.columns)} 個欄位 (包含很多模型不需要的垃圾)")

    # --- D. 執行前處理 ---
    print("\n⚡ 執行極速前處理 (對齊、清洗、轉型)...")
    X_input, final_columns = preprocessor.process(df_live)

    # --- E. 驗證結果 (最重要的環節) ---
    print("\n📊 [驗證報告]")
    print(f"1. 輸出形狀 (Shape): {X_input.shape}")
    
    if X_input.shape[1] == expected_features_count:
        print("   🟢 完美！特徵數量完全符合模型預期。")
    else:
        print(f"   🔴 錯誤！特徵數量不符 (預期: {expected_features_count}，實際: {X_input.shape[1]})")

    # 檢查是否有 NaN
    if np.isnan(X_input).any():
        print("   🔴 錯誤！資料陣列中殘留 NaN 空值。")
    else:
        print("   🟢 完美！所有空值皆已清除。")

    # 檢查是否為純數字 (Float)
    if not np.issubdtype(X_input.dtype, np.number):
        print(f"   🔴 錯誤！資料陣列中包含非數字型態 ({X_input.dtype})。")
    else:
        print("   🟢 完美！資料陣列是純數字，模型可直接讀取。")

    print("\n✅ 測試完成！如果上方全是綠燈，你的前處理器已經準備好上戰場了！")
    
    # (可選) 印出前兩筆處理好的資料預覽
    print("\n🔍 處理後的資料預覽 (前兩筆):")
    print(X_input[:2])