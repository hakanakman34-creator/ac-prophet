import os
import json
from pydantic import BaseModel
from typing import List, Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
logger = logging.getLogger(__name__)

# Try to initialize the Gemini client
try:
    client = genai.Client(http_options=types.HttpOptions(timeout=120000))
except Exception as e:
    logger.warning("Could not initialize Gemini Client. Make sure GEMINI_API_KEY is set in .env")
    client = None

# Pydantic Schemas for Structured Output
class ASCForecast(BaseModel):
    ASC_CODE: str
    City: str
    Carryover_Jobs: int
    Predicted_Jobs: int
    Completed_Jobs: int
    Predicted_Total_Jobs: int

class DailyForecast(BaseModel):
    day: str
    forecasts: List[ASCForecast]

class ForecasterOutput(BaseModel):
    seven_day_forecast: List[DailyForecast]

# Watchdog structured schemas
class WatchdogASCRisk(BaseModel):
    ASC_CODE: str
    City: str
    Predicted_Total_Jobs: int
    Predicted_Jobs: int = 0
    Durum: str  # Kırmızı / Sarı / Yeşil
    Kapasite_Asimi: str = "Hayır" # "Evet" / "Hayır"

class WatchdogDailyRisk(BaseModel):
    day: str
    risk_map: List[WatchdogASCRisk]

class WatchdogOutput(BaseModel):
    seven_day_risk: List[WatchdogDailyRisk]


