import pandas as pd

# Load the latest output file
df = pd.read_csv('./merged-12_05_2026@09_37_31.csv')

print("===== OUTPUT FILE SUMMARY =====")
print(f"File: merged-12_05_2026@09_37_31.csv")
print(f"Total rows: {len(df)}")
print(f"Total columns: {len(df.columns)}")
print(f"\nFirst few columns: {df.columns[:5].tolist()}")

if 'attack' in df.columns:
    print(f"\nAttack label column found!")
    print(f"Attack label value counts:")
    print(df['attack'].value_counts())
    print(f"\nFirst 10 rows of attack column:")
    print(df['attack'].head(10).tolist())
    print(f"\nNull values in attack column: {df['attack'].isnull().sum()}")
else:
    print(f"\nWarning: 'attack' column not found!")
    print(f"Available columns: {df.columns.tolist()}")

print(f"\n===== DATA SHAPE VERIFICATION =====")
print(f"Shape: {df.shape}")
print(f"First row timestamp: {df['timestamp'].iloc[0]}")
print(f"Last row timestamp: {df['timestamp'].iloc[-1]}")
