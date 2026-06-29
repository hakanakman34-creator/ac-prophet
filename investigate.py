"""
Investigate why predictions for BİGA DRONE (7077448) and UĞUR ELEKTRONİK (3367743) are abnormal.
Replicates the exact app.py pipeline.
"""
import pandas as pd
import io
import json
from data_processor import load_and_preprocess_data, load_marmara_services_config

# 1. Load data exactly like app.py does
df = load_and_preprocess_data('Jobsdata.xlsx', 'weatherdata.xlsx')
services_df = load_marmara_services_config('ServiceList.xlsx')

df['POSTING_DATE'] = pd.to_datetime(df['POSTING_DATE'])

# 2. Get recent_data exactly like app.py (last 10 days)
recent_days = sorted(df['POSTING_DATE'].unique())[-10:]
recent_data = df[df['POSTING_DATE'].isin(recent_days)].copy()

for col in ['NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS']:
    if col not in recent_data.columns:
        recent_data[col] = 0

def calc_trend(group):
    last_3 = group.sort_values('POSTING_DATE').tail(3)['Total_Jobs'].mean()
    overall = group['Total_Jobs'].mean()
    if pd.isna(last_3) or pd.isna(overall) or overall == 0:
        return 1.0
    return round(last_3 / overall, 2)

trend_map = recent_data.groupby('ASC_CODE').apply(calc_trend, include_groups=False).reset_index(name='Trend_Faktoru')
recent_data = pd.merge(recent_data, trend_map, on='ASC_CODE', how='left')
recent_data['Trend_Faktoru'] = recent_data['Trend_Faktoru'].fillna(1.0)

cols_to_keep = ['POSTING_DATE', 'Haftanin_Gunu', 'City', 'ASC_CODE', 'ASC_NAME', 'Total_Jobs',
                'Ortalama_Sicaklik', 'Hissedilen_Sicaklik', 'Hissedilen_Sicaklik_Lag1', 'Hissedilen_Sicaklik_Lag2',
                'NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS', 'Trend_Faktoru']
for c in cols_to_keep:
    if c not in recent_data.columns:
        recent_data[c] = ""
critical_cols = ['POSTING_DATE', 'Haftanin_Gunu', 'City', 'ASC_CODE', 'ASC_NAME', 'Total_Jobs',
                 'NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS']
recent_data = recent_data[cols_to_keep].dropna(subset=critical_cols).copy()

# 3. Build capacity data exactly like app.py
capacity_info = services_df[['ASC_CODE', 'ASC_NAME', 'City', 'Team Quantity', 'Job Completion Capacity']].copy()
capacity_info['Daily_Capacity'] = capacity_info['Team Quantity'] * capacity_info['Job Completion Capacity']

target_codes = ['3367743', '7077448']

print("=" * 80)
print("SECTION 1: HISTORICAL DATA (last 10 days) for target ASCs")
print("=" * 80)
target_data = recent_data[recent_data['ASC_CODE'].astype(str).isin(target_codes)]
print(target_data[['POSTING_DATE', 'ASC_CODE', 'ASC_NAME', 'Total_Jobs', 
                    'NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS', 'Trend_Faktoru']].to_string(index=False))

print("\n" + "=" * 80)
print("SECTION 2: CAPACITY for target ASCs")
print("=" * 80)
cap = capacity_info[capacity_info['ASC_CODE'].astype(str).isin(target_codes)]
print(cap[['ASC_CODE', 'ASC_NAME', 'City', 'Team Quantity', 'Job Completion Capacity', 'Daily_Capacity']].to_string(index=False))

print("\n" + "=" * 80)
print("SECTION 3: BATCH ASSIGNMENT - which cities are these ASCs batched with?")
print("=" * 80)
cities_list = list(capacity_info['City'].dropna().unique())
batch_size = 2
city_batches = [cities_list[i:i + batch_size] for i in range(0, len(cities_list), batch_size)]
target_city = target_data['City'].iloc[0] if len(target_data) > 0 else "?"
print(f"Target ASCs city: {target_city}")
for i, batch in enumerate(city_batches):
    if target_city in batch:
        print(f"Batch {i+1}: {batch}")
        batch_cap = capacity_info[capacity_info['City'].isin(batch)]
        print(f"\nAll ASCs in this batch ({len(batch_cap)} total):")
        print(batch_cap[['ASC_CODE', 'ASC_NAME', 'City', 'Daily_Capacity']].to_string(index=False))
        
        # Show how much historical data exists for each ASC in this batch
        print(f"\nHistorical data row counts per ASC in this batch:")
        batch_hist = recent_data[recent_data['City'].isin(batch)]
        for code in batch_cap['ASC_CODE'].astype(str).unique():
            code_rows = batch_hist[batch_hist['ASC_CODE'].astype(str) == code]
            name = code_rows['ASC_NAME'].iloc[0] if len(code_rows) > 0 else "?"
            avg = code_rows['Total_Jobs'].mean() if len(code_rows) > 0 else 0
            last_val = code_rows.sort_values('POSTING_DATE')['Total_Jobs'].iloc[-1] if len(code_rows) > 0 else 0
            print(f"  {code} ({name}): {len(code_rows)} rows, avg={avg:.1f}, last={last_val}")

