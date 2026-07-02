import pandas as pd
import json

with open('prediction_history.json', 'r', encoding='utf-8') as f:
    history = json.load(f)
df_pred = pd.DataFrame(history)
df_pred['target_date'] = pd.to_datetime(df_pred['target_date'])
df_pred['prediction_date'] = pd.to_datetime(df_pred['prediction_timestamp']).dt.date
df_pred['prediction_date'] = pd.to_datetime(df_pred['prediction_date'])
df_pred['Lag_Days'] = (df_pred['target_date'] - df_pred['prediction_date']).dt.days

df_actual = pd.read_excel('Jobsdata.xlsx')
df_actual['POSTING_DATE'] = pd.to_datetime(df_actual['POSTING_DATE'])
actual_agg = df_actual.groupby(['POSTING_DATE', 'ASC_CODE'])['NEW_ASSIGNED_JOBS'].sum().reset_index()
actual_agg['ASC_CODE'] = actual_agg['ASC_CODE'].astype(str).str.strip()
actual_agg.rename(columns={'POSTING_DATE': 'target_date'}, inplace=True)

df_pred['ASC_CODE'] = df_pred['ASC_CODE'].astype(str).str.strip()
merged = pd.merge(df_pred, actual_agg, on=['target_date', 'ASC_CODE'], how='inner')

merged['Error_Count'] = abs(merged['Predicted_Jobs'] - merged['NEW_ASSIGNED_JOBS'])

print(f"OVERALL:")
t_pred = merged['Predicted_Jobs'].sum()
t_act = merged['NEW_ASSIGNED_JOBS'].sum()
acc = max(0, 100 - (abs(t_pred - t_act) / t_act * 100))
print(f"Total Pred: {t_pred}, Total Actual: {t_act}, Diff: {t_pred - t_act}, Genel Hacim Doğruluğu: {acc:.1f}%")
print("-" * 30)

for lag in range(1, 6):
    lag_df = merged[merged['Lag_Days'] == lag]
    if lag_df.empty: continue
    lp = lag_df['Predicted_Jobs'].sum()
    la = lag_df['NEW_ASSIGNED_JOBS'].sum()
    if la > 0:
        l_acc = max(0, 100 - (abs(lp - la) / la * 100))
    else:
        l_acc = 100 if lp == 0 else 0
    print(f"Lag {lag}: Pred: {lp}, Actual: {la}, Diff: {lp - la}, Genel Hacim: {l_acc:.1f}%")
