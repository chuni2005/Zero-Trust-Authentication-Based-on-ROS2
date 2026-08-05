import pandas as pd
import numpy as np
import os
import warnings
import datetime
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
        meta_info = {
            'original_columns': raw_packet_df.columns.tolist(),
            'original_dtypes': raw_packet_df.dtypes.to_dict(),
            'transformations': [] # 依序記錄破壞性操作
        }
        #對齊欄位
        missing_cols = [col for col in self.features if col not in raw_packet_df.columns]
        meta_info['missing_columns_filled'] = missing_cols

        current_df = raw_packet_df.reindex(columns=self.features)

        numeric_check = current_df.apply(pd.to_numeric, errors='coerce')
        #原本就是-1
        meta_info['original_minus_one_mask'] = (numeric_check == -1).values
        #無限大
        meta_info['inf_mask'] = (current_df == np.inf).values
        meta_info['neginf_mask'] = (current_df == -np.inf).values
        #原本就是nan
        meta_info['nan_mask'] = current_df.isna().values

        numeric_df = current_df.apply(pd.to_numeric, errors='coerce')

        #髒掉的string
        meta_info['dirty_string_mask'] = numeric_df.isna().values & ~meta_info['nan_mask']
        meta_info['dirty_string_values'] = current_df.values[meta_info['dirty_string_mask']]

        final_df = numeric_df.fillna(-1)
        model_input_array = final_df.values

        return model_input_array, meta_info

    def reverse(self, model_input_array, meta_info):
        rev_df = pd.DataFrame(model_input_array, columns=self.features)

        #目前是-1，但原本不是的人
        not_originally_minus_one = (rev_df.values == -1) & ~meta_info['original_minus_one_mask']

        #還原髒字串
        string_restore_mask = not_originally_minus_one & meta_info['dirty_string_mask']
        if string_restore_mask.any():
            rev_df.values[string_restore_mask] = meta_info['dirty_string_values']

        #還原inf
        inf_restore_mask = not_originally_minus_one & meta_info['inf_mask']
        rev_df.values[inf_restore_mask] = np.inf
        neginf_restore_mask = not_originally_minus_one & meta_info['neginf_mask']
        rev_df.values[neginf_restore_mask] = -np.inf

        #還原nan
        nan_restore_mask = not_originally_minus_one & meta_info['nan_mask']
        rev_df = rev_df.astype(object)
        rev_df.values[nan_restore_mask] = np.nan

        #模型需要，但資料沒有的欄位 (原本就沒有，所以丟掉)
        rev_df = rev_df.drop(columns=meta_info['missing_columns_filled'])
        #模型不需要，但資料有的欄位 (不需要，所以設nan)
        for col in meta_info['original_columns']:
            if col not in rev_df.columns:
                rev_df[col] = np.nan

        #reindex
        rev_df = rev_df.reindex(columns=meta_info['original_columns'])
        #還原type
        for col, dtype in meta_info['original_dtypes'].items():
            try:
                rev_df[col] = rev_df[col].astype(dtype)
            except:
                pass
        return rev_df

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
    X_input, meta_info= preprocessor.process(df_live)

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
    print("\n🔄 執行逆向還原測試...")
    try:
        df_reversed = preprocessor.reverse(X_input, meta_info)
        print("   🟢 成功執行 reverse()，回傳已正確接收。")

        print("\n📊 [驗證報告 - 逆向還原結果]")

        # 驗證 1：欄位數量與順序是否一致
        if df_reversed.columns.tolist() == df_live.columns.tolist():
            print("   🟢 完美！還原後的欄位名稱與順序與原始資料 100% 一致。")
        else:
            print("   🔴 錯誤！還原後的欄位結構或順序與原始資料不符。")

        # 驗證 2：資料筆數是否一致
        if len(df_reversed) == len(df_live):
            print(f"   🟢 完美！資料筆數一致 ({len(df_reversed)} 筆)。")
        else:
            print(f"   🔴 錯誤！筆數不一致 (原始: {len(df_live)}，還原: {len(df_reversed)})")
        # 驗證 3：型態是否一致
        type_mismatches = 0
        used_features = [col for col in preprocessor.features if col in df_live.columns]
        for col in used_features:
            if df_reversed[col].dtype != df_live[col].dtype:
                # 排除因為包含 NaN 導致無法轉回 int 的特殊狀況
                if not (df_live[col].dtype == np.int64 and df_reversed[col].dtype == np.float64):
                    type_mismatches += 1
                    print(f"   🟡 型態不符欄位: {col} (原始: {df_live[col].dtype} -> 還原: {df_reversed[col].dtype})")

        if type_mismatches == 0:
            print("   🟢 完美！欄位資料型態皆已還原（或處於安全的相容狀態）。")
        else:
            print(f"   🟡 警告！有 {type_mismatches} 個欄位的型態與原始資料不完全對齊 (通常是 NaN 引起的)。")
    except Exception as e:
        print(f"   🔴 錯誤！逆向還原過程中發生崩潰: {str(e)}")
    print("\n✅ 測試完成！如果上方全是綠燈，你的前處理器已經準備好上戰場了！")
    
    # (可選) 印出前兩筆處理好的資料預覽
    print("\n🔍 處理後的資料預覽 (前兩筆):")
    print(X_input[:2])
    if df_reversed is not None:
        print("\n💾 執行動態時間戳記存檔...")
        output_dir = "./rev"
        os.makedirs(output_dir, exist_ok=True)

        current_time = datetime.datetime.now()
        date_str = current_time.strftime("%m%d")
        now_str = current_time.strftime("%H%M")
        file_name = f"rev_{date_str}_{now_str}.csv"
        target_path = os.path.join(output_dir, file_name)
        df_reversed.to_csv(target_path, index=False)
        print(f"   🟢 [儲存成功] 還原檔案已寫入 -> {target_path}")