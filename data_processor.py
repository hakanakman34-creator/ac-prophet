import pandas as pd
import logging
import json
import os
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONFIG_FILE = 'marmara_services_config.json'

def load_marmara_services_config(services_excel: str = 'ServiceList.xlsx') -> pd.DataFrame:
    """
    Loads Marmara region services from ServiceList.xlsx, then merges any custom capacity
    configurations (Team Quantity, Job Completion Capacity) from marmara_services_config.json
    if it exists. This ensures we only load services present in the Excel file,
    discarding any obsolete or test services from the JSON config, while preserving
    any custom capacities the user has configured.
    """
    logger.info("Loading services from Excel source of truth...")
    try:
        df = pd.read_excel(services_excel)
    except Exception as e:
        logger.error(f"Error reading {services_excel}: {e}")
        raise e

    # Rename columns to match expected schema
    if 'Ship To Code' in df.columns:
        df.rename(columns={'Ship To Code': 'ASC_CODE', 'ASC Name': 'ASC_NAME'}, inplace=True)
        
    # Filter for Marmara (assuming Region is Istanbul, Marmara, etc. Let's just catch ISTANBUL variants for now, or use the user's rule)
    marmara_regions = ['İSTANBUL', 'ISTANBUL', 'STANBUL', 'MARMARA']
    df = df[df['Region'].str.upper().isin(marmara_regions)].copy()
    
    # Ensure ASC_CODE is standard integers
    df['ASC_CODE'] = df['ASC_CODE'].astype(int)

    # Initialize capacity columns with defaults
    df['Team Quantity'] = 5
    df['Job Completion Capacity'] = 4.0  # 4.0 jobs per team per day

    # Load custom settings from config JSON if it exists
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Create a lookup mapping: str(ASC_CODE) -> (Team Quantity, Job Completion Capacity)
            # We use string matching to be robust against any int/str type mismatches
            config_lookup = {}
            for item in config_data:
                code = str(item.get('ASC_CODE', '')).strip()
                if code:
                    config_lookup[code] = {
                        'Team Quantity': item.get('Team Quantity', 5),
                        'Job Completion Capacity': float(item.get('Job Completion Capacity', 4.0))
                    }
            
            # Apply to the dataframe
            for idx, row in df.iterrows():
                code_str = str(row['ASC_CODE']).strip()
                if code_str in config_lookup:
                    df.at[idx, 'Team Quantity'] = config_lookup[code_str]['Team Quantity']
                    df.at[idx, 'Job Completion Capacity'] = config_lookup[code_str]['Job Completion Capacity']
                    
            logger.info("Successfully merged custom capacities from config JSON.")
        except Exception as e:
            logger.error(f"Error merging custom config file: {e}")

    # Save the cleaned/synchronized config back to JSON
    try:
        save_marmara_services_config(df)
        logger.info(f"Synchronized configuration saved to {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Error saving synchronized config: {e}")
        
    return df

def save_marmara_services_config(df: pd.DataFrame):
    """
    Saves the services dataframe to a JSON config file.
    """
    data = df.to_dict(orient='records')
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def calculate_heat_index(temp_c, humidity):
    """
    Approximates the Heat Index (Hissedilen Sıcaklık) in Celsius.
    """
    if pd.isna(temp_c) or pd.isna(humidity):
        return temp_c
        
    temp_f = (temp_c * 9/5) + 32
    
    if temp_c < 27:
        hi_f = 0.5 * (temp_f + 61.0 + ((temp_f - 68.0) * 1.2) + (humidity * 0.094))
        return round((hi_f - 32) * 5/9, 1)
        
    hi_f = -42.379 + 2.04901523*temp_f + 10.14333127*humidity - 0.22475541*temp_f*humidity \
           - 6.83783e-3*temp_f**2 - 5.481717e-2*humidity**2 + 1.22874e-3*temp_f**2*humidity \
           + 8.5282e-4*temp_f*humidity**2 - 1.99e-6*temp_f**2*humidity**2
           
    if humidity < 13 and 80 <= temp_f <= 112:
        adjustment = ((13 - humidity) / 4) * ((17 - abs(temp_f - 95)) / 17)**0.5
        hi_f -= adjustment
    elif humidity > 85 and 80 <= temp_f <= 87:
        adjustment = ((humidity - 85) / 10) * ((87 - temp_f) / 5)
        hi_f += adjustment
        
    return round((hi_f - 32) * 5/9, 1)

