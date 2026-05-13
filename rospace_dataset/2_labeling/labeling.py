#!/usr/bin/env python

import argparse, os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import timedelta
from datetime import datetime as dt
import glob
import gc
import concurrent.futures as fut
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
import traceback

parser = argparse.ArgumentParser(description="Helper script label the merged csv file")

parser.add_argument('-s', '--source', metavar='PATH', type=str,
                    help='the path to the csv file containing the unlabeled csv', required=True)

parser.add_argument('-a', '--attacks', metavar='PATH', type=str,
                    help='the path to the csv file containing attacks information (attack.py script output)', required=True)

args = parser.parse_args()

# [修改 1] 自動抓取資料日期作為輸出檔名
dataset_id = Path(args.attacks).stem.split('_')[-1]

def load_and_preprocess(path, timestamp_col_name, time_unit='ms', columns=None, nrows=None, skiprows=None):
    try:
        if "attack" in str(path): 
            time_unit = "s"

        print(f"Loading '{path}'...", end='', flush=True)
        content = pd.read_csv(path, nrows=nrows, skiprows=skiprows)

        if columns is not None:
            content.columns = columns
        print(f'{path} loaded')
        path = str(path)
        
        print(f"Sorting {path}...", end='', flush=True)
        content.sort_values(timestamp_col_name, inplace=True)
        gc.collect()
        print(f'{path} sorted')
        
        print(f"Convert timestamp on {path}...", end='', flush=True)
        timestamp = content[timestamp_col_name]
        content.drop(columns=[timestamp_col_name], inplace=True)
        
        # [修改 2] 強制將 Attacks 的時間轉換為純數字 Unix 秒數
        try: 
            temp_time = pd.to_datetime(timestamp, unit=time_unit)
        except ValueError:
            temp_time = pd.to_datetime(timestamp)
        if temp_time.dt.tz is not None:
            temp_time = temp_time.dt.tz_convert('UTC').dt.tz_localize(None)

        unix_time = (temp_time - pd.Timestamp('1970-01-01')) / pd.Timedelta('1s')
        content = content.assign(timestamp=unix_time)
        
        del timestamp
        gc.collect()
        print(f'{path} converted')
        min_stamp = content['timestamp'].min()
        max_stamp = content['timestamp'].max()
    except Exception as e:
        raise Exception(f"processing {path}: {str(e)}")
    return content, min_stamp, max_stamp

attacks_p = Path(args.attacks).resolve()
attacks, a_min, a_max = load_and_preprocess(attacks_p, 'timestamp')

print(f"Reading source file to determine size...")
merged_full = pd.read_csv(args.source, low_memory=False)
total_rows = len(merged_full)
print(f"Total rows in source file: {total_rows}")

skip = 0
rows = 500000

while skip < total_rows:  
    end_row = min(skip + rows, total_rows)
    print(f"Processing rows {skip} to {end_row}...", end='', flush=True)
    
    if skip == 0:
        merged = pd.read_csv(args.source, nrows=end_row, low_memory=False)
    else:
        merged = pd.read_csv(args.source, skiprows=range(1, skip+1), nrows=end_row-skip, low_memory=False)
    
    # [修改 3] 無情斬殺所有 Unnamed 幽靈欄位
    unnamed_cols = [c for c in merged.columns if 'Unnamed' in c]
    if unnamed_cols:
        merged.drop(columns=unnamed_cols, inplace=True)
        
    # [修改 4] 重建列編號，確保最左邊的數字列完美連貫
    merged.index = range(skip, end_row)
    
    # (已經刪除原本把 timestamp 轉成 datetime 字串的錯誤程式碼)
 
    print('Labeling attacks...', end='', flush=True)
    to_label = []
    for index, row in merged.iterrows():
        current = attacks[(attacks['timestamp'] <= row['timestamp'])].iloc[-1]
        label = current['event']
        attack = current['attack']
        succ = attacks[(attacks['timestamp'] > row['timestamp'])]
        if len(succ) <= 0:
            to_label.append(None)
            continue
        next_label = succ.iloc[0]['event']
        if label == 'start':
            to_label.append(attack)
        elif label == 'end' and next_label == 'observe':
            # osservazioni fra la fine di un attacco e l'inizio del periodo di observe; le scartiamo poi
            to_label.append('discard')
        elif label == 'observe' and next_label == 'start':
            to_label.append(label)
        else:
            print(f'unexpected entry (timestamp={row["timestamp"]} at index {index}) between {label} and {next_label} found: flagged to be removed')
            to_label.append('discard')

    label_values = np.array(to_label)
    del to_label
    
    merged = merged.assign(attack=label_values)
    gc.collect()

    print('Removing observations outside boundaries...')
    print(merged.shape)
    merged = merged[(merged['attack'] != 'discard')]
    print(merged.shape)
    gc.collect()
    print('done')

    working_dir = Path(os.getcwd()).resolve()
    target_dir = working_dir / 'merged-dataset'
    if not target_dir.exists():
        target_dir.mkdir()
        
    # [修改 6] 修正輸出檔名，並設定 index=True 產生與 merge 相同的格式
    target = target_dir / f'merged-{dataset_id}.csv'
    print(f'Saving to {target}...', end='', flush=True)
    
    if skip == 0:
        merged.to_csv(target, index=True, mode='w')
    else:
        merged.to_csv(target, index=True, mode='a', header=False)
        
    print('done')
    print(f'Labeling batch completed: {len(merged)} rows saved to {target}')

    skip = end_row
    del merged

print('\n=== Labeling process completed successfully ===')
print(f'Total rows processed: {total_rows}')