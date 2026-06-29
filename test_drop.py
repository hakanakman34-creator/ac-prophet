import pandas as pd
from data_processor import load_and_preprocess_data

df = load_and_preprocess_data('Jobsdata.xlsx', 'weatherdata.xlsx')
print("Total rows:", len(df))

# app.py logic
df['POSTING_DATE'] = pd.to_datetime(df['POSTING_DATE'])
recent_days = sorted(df['POSTING_DATE'].unique())[-10:]
recent_data = df[df['POSTING_DATE'].isin(recent_days)].copy()

for col in ['NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS']:
    if col not in recent_data.columns:
        recent_data[col] = 0

critical_cols = ['POSTING_DATE', 'Haftanin_Gunu', 'City', 'ASC_CODE', 'ASC_NAME', 'Total_Jobs', 
                 'NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS']
cols_to_keep = critical_cols + ['Ortalama_Sicaklik', 'Hissedilen_Sicaklik', 'Hissedilen_Sicaklik_Lag1', 'Hissedilen_Sicaklik_Lag2', 'Trend_Faktoru']

for c in cols_to_keep:
    if c not in recent_data.columns:
        recent_data[c] = ""

dropped = recent_data[cols_to_keep].dropna(subset=critical_cols).copy()
print("After dropna:", len(dropped))
print("Biga Drone in dropped?", any(dropped['ASC_NAME'].str.contains('B.GA', regex=True, na=False, case=False)))
print("Ugur in dropped?", any(dropped['ASC_NAME'].str.contains('U.UR', regex=True, na=False, case=False)))