def fetch_future_weather(cities: list) -> pd.DataFrame:
    """
    Fetches 7-day future weather forecasts for a list of cities using Open-Meteo or Visual Crossing based on settings.
    """
    import os
    import json
    
    settings_file = "settings.json"
    weather_source = "Open-Meteo"
    vc_api_key = ""
    
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                app_settings = json.load(f)
                weather_source = app_settings.get("weather_source", "Open-Meteo")
                vc_api_key = app_settings.get("visual_crossing_api_key", "")
        except Exception as e:
            logger.error(f"Failed to read settings.json: {e}")

    try:
        import streamlit as st
        if st.secrets.get("visual_crossing_api_key") and not vc_api_key:
            vc_api_key = st.secrets.get("visual_crossing_api_key")
    except Exception:
        pass

    # Quick coordinate mapping for Marmara cities
    city_coords = {
        'ISTANBUL': (41.0082, 28.9784),
        'BURSA': (40.1828, 29.0667),
        'KOCAELI': (40.7654, 29.9408),
        'KOCAELİ': (40.7654, 29.9408),
        'SAKARYA': (40.7731, 30.3948),
        'TEKIRDAG': (40.9780, 27.5110),
        'TEKİRDAĞ': (40.9780, 27.5110),
        'CANAKKALE': (40.1553, 26.4142),
        'ÇANAKKALE': (40.1553, 26.4142),
        'EDIRNE': (41.6771, 26.5560),
        'EDİRNE': (41.6771, 26.5560),
        'YALOVA': (40.6500, 29.2667),
        'BALIKESIR': (39.6484, 27.8826),
        'BALIKESİR': (39.6484, 27.8826),
        'BILECIK': (40.1451, 29.9798),
        'BİLECİK': (40.1451, 29.9798),
        'KIRKLARELI': (41.7333, 27.2167),
        'KIRKLARELİ': (41.7333, 27.2167)
    }
    
    all_forecasts = []
    
    for city in set(cities):
        # Default to Istanbul coords if not found
        lat, lon = city_coords.get(city.upper(), (41.0082, 28.9784))
        
        try:
            if weather_source == "Visual Crossing" and vc_api_key:
                url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/next7days?unitGroup=metric&include=days&key={vc_api_key}&contentType=json"
                res = requests.get(url, timeout=10)
                if res.status_code != 200:
                    raise Exception(f"Visual Crossing returned status code {res.status_code}: {res.text}")
                data = res.json()
                days = data.get('days', [])
                
                for day in days:
                    date_str = day.get('datetime', '')
                    if not date_str: continue
                    t_m = float(day.get('tempmax', 0.0))
                    t_mn = float(day.get('tempmin', 0.0))
                    h_m = float(day.get('humidity', 0.0))
                    
                    avg_temp = round((t_m + t_mn) / 2, 1)
                    hi_temp = calculate_heat_index(avg_temp, h_m)
                    
                    import datetime
                    try:
                        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                        days_tr = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
                        haftanin_gunu = days_tr[dt.weekday()]
                    except Exception:
                        haftanin_gunu = ""
                        
                    all_forecasts.append({
                        'Tarih': date_str,
                        'Yıl': date_str[:4],
                        'Ay': date_str[5:7],
                        'Gün': date_str[8:10],
                        'Haftanin_Gunu': haftanin_gunu,
                        'City': city,
                        'Ortalama_Sicaklik': avg_temp,
                        'Hissedilen_Sicaklik': hi_temp,
                        'Maksimum_Sicaklik': t_m,
                        'Minimum_Sicaklik': t_mn,
                        'Ortalama_Nem': h_m
                    })
            else:
                # Open-Meteo logic
                url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&past_days=14&daily=temperature_2m_max,temperature_2m_min,relative_humidity_2m_max&timezone=auto"
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                res = requests.get(url, headers=headers, timeout=15)
                if res.status_code != 200:
                    raise Exception(f"Open-Meteo returned status code {res.status_code}: {res.text}")
                data = res.json()
                daily = data.get('daily', {})
                dates = daily.get('time', [])
                t_max = daily.get('temperature_2m_max', [])
                t_min = daily.get('temperature_2m_min', [])
                h_max = daily.get('relative_humidity_2m_max', [])
                
                for i in range(len(dates)):
                    try:
                        t_m = float(t_max[i])
                        t_mn = float(t_min[i])
                        h_m = float(h_max[i])
                    except (TypeError, ValueError):
                        t_m, t_mn, h_m = 0.0, 0.0, 0.0
                        
                    avg_temp = round((t_m + t_mn) / 2, 1)
                    hi_temp = calculate_heat_index(avg_temp, h_m)
                    
                    import datetime
                    try:
                        dt = datetime.datetime.strptime(dates[i], "%Y-%m-%d")
                        days_tr = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
                        haftanin_gunu = days_tr[dt.weekday()]
                    except Exception:
                        haftanin_gunu = ""
                        
                    all_forecasts.append({
                        'Tarih': dates[i],
                        'Yıl': dates[i][:4],
                        'Ay': dates[i][5:7],
                        'Gün': dates[i][8:10],
                        'Haftanin_Gunu': haftanin_gunu,
                        'City': city,
                        'Ortalama_Sicaklik': avg_temp,
                        'Hissedilen_Sicaklik': hi_temp,
                        'Maksimum_Sicaklik': t_m,
                        'Minimum_Sicaklik': t_mn,
                        'Ortalama_Nem': h_m
                    })
        except Exception as e:
            logger.error(f"Failed to fetch weather for {city} via {weather_source}: {e}")
            
        import time
        time.sleep(0.3)
        
    return pd.DataFrame(all_forecasts)

