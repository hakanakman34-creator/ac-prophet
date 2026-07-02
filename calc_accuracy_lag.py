import pandas as pd
import json
from datetime import datetime

# Load predictions
try:
    with open('prediction_history.json', 'r', encoding='utf-8') as f:
        history = json.load(f)
    df_pred = pd.DataFrame(history)
    df_pred['target_date'] = pd.to_datetime(df_pred['target_date'])
    df_pred['prediction_date'] = pd.to_datetime(df_pred['prediction_timestamp']).dt.date
    df_pred['prediction_date'] = pd.to_datetime(df_pred['prediction_date'])
    df_pred['Lag_Days'] = (df_pred['target_date'] - df_pred['prediction_date']).dt.days
except Exception as e:
    print(f"Error loading predictions: {e}")
    exit()

# Load actuals
try:
    df_actual = pd.read_excel('Jobsdata.xlsx')
    df_actual['POSTING_DATE'] = pd.to_datetime(df_actual['POSTING_DATE'])
    actual_agg = df_actual.groupby(['POSTING_DATE', 'ASC_CODE'])['NEW_ASSIGNED_JOBS'].sum().reset_index()
    actual_agg['ASC_CODE'] = actual_agg['ASC_CODE'].astype(str).str.strip()
    actual_agg.rename(columns={'POSTING_DATE': 'target_date'}, inplace=True)
except Exception as e:
    print(f"Error loading actuals: {e}")
    exit()

df_pred['ASC_CODE'] = df_pred['ASC_CODE'].astype(str).str.strip()
merged = pd.merge(df_pred, actual_agg, on=['target_date', 'ASC_CODE'], how='inner')

if 'Predicted_Jobs' not in merged.columns:
    print("No Predicted_Jobs in data")
    exit()

merged['Error_Count'] = abs(merged['Predicted_Jobs'] - merged['NEW_ASSIGNED_JOBS'])

results = []
for lag in range(1, 6):
    lag_df = merged[merged['Lag_Days'] == lag]
    if lag_df.empty:
        results.append({'Lag': f"{lag} gün önceden", 'Genel Hacim Doğruluğu (%)': 'Veri Yok', 'Mutlak Tahmin Doğruluğu (%)': 'Veri Yok'})
        continue
    
    total_pred = lag_df['Predicted_Jobs'].sum()
    total_actual = lag_df['NEW_ASSIGNED_JOBS'].sum()
    total_absolute_error = lag_df['Error_Count'].sum()
    
    # Genel Hacim Doğruluğu (%)
    if total_actual > 0:
        genel_hacim = max(0, 100 - (abs(total_pred - total_actual) / total_actual * 100))
    elif total_pred == 0:
        genel_hacim = 100
    else:
        genel_hacim = 0
        
    # Mutlak Tahmin Doğruluğu (%)
    if total_actual > 0:
        mutlak_tahmin = max(0, 100 - (total_absolute_error / total_actual * 100))
    elif total_pred == 0:
        mutlak_tahmin = 100
    else:
        mutlak_tahmin = 0
    
    results.append({
        'Tahmin Günü (Lag)': f"{lag} gün önceden",
        'Genel Hacim Doğruluğu (%)': f"%{genel_hacim:.1f}",
        'Mutlak Tahmin Doğruluğu (%)': f"%{mutlak_tahmin:.1f}"
    })

res_df = pd.DataFrame(results)
print(res_df.to_string(index=False))
