import pandas as pd
from data_processor import load_and_preprocess_data, load_marmara_services_config

df = load_and_preprocess_data('Jobsdata.xlsx', 'weatherdata.xlsx')
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
recent_data = recent_data[cols_to_keep].dropna(subset=critical_cols).copy()

batch_hist = recent_data[recent_data['City'].str.contains('ÇANAKKALE', na=False, case=False)]
print("Hist:")
print(batch_hist[['POSTING_DATE', 'City', 'ASC_NAME', 'Total_Jobs']].to_string(index=False))

capacity_info = load_marmara_services_config()[['ASC_CODE', 'ASC_NAME', 'City', 'Team Quantity', 'Job Completion Capacity']].copy()
capacity_info['Daily_Capacity'] = capacity_info['Team Quantity'] * capacity_info['Job Completion Capacity']
batch_cap = capacity_info[capacity_info['City'].str.contains('ÇANAKKALE', na=False, case=False)]
print("\nCap:")
print(batch_cap[['ASC_CODE', 'ASC_NAME', 'Daily_Capacity']].to_string(index=False))
