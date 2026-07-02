import pandas as pd
import json

with open('prediction_history.json', 'r', encoding='utf-8') as f:
    history = json.load(f)
df_pred = pd.DataFrame(history)
df_pred['target_date'] = pd.to_datetime(df_pred['target_date'])
df_pred['prediction_date'] = pd.to_datetime(df_pred['prediction_timestamp']).dt.normalize()
df_pred['target_date_dt'] = pd.to_datetime(df_pred['target_date']).dt.normalize()
df_pred['Lag_Days'] = (df_pred['target_date_dt'] - df_pred['prediction_date']).dt.days

# Exactly as in app.py for the dashboard totals
df_pred_latest = df_pred.sort_values('prediction_timestamp').groupby(['target_date', 'ASC_CODE']).tail(1).reset_index(drop=True)

df_actual = pd.read_excel('Jobsdata.xlsx')
df_actual['POSTING_DATE'] = pd.to_datetime(df_actual['POSTING_DATE'])
actual_agg = df_actual.groupby(['POSTING_DATE', 'ASC_CODE'])['NEW_ASSIGNED_JOBS'].sum().reset_index()
actual_agg['ASC_CODE'] = actual_agg['ASC_CODE'].astype(str).str.strip()
actual_agg.rename(columns={'POSTING_DATE': 'target_date'}, inplace=True)

df_pred_latest['ASC_CODE'] = df_pred_latest['ASC_CODE'].astype(str).str.strip()
merged = pd.merge(df_pred_latest, actual_agg, on=['target_date', 'ASC_CODE'], how='inner')

t_pred = merged['Predicted_Jobs'].sum()
t_act = merged['NEW_ASSIGNED_JOBS'].sum()
acc = max(0, 100 - (abs(t_pred - t_act) / t_act * 100))
print(f"LATEST PREDS OVERALL - Pred: {t_pred}, Act: {t_act}, Acc: {acc:.1f}%")

# Now calculate by lag using df_pred_latest
print("By lag (using only latest predictions):")
for lag in range(1, 6):
    lag_df = merged[merged['Lag_Days'] == lag]
    if lag_df.empty: continue
    lp = lag_df['Predicted_Jobs'].sum()
    la = lag_df['NEW_ASSIGNED_JOBS'].sum()
    if la > 0:
        l_acc = max(0, 100 - (abs(lp - la) / la * 100))
    else:
        l_acc = 100 if lp == 0 else 0
    print(f"Lag {lag}: Pred: {lp}, Actual: {la}, Hacim Doğruluk: {l_acc:.1f}%")
