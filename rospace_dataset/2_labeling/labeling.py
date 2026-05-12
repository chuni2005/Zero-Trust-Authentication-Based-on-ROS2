#!/usr/bin/env python

import argparse, os
# import modin.pandas as pd
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
        ## non capisco perché non siano già ordinati...
        print(f"Sorting {path}...", end='', flush=True)
        # content = content.sort_values(timestamp_col_name)
        content.sort_values(timestamp_col_name, inplace=True)
        gc.collect()
        print(f'{path} sorted')
        print(f"Convert timestamp on {path}...", end='', flush=True)
        timestamp = content[timestamp_col_name]
        #content = content.drop(columns=[timestamp_col_name])
        content.drop(columns=[timestamp_col_name], inplace=True)
        
        #content = content.assign(timestamp=pd.to_datetime(timestamp, unit=time_unit))
        content = content.assign(timestamp=pd.to_datetime(timestamp, unit=time_unit))
        del timestamp
        gc.collect()
        print(f'{path} converted')
        min_stamp = content['timestamp'].min()
        max_stamp = content['timestamp'].max()
    except Exception as e:
        # print(f"in {path}: {str(e)}", level='Error')
        raise Exception(f"processing {path}: {str(e)}")
    return content, min_stamp, max_stamp

attacks_p = Path(args.attacks).resolve()
attacks, a_min, a_max = load_and_preprocess(attacks_p, 'timestamp')

# Read the full merged file to determine its size
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
    #merged = pd.read_csv("./merged-dataset/run_13_unlabelled.csv", usecols=cols)
    
    # Convert merged timestamp to datetime (timestamps are in seconds)
    merged['timestamp'] = pd.to_datetime(merged['timestamp'], unit='s')
 
    print('Labeling attacks...', end='', flush=True)
    to_label = []
    for index, row in merged.iterrows():
        current = attacks[(attacks['timestamp'] <= row['timestamp'])].iloc[-1]
        label = current['event']
        attack = current['attack']
        succ = attacks[(attacks['timestamp'] > row['timestamp'])]
        if len(succ) <= 0:
            # valori oltre la fine degli attacchi, scartare
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
    # merged = merged.assign(attack=lambda x: (x.index == to_label).astype(int))
    # merged = merged.assign(attack=label_values)
    merged = merged.assign(attack=label_values)
    gc.collect()
    #print(merged['attack'])

    print('Removing observations outside boundaries...')
    print(merged.shape)
    print(merged)
    merged = merged[(merged['attack'] != 'discard')]
    print(merged)
    gc.collect()
    print('done')

    working_dir = Path(os.getcwd()).resolve()
    target_dir = working_dir / 'merged-dataset'
    if not target_dir.exists():
        target_dir.mkdir()
    target = target_dir / f'merged-{dt.now().strftime("%d_%m_%Y@%H_%M_%S")}.csv'
    print(f'Saving to {target}...', end='', flush=True)
    merged.to_csv(target)
    print('done')
    print(f'Labeling batch completed: {len(merged)} rows saved to {target}')

    skip = end_row
    del merged

print('\n=== Labeling process completed successfully ===')
print(f'Total rows processed: {total_rows}')
