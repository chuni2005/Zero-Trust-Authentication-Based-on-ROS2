#!/usr/bin/env python3

import argparse
import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime as dt
import gc

# 1. 設定參數接收
parser = argparse.ArgumentParser(description="Helper script to label large merged csv files in chunks")
parser.add_argument('-s', '--source', metavar='PATH', type=str,
                    help='the path to the unlabelled merged csv file',
                    nargs=1, required=True)
parser.add_argument('-a', '--attacks', metavar='PATH', type=str,
                    help='the path to the attacks log csv file',
                    nargs=1, required=True)
args = parser.parse_args()

def process_large_file():
    # 2. 解析路徑
    source_p = Path(args.source[0]).resolve()
    attacks_p = Path(args.attacks[0]).resolve()

    if not source_p.exists() or not attacks_p.exists():
        print("找不到來源檔案或攻擊日誌，請確認路徑是否正確。")
        return

    # 3. 讀取並整理攻擊日誌
    print(f"Loading attacks log from {attacks_p}...")
    attacks = pd.read_csv(attacks_p)
    attacks.sort_values('timestamp', inplace=True)
    
    # 4. 設定輸出目標
    working_dir = Path(os.getcwd()).resolve()
    target_dir = working_dir / 'merged-dataset'
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f'labelled_large_{dt.now().strftime("%d_%m_%Y@%H_%M_%S")}.csv'
    
    # 5. 分批處理設定 (每次讀取 50 萬筆)
    chunksize = 500000
    chunk_idx = 0
    print(f"開始分批處理，每次讀取 {chunksize} 筆資料...")

    # 使用 chunksize 參數，Pandas 會回傳一個可迭代的物件
    for chunk in pd.read_csv(source_p, chunksize=chunksize):
        print(f"\n--- 正在處理第 {chunk_idx + 1} 批次資料 (大小: {chunk.shape}) ---")
        
        to_label = []
        for index, row in chunk.iterrows():
            # 找出時間點之前的所有攻擊紀錄
            past_attacks = attacks[(attacks['timestamp'] <= row['timestamp'])]
            if len(past_attacks) == 0:
                to_label.append(None)
                continue
                
            current = past_attacks.iloc[-1]
            label = current['event']
            attack_name = current['attack']
            
            # 找出時間點之後的所有攻擊紀錄
            succ = attacks[(attacks['timestamp'] > row['timestamp'])]
            if len(succ) == 0:
                to_label.append(None)
                continue
                
            next_label = succ.iloc[0]['event']
            
            # 判斷標籤邏輯
            if label == 'start':
                to_label.append(attack_name)
            elif label == 'end' and next_label == 'observe':
                to_label.append('discard')
            elif label == 'observe' and next_label == 'start':
                to_label.append(label)
            else:
                to_label.append('discard')

        # 貼上標籤並剃除 discard 的資料
        chunk = chunk.assign(attack=to_label)
        chunk_filtered = chunk[chunk['attack'] != 'discard']
        
        # 6. 分批寫入 CSV
        # 如果是第一批，就寫入欄位標題 (header=True)，模式為覆寫 ('w')
        # 如果是後續批次，就不寫標題 (header=False)，模式為附加 ('a')
        mode = 'w' if chunk_idx == 0 else 'a'
        header = True if chunk_idx == 0 else False
        
        print(f"寫入 {chunk_filtered.shape[0]} 筆有效資料至檔案...")
        chunk_filtered.to_csv(target, mode=mode, header=header, index=False)
        
        chunk_idx += 1
        del chunk, chunk_filtered, to_label
        gc.collect() # 強制釋放記憶體

    print(f"\n大量資料標註完成！檔案已存至: {target}")

if __name__ == "__main__":
    process_large_file()