print("\n" + "=" * 80)
print("SECTION 4: WHAT THE AI ACTUALLY SEES (the exact prompt text)")
print("=" * 80)
# Replicate predict_batch exactly
for i, batch in enumerate(city_batches):
    if target_city in batch:
        capacity_df = capacity_info.copy()
        hist_json = recent_data.to_json(orient='records', force_ascii=False)
        hist_df = pd.read_json(io.StringIO(hist_json))
        
        batch_capacity = capacity_df[capacity_df['City'].isin(batch)]
        batch_hist = hist_df[hist_df['City'].isin(batch)]
        
        batch_capacity_str = batch_capacity[['ASC_CODE', 'ASC_NAME', 'Daily_Capacity']].to_string(index=False)
        batch_hist_str = batch_hist.to_string(index=False)
        
        print(f"--- CAPACITY PORTION ---")
        print(batch_capacity_str)
        print(f"\n--- HISTORY PORTION (first 5 rows) ---")
        print(batch_hist.head(5).to_string(index=False))
        print(f"... ({len(batch_hist)} total rows)")
        
        # Check: are the target ASCs present?
        for code in target_codes:
            present = batch_hist[batch_hist['ASC_CODE'].astype(str) == code]
            print(f"\nASC {code} in batch_hist: {len(present)} rows")

print("\n" + "=" * 80)
print("SECTION 5: ACTUAL AI PREDICTION (live call)")
print("=" * 80)
from agents import ForecasterAgent, client, ForecasterOutput
import google.genai.types as types

agent = ForecasterAgent()

for i, batch in enumerate(city_batches):
    if target_city in batch:
        capacity_df = capacity_info.copy()
        hist_json = recent_data.to_json(orient='records', force_ascii=False)
        hist_df = pd.read_json(io.StringIO(hist_json))
        
        batch_capacity = capacity_df[capacity_df['City'].isin(batch)]
        batch_hist = hist_df[hist_df['City'].isin(batch)]
        
        batch_capacity_str = batch_capacity[['ASC_CODE', 'ASC_NAME', 'Daily_Capacity']].to_string(index=False)
        batch_hist_str = batch_hist.to_string(index=False)
        
        cities_str = ", ".join(batch)
        prompt = (
            f"Historical Context for {cities_str}:\n{batch_hist_str}\n\n"
            f"Capacity Data for {cities_str}:\n{batch_capacity_str}\n\n"
            f"7-Day Weather Forecast for {cities_str}:\nNo weather data\n\n"
            f"Multi-Year Historical Patterns:\nNo patterns\n\n"
            f"CRITICAL: You must include every single ASC_CODE shown in the capacity data above in your output.\n"
            f"Please generate the forecast for the following cities: {cities_str}."
        )
        
        response = client.models.generate_content(
            model=agent.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=agent.system_instruction,
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_budget=1024),
            ),
        )
        
        text = response.text
        start = text.find('{')
        end = text.rfind('}')
        json_str = text[start:end+1] if start != -1 and end != -1 else text
        out = ForecasterOutput.model_validate_json(json_str)
        
        print(f"\nAI PREDICTIONS FOR BATCH: {cities_str}")
        for day in out.seven_day_forecast:
            print(f"\n{day.day}:")
            for f in day.forecasts:
                marker = " <<<< TARGET" if str(f.ASC_CODE) in target_codes else ""
                print(f"  {f.ASC_CODE} | Carry={int(f.Carryover_Jobs):3d} | NewJobs={int(f.Predicted_Jobs):3d} | Completed={int(f.Completed_Jobs):3d} | Backlog={int(f.Predicted_Total_Jobs):3d}{marker}")
        break