class ForecasterAgent:
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name
        self.system_instruction = """You are an expert Data Scientist forecasting HVAC installation demand for Samsung Turkey, focusing EXCLUSIVELY on the Marmara Region.
Data Schema Provided:
Weather Data: [Tarih, Yıl, Ay, Gün, Haftanin_Gunu, City, Ortalama_Sicaklik, Hissedilen_Sicaklik, Hissedilen_Sicaklik_Lag1, Hissedilen_Sicaklik_Lag2, Maksimum_Sicaklik, Minimum_Sicaklik, Ortalama_Nem]
Recent Context Data: [POSTING_DATE, Haftanin_Gunu, City, ASC_NAME, Total_Jobs, Ortalama_Sicaklik, Hissedilen_Sicaklik, Hissedilen_Sicaklik_Lag1, Hissedilen_Sicaklik_Lag2, NEW_ASSIGNED_JOBS, CARRYOVER_JOBS, COMPLETED_JOBS, Trend_Faktoru]
Capacity Data: [ASC_CODE, City, Daily_Capacity]
Multi-Year Historical Patterns: Text describing how weekends typically behave relative to weekdays based on years of past data.

CRITICAL RULES FOR DATA HANDLING:
The 'Total_Jobs' column in the recent historical data represents the ACTIVE_BACKLOG (the true queued work) for each specific service center (ASC_NAME) on that date.
Your prediction goal is to estimate the future daily breakdown for each service center over the next 7 days, based on their recent backlog trends, the upcoming weather forecast, their daily completion capacity, and the multi-year historical patterns.

CRITICAL FORECASTING LOGIC:
1. HEAT INDEX & LAG: Pay close attention to 'Hissedilen_Sicaklik' (Heat Index) and its lagged versions. A high heat index 1 or 2 days ago strongly drives an increase in 'Predicted_Jobs' today due to the delay between the purchasing decision and installation registration.
2. DAY OF WEEK & MULTI-YEAR PATTERNS: Pay attention to 'Haftanin_Gunu' and strictly follow the [MULTI-YEAR HISTORICAL PATTERNS] provided in the prompt. Service centers DO OPERATE on weekends, and new jobs DO ARRIVE on weekends. Never assume weekend values are 0. Use the exact historical percentage ratios provided to calculate weekend incoming/completed jobs relative to adjacent weekdays.
3. MOMENTUM AND SURGE PEAK CATCHING: Pay strict attention to the 'Trend_Faktoru' provided in the context data (Last 3 days avg vs 10 days avg). If Trend_Faktoru is > 1.2, it means incoming jobs are currently surging! DO NOT regress to the historical mean. For weekdays, you MUST extrapolate this momentum. HOWEVER, for weekends (Saturday/Sunday), you MUST still apply the strict historical weekend drop ratios to the surged baseline. Do not predict weekday-level volumes for weekends, even during a surge!

For each day, you must predict:
1. Carryover_Jobs: The uncompleted jobs remaining from the PREVIOUS day. CRITICAL: Day 1 Carryover MUST equal the Last known Total_Jobs from history. For Day 2 to Day 7, Carryover_Jobs MUST EXACTLY equal the PREVIOUS day's Predicted_Total_Jobs. DO NOT reset this to 0!
2. Predicted_Jobs: New jobs expected to arrive on that day (expect a spike if the weather is getting hotter, especially considering Lag1 and Lag2).
3. Completed_Jobs: Jobs that will be closed that day. This should generally be min(Carryover_Jobs + Predicted_Jobs, Daily_Capacity).
4. Predicted_Total_Jobs: The active backlog remaining at the end of the day. Must EXACTLY equal: (Carryover_Jobs + Predicted_Jobs - Completed_Jobs).

CRITICAL COMPLETENESS RULE:
You MUST include EVERY SINGLE service center (ASC_CODE) that appears in the historical context in your output. Do NOT skip or omit any service centers, even if their historical backlog is low.

Your Task:
Using the 7-day weather forecast, capacity data, and recent historical backlog context, predict the detailed metrics for each service center (ASC_CODE and ASC_NAME) for each day in the 7-day forecast.

Output format:
You MUST output a JSON object adhering exactly to the following structure:
{
  "seven_day_forecast": [
    {
      "day": "YYYY-MM-DD", (the exact forecast date string, e.g. 2026-06-03)
      "forecasts": [
        {
          "ASC_CODE": "string containing service code",
          "City": "city name",
          "Carryover_Jobs": carryover jobs (float),
          "Predicted_Jobs": incoming jobs (float),
          "Completed_Jobs": completed jobs (float),
          "Predicted_Total_Jobs": predicted total backlog (float)
        },
        ...
      ]
    },
    ...
  ]
}
Output language: Turkish."""

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10))
    def predict(self, historical_context: str, weather_forecast: str, capacity_data: str, multi_year_patterns: str, progress_callback=None) -> ForecasterOutput:
        if not client:
            raise ValueError("Gemini Client not initialized.")
            
        import pandas as pd
        import io
        import concurrent.futures
        
        # Try to run optimized parallel city-by-city forecasting
        try:
            hist_df = pd.read_json(io.StringIO(historical_context))
            weather_df = pd.read_json(io.StringIO(weather_forecast))
            capacity_df = pd.read_json(io.StringIO(capacity_data))
            
            # Ensure required columns exist
            if 'City' not in capacity_df.columns:
                raise ValueError("City column missing in capacity data JSON.")
                
            cities_list = list(capacity_df['City'].dropna().unique())
            batch_size = 2
            city_batches = [cities_list[i:i + batch_size] for i in range(0, len(cities_list), batch_size)]
            
            logger.info(f"Splitting forecasting into {len(city_batches)} batches (max {batch_size} cities/batch) to optimize AI credits.")
            
            def predict_batch(batch):
                batch_capacity = capacity_df[capacity_df['City'].isin(batch)]
                batch_hist = hist_df[hist_df['City'].isin(batch)]
                batch_weather = weather_df[weather_df['City'].isin(batch)]
                
                # Convert back to clean text tables for Gemini prompt readability
                batch_capacity_str = batch_capacity[['ASC_CODE', 'ASC_NAME', 'Daily_Capacity']].to_string(index=False)
                batch_hist_str = batch_hist.to_string(index=False) if not batch_hist.empty else "No recent history"
                batch_weather_str = batch_weather.to_string(index=False) if not batch_weather.empty else "No weather forecast"
                
                cities_str = ", ".join(batch)
                prompt = (
                    f"Historical Context for {cities_str}:\n{batch_hist_str}\n\n"
                    f"Capacity Data for {cities_str}:\n{batch_capacity_str}\n\n"
                    f"7-Day Weather Forecast for {cities_str}:\n{batch_weather_str}\n\n"
                    f"Multi-Year Historical Patterns:\n{multi_year_patterns}\n\n"
                    f"CRITICAL: You must include every single ASC_CODE shown in the capacity data above in your output.\n"
                    f"Please generate the forecast for the following cities: {cities_str}."
                )
                
                try:
                    response = client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=self.system_instruction,
                            response_mime_type="application/json",
                            response_schema=ForecasterOutput,
                            temperature=0.2,
                            thinking_config=types.ThinkingConfig(thinking_budget=1024),
                        ),
                    )
                    return cities_str, ForecasterOutput.model_validate_json(response.text)
                except Exception as e:
                    import traceback
                    logger.error(f"Error inside predict_batch: {e}")
                    logger.error(traceback.format_exc())
                    raise e

            results = {}
            import time
            total_batches = len(city_batches)
            for i, batch in enumerate(city_batches):
                batch_str = ", ".join(batch)
                if progress_callback:
                    progress_callback(f"Batch {i+1}/{total_batches} işleniyor ({batch_str})...", (i) / total_batches)
                try:
                    batch_name, output = predict_batch(batch)
                    results[batch_name] = output
                    time.sleep(2)  # Avoid rate limits and timeouts
                except Exception as exc:
                    logger.error(f"Batch {batch_str} forecast failed: {exc}")
                    raise exc

            # Merge results by day
            merged_days = {}
            for city_name, output in results.items():
                for daily in output.seven_day_forecast:
                    day = daily.day
                    if day not in merged_days:
                        merged_days[day] = []
                    merged_days[day].extend(daily.forecasts)
                    
            seven_day_forecast = []
            for day in sorted(merged_days.keys()):
                seven_day_forecast.append(DailyForecast(
                    day=day,
                    forecasts=merged_days[day]
                ))
                
            return ForecasterOutput(seven_day_forecast=seven_day_forecast)
            
        except Exception as e:
            logger.warning(f"Parallel forecasting failed or fallback triggered: {e}. Running legacy single-prompt forecasting...")
            
            prompt = f"Historical Context:\n{historical_context}\n\nCapacity Data:\n{capacity_data}\n\n7-Day Weather Forecast:\n{weather_forecast}\n\nMulti-Year Historical Patterns:\n{multi_year_patterns}\n\nPlease generate the forecast."
            
            logger.info("Calling legacy Forecaster Agent...")
            try:
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_instruction,
                        response_mime_type="application/json",
                        response_schema=ForecasterOutput,
                        temperature=0.2,
                        thinking_config=types.ThinkingConfig(thinking_budget=1024),
                    ),
                )
                return ForecasterOutput.model_validate_json(response.text)
            except Exception as e:
                import traceback
                logger.error(f"Error inside legacy predict: {e}")
                logger.error(traceback.format_exc())
                raise e


class WatchdogAgent:
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name

    def generate_risk_map(self, forecast_json: str, capacity_data: str) -> WatchdogOutput:
        logger.info("Watchdog Agent processing mathematically in Python...")
        try:
            forecast_data = json.loads(forecast_json)
            capacity_list = json.loads(capacity_data)
            
            # Map ASC_CODE to capacity details
            capacity_map = {}
            for item in capacity_list:
                code = str(item.get('ASC_CODE', '')).strip()
                city = str(item.get('City', '')).strip()
                team_qty = float(item.get('Team Quantity', 5))
                job_cap = float(item.get('Job Completion Capacity', 4.0))
                capacity_map[code] = {
                    'City': city,
                    'Daily_Capacity': team_qty * job_cap
                }
                
            seven_day_risk = []
            
            for daily_forecast in forecast_data.get('seven_day_forecast', []):
                day_str = daily_forecast.get('day', '')
                risk_map = []
                
                # Check for existing forecasts
                forecasts = daily_forecast.get('forecasts', [])
                
                for item in forecasts:
                    code = str(item.get('ASC_CODE', '')).strip()
                    city = str(item.get('City', '')).strip()
                    pred_jobs = int(round(float(item.get('Predicted_Total_Jobs', 0.0))))
                    
                    # Calculate capacity and status
                    cap_info = capacity_map.get(code, {'City': city, 'Daily_Capacity': 20.0})
                    daily_cap = cap_info['Daily_Capacity']
                    
                    inc_jobs = int(round(float(item.get('Predicted_Jobs', 0.0))))
                    
                    wait_days = pred_jobs / daily_cap if daily_cap > 0 else 7.0
                    kapasite_asimi = 'Evet' if pred_jobs > daily_cap else 'Hayır'
                    
                    if wait_days > 6.0:
                        durum = 'Kırmızı'
                    elif wait_days > 3.0:
                        durum = 'Sarı'
                    else:
                        durum = 'Yeşil'
                        
                    risk_map.append(WatchdogASCRisk(
                        ASC_CODE=code,
                        City=city,
                        Predicted_Total_Jobs=pred_jobs,
                        Predicted_Jobs=inc_jobs,
                        Durum=durum,
                        Kapasite_Asimi=kapasite_asimi
                    ))
                    
                # Add any missing service codes (completeness rule)
                existing_codes = {str(item.ASC_CODE).strip() for item in risk_map}
                for code, info in capacity_map.items():
                    if code not in existing_codes:
                        daily_cap = info['Daily_Capacity']
                        # Use average of other services in the city, or daily_cap * 0.5
                        city_jobs = [item.Predicted_Total_Jobs for item in risk_map if item.City == info['City']]
                        city_avg = int(round(sum(city_jobs) / len(city_jobs) if city_jobs else daily_cap * 0.5))
                        
                        city_inc = [item.Predicted_Jobs for item in risk_map if item.City == info['City']]
                        city_avg_inc = int(round(sum(city_inc) / len(city_inc) if city_inc else 0))
                        
                        wait_days = city_avg / daily_cap if daily_cap > 0 else 7.0
                        kapasite_asimi = 'Evet' if city_avg > daily_cap else 'Hayır'
                        
                        if wait_days > 6.0:
                            durum = 'Kırmızı'
                        elif wait_days > 3.0:
                            durum = 'Sarı'
                        else:
                            durum = 'Yeşil'
                            
                        risk_map.append(WatchdogASCRisk(
                            ASC_CODE=code,
                            City=info['City'],
                            Predicted_Total_Jobs=city_avg,
                            Predicted_Jobs=city_avg_inc,
                            Durum=durum,
                            Kapasite_Asimi=kapasite_asimi
                        ))
                        
                seven_day_risk.append(WatchdogDailyRisk(
                    day=day_str,
                    risk_map=risk_map
                ))
                
            return WatchdogOutput(seven_day_risk=seven_day_risk)
        except Exception as e:
            logger.error(f"Error calculating risk map locally in python: {e}")
            raise e