def load_and_preprocess_data(jobs_file: str, weather_file: str) -> pd.DataFrame:
    """
    Loads historical jobs and weather data, filters for Marmara region (ISTANBUL),
    and aggregates daily counts per City and ASC.
    """
    logger.info("Loading Jobs data...")
    xls = pd.ExcelFile(jobs_file)
    jobs_dfs = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        jobs_dfs.append(df)
    
    jobs_df = pd.concat(jobs_dfs, ignore_index=True)
    jobs_df = jobs_df[jobs_df['Region'] == 'İSTANBUL']
    jobs_df['POSTING_DATE'] = pd.to_datetime(jobs_df['POSTING_DATE']).dt.date
    
    logger.info("Aggregating daily active backlog...")
    daily_jobs = jobs_df.groupby(
        ['ASC_CODE', 'ASC_NAME', 'City', 'POSTING_DATE'], 
        as_index=False
    )[['ACTIVE_BACKLOG', 'NEW_ASSIGNED_JOBS', 'CANCELLED_JOBS', 'COMPLETED_JOBS', 'CARRYOVER_JOBS']].sum()
    daily_jobs.rename(columns={'ACTIVE_BACKLOG': 'Total_Jobs'}, inplace=True)
    daily_jobs['Total_Jobs'] = daily_jobs['Total_Jobs'].clip(lower=0)
    
    logger.info("Loading Weather data...")
    weather_df = pd.read_excel(weather_file)
    weather_df.columns = [
        'Tarih', 'Yil', 'Ay', 'Gun', 'Il', 
        'Ortalama_Sicaklik', 'Maksimum_Sicaklik', 'Minimum_Sicaklik', 'Ortalama_Nem'
    ]
    weather_df['Tarih'] = pd.to_datetime(weather_df['Tarih']).dt.date
    
    logger.info("Merging Jobs and Weather data...")
    merged_df = pd.merge(
        daily_jobs,
        weather_df,
        left_on=['POSTING_DATE', 'City'],
        right_on=['Tarih', 'Il'],
        how='left'
    )
    
    # 1. Hissedilen Sıcaklık
    merged_df['Hissedilen_Sicaklik'] = merged_df.apply(
        lambda row: calculate_heat_index(row['Ortalama_Sicaklik'], row['Ortalama_Nem']), axis=1
    )
    
    # 2. Haftanin_Gunu
    merged_df['POSTING_DATE_dt'] = pd.to_datetime(merged_df['POSTING_DATE'])
    days_tr = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    merged_df['Haftanin_Gunu'] = merged_df['POSTING_DATE_dt'].dt.weekday.map(lambda x: days_tr[int(x)] if pd.notna(x) else "")
    
    # 3. Lags
    merged_df = merged_df.sort_values(by=['City', 'POSTING_DATE_dt']).reset_index(drop=True)
    merged_df['Hissedilen_Sicaklik_Lag1'] = merged_df.groupby('City')['Hissedilen_Sicaklik'].shift(1)
    merged_df['Hissedilen_Sicaklik_Lag2'] = merged_df.groupby('City')['Hissedilen_Sicaklik'].shift(2)
    
    # Backfill NAs for lags just in case
    merged_df['Hissedilen_Sicaklik_Lag1'] = merged_df['Hissedilen_Sicaklik_Lag1'].bfill().fillna(merged_df['Hissedilen_Sicaklik'])
    merged_df['Hissedilen_Sicaklik_Lag2'] = merged_df['Hissedilen_Sicaklik_Lag2'].bfill().fillna(merged_df['Hissedilen_Sicaklik'])
    
    merged_df.drop(columns=['POSTING_DATE_dt'], inplace=True)
    
    return merged_df