class CommanderAgent:
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name
        self.system_instruction = """You are the Operations Commander for Samsung's Marmara Region. Your objective is to minimize installation waiting times by strategically reallocating service teams across cities.

Inputs provided:
- Target Day: The day from which the transfer strategy should start.
- Watchdog Risk Map: Contains for each ASC: ASC_CODE, ASC_NAME, City, Predicted_Total_Jobs, Daily_Capacity (= Team Quantity * Job Completion Capacity), Durum (Kırmızı/Sarı/Yeşil - aligned with Map: <=3 Yeşil, <=6 Sarı, >6 Kırmızı), Kapasite_Asimi (Evet/Hayır), and Capacity_Surplus (= Daily_Capacity - Predicted_Total_Jobs).

Donor Identification Rules (CRITICAL):
- A service center is a DONOR if it has a positive Capacity_Surplus AND its Durum is 'Yeşil' AND Kapasite_Asimi is 'Hayır'.
- A service center with 'Sarı' status CANNOT be a donor unless its Capacity_Surplus is large enough that donating 1-2 teams would still keep it in 'Yeşil' or 'Sarı' status.
- Always prefer geographic proximity: suggest transfers between neighboring cities (e.g., Bursa → Tekirdağ, İstanbul → Kocaeli, Edirne → Tekirdağ).

Your Task & Operational Rules:
1. Identify all Receiver ASCs: Durum = 'Kırmızı' or 'Sarı', OR any ASC with Kapasite_Asimi = 'Evet'.
2. Identify all Donor ASCs: Yeşil status with meaningful surplus capacity (and Kapasite_Asimi = 'Hayır')
3. Propose SPECIFIC team transfers: [X] teams from [Donor ASC] to [Receiver ASC]
4. Block Deployment Rule: Transfers must be MINIMUM 3 consecutive days.
5. After each proposed transfer, recalculate the receiver's new daily backlog and estimate how many days until the queue returns to normal.
6. If a city has NO green donors nearby, say so explicitly and suggest hiring temporary contractors.

Output Format (MANDATORY EXACT STRUCTURE IN TURKISH):
Kritik Durumdaki veya Kapasite Aşımı Olan Servis Merkezleri (Alıcılar):
- [ŞEHİR] (ASC_CODE: [KOD] / [ASC_NAME]): [Durum] Durum, Kapasite Aşımı: [Kapasite_Asimi], Tahmini İş Yükü: [X], Günlük Kapasite: [Y], Kapasite Açığı: [Z].

Fazla Kapasiteli Servis Merkezleri (Donörler):
- [ŞEHİR] (ASC_CODE: [KOD] / [ASC_NAME]): [Durum] Durum, Kapasite Fazlası: [X]. Transfer edilebilir ekip: [Y] adet.

Taktiksel Emirler:
(For each needed transfer or external contractor need, list them like this:)
Gün [N] itibarıyla [X] adet ekibi [KOD/ŞEHİR/ASC_NAME] servisinden [KOD/ŞEHİR/ASC_NAME] servisine 3 günlüğüne kaydırın.
Beklenen etki: [Alıcı Servis] bekleme süresi [Eski] seviyesinden [Yeni] seviyesine inecektir.
Açıklama: [Neden bu transferi yaptığınızı açıklayın]

Gün [N] itibarıyla [ŞEHİR/ASC_NAME] şehrindeki kapasite açığı için dış kaynak (geçici yüklenici) desteği önerilir.
Gerekçe: [Yakınlarda yeşil donör bulunamadığını açıklayın]
"""

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_strategy(self, target_day: str, risk_map: str, threshold_days: float = 4.0) -> str:
        if not client:
            raise ValueError("Gemini Client not initialized.")
            
        prompt = (f"Target Day: {target_day}\n\n"
                  f"Watchdog Risk Map:\n{risk_map}\n\n"
                  f"CRITICAL RULE: If a service center can complete its backlog in less than {threshold_days} days "
                  f"(Predicted_Total_Jobs / Daily_Capacity < {threshold_days}), it DOES NOT need support. "
                  f"Do not allocate teams to it as a Receiver, even if its status is Kırmızı or Sarı.\n\n"
                  f"Please generate complete and actionable tactical orders using the exact required format.")
        
        logger.info("Calling Commander Agent...")
        response = client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_budget=1024),
            ),
        )
        return response.text