def extract_multi_year_patterns(historical_file: str = 'Jobsdata_backup_old.xlsx') -> str:
    """
    Extracts high-level statistical patterns from the multi-year raw database.
    Calculates the relative volume of jobs arriving on each day of the week,
    proving to the ForecasterAgent that weekends are active.
    """
    try:
        if not os.path.exists(historical_file):
            return "No long-term historical file found. Assume normal weekend drops (e.g. Sat=80%, Sun=20% of weekdays)."
            
        df = pd.read_excel(historical_file)
        if 'COMPLETE_DT' not in df.columns or 'COUNT' not in df.columns:
            return "Historical file format unrecognizable. Assume normal weekend drops (e.g. Sat=80%, Sun=20% of weekdays)."
            
        df['COMPLETE_DT'] = pd.to_datetime(df['COMPLETE_DT'])
        df['day_name'] = df['COMPLETE_DT'].dt.day_name()
        
        # Calculate sums per day
        daily_sums = df.groupby('day_name')['COUNT'].sum()
        
        # Calculate average weekday volume
        weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        weekday_vols = [daily_sums.get(d, 0) for d in weekdays]
        avg_weekday = sum(weekday_vols) / len(weekdays) if weekdays else 1.0
        
        sat_vol = daily_sums.get('Saturday', 0)
        sun_vol = daily_sums.get('Sunday', 0)
        
        sat_ratio = round((sat_vol / avg_weekday) * 100, 1) if avg_weekday > 0 else 0
        sun_ratio = round((sun_vol / avg_weekday) * 100, 1) if avg_weekday > 0 else 0
        
        pattern_str = (
            f"[MULTI-YEAR HISTORICAL PATTERNS]\n"
            f"Based on {len(df)} historical records spanning past years:\n"
            f"- Average Weekday Volume: {round(avg_weekday, 1)} jobs\n"
            f"- Saturday Volume: {sat_vol} jobs -> ({sat_ratio}% of a regular weekday)\n"
            f"- Sunday Volume: {sun_vol} jobs -> ({sun_ratio}% of a regular weekday)\n"
            f"CRITICAL RULE: Service centers ARE ACTIVE on weekends. "
            f"You MUST NOT predict 0 incoming/completed jobs for weekends. Use the historical percentages above to estimate weekend volume compared to nearby weekdays."
        )
        return pattern_str
    except Exception as e:
        logger.error(f"Error extracting patterns: {e}")
        return "Error reading multi-year history. Assume Sat=80% and Sun=20% of weekday volume."

PREDICTION_HISTORY_FILE = "prediction_history.json"

def save_prediction_history(seven_day_risk_list: list):
    """
    Saves generated predictions to a local JSON file for later accuracy analysis.
    seven_day_risk_list is the list of daily risk map dictionaries.
    """
    history = []
    if os.path.exists(PREDICTION_HISTORY_FILE):
        try:
            with open(PREDICTION_HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception as e:
            logger.error(f"Error reading prediction history: {e}")
            history = []
            
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Use a dictionary to overwrite existing predictions for the same target_date & ASC_CODE
    # so we keep the most recent prediction if it is run multiple times.
    # Alternatively, just append. The user probably wants the latest prediction for a day.
    # Let's just keep the most recent one by using a dict key.
    
    history_dict = {}
    for r in history:
        # key: target_date + ASC_CODE
        k = f"{r.get('target_date')}_{r.get('ASC_CODE')}"
        history_dict[k] = r
    
    for daily in seven_day_risk_list:
        day_str = str(daily.get('day', '')).strip()
        risk_map = daily.get('risk_map', [])
        for item in risk_map:
            asc_code = str(item.get('ASC_CODE', '')).strip()
            pred_jobs = item.get('Predicted_Total_Jobs', 0)
            inc_jobs = item.get('Predicted_Jobs', 0)
            
            record = {
                "prediction_timestamp": now_str,
                "target_date": day_str,
                "ASC_CODE": asc_code,
                "Predicted_Total_Jobs": pred_jobs,
                "Predicted_Jobs": inc_jobs
            }
            k = f"{day_str}_{asc_code}"
            history_dict[k] = record
            
    new_history = list(history_dict.values())
            
    try:
        with open(PREDICTION_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_history, f, ensure_ascii=False, indent=4)
        logger.info(f"Successfully saved predictions to {PREDICTION_HISTORY_FILE}")
    except Exception as e:
        logger.error(f"Error saving prediction history: {e}")

if __name__ == "__main__":
    df = load_and_preprocess_data('Jobsdata.xlsx', 'weatherdata.xlsx')
    print(df.head())
    print(f"Total rows: {len(df)}")
