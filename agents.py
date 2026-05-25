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
    client = genai.Client(http_options=types.HttpOptions(timeout=300000))
except Exception as e:
    logger.warning("Could not initialize Gemini Client. Make sure GEMINI_API_KEY is set in .env")
    client = None

# Pydantic Schemas for Structured Output
class ASCForecast(BaseModel):
    ASC_CODE: str
    City: str
    Carryover_Jobs: float
    Incoming_Jobs: float
    Completed_Jobs: float
    Predicted_Total_Jobs: float

class DailyForecast(BaseModel):
    day: str
    forecasts: List[ASCForecast]

class ForecasterOutput(BaseModel):
    seven_day_forecast: List[DailyForecast]

# Watchdog structured schemas
class WatchdogASCRisk(BaseModel):
    ASC_CODE: str
    City: str
    Predicted_Total_Jobs: float
    Durum: str  # Kırmızı / Sarı / Yeşil

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
Historical Context Data: [POSTING_DATE, Haftanin_Gunu, City, ASC_NAME, Total_Jobs, Ortalama_Sicaklik, Hissedilen_Sicaklik, Hissedilen_Sicaklik_Lag1, Hissedilen_Sicaklik_Lag2, NEW_ASSIGNED_JOBS, CARRYOVER_JOBS, COMPLETED_JOBS]
Capacity Data: [ASC_CODE, City, Daily_Capacity]

CRITICAL RULES FOR DATA HANDLING:
The 'Total_Jobs' column in the historical data represents the ACTIVE_BACKLOG (the true queued work) for each specific service center (ASC_NAME) on that date.
Your prediction goal is to estimate the future daily breakdown for each service center over the next 7 days, based on their recent historical trends, the upcoming weather forecast, and their daily completion capacity.

CRITICAL FORECASTING LOGIC:
1. HEAT INDEX & LAG: Pay close attention to 'Hissedilen_Sicaklik' (Heat Index) and its lagged versions (Lag1: yesterday's heat index, Lag2: day before yesterday's heat index). A high heat index 1 or 2 days ago strongly drives an increase in 'Incoming_Jobs' today due to the delay between the purchasing decision and installation registration.
2. DAY OF WEEK: Pay attention to 'Haftanin_Gunu'. Weekends (Cumartesi, Pazar) typically show different patterns in both Incoming_Jobs and Completed_Jobs compared to weekdays.

For each day, you must predict:
1. Carryover_Jobs: The uncompleted jobs remaining from the PREVIOUS day. CRITICAL: Day 1 Carryover MUST equal the Last known Total_Jobs from history. For Day 2 to Day 7, Carryover_Jobs MUST EXACTLY equal the PREVIOUS day's Predicted_Total_Jobs. DO NOT reset this to 0!
2. Incoming_Jobs: New jobs expected to arrive on that day (expect a spike if the weather is getting hotter, especially considering Lag1 and Lag2).
3. Completed_Jobs: Jobs that will be closed that day. This should generally be min(Carryover_Jobs + Incoming_Jobs, Daily_Capacity).
4. Predicted_Total_Jobs: The active backlog remaining at the end of the day. Must EXACTLY equal: (Carryover_Jobs + Incoming_Jobs - Completed_Jobs).

CRITICAL COMPLETENESS RULE:
You MUST include EVERY SINGLE service center (ASC_CODE) that appears in the historical context in your output. Do NOT skip or omit any service centers, even if their historical backlog is low.

Your Task:
Using the 7-day weather forecast, capacity data, and recent historical backlog context, predict the detailed metrics for each service center (ASC_CODE and ASC_NAME) for each day in the 7-day forecast.
Output format:
Provide a JSON array formatted as [Day_1, Day_2, ..., Day_7]. Inside each day, list ASC_CODE, City, Carryover_Jobs, Incoming_Jobs, Completed_Jobs, and Predicted_Total_Jobs as floats/integers. Output language: Turkish."""

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
    def predict(self, historical_context: str, weather_forecast: str, capacity_data: str) -> ForecasterOutput:
        if not client:
            raise ValueError("Gemini Client not initialized.")
            
        prompt = f"Historical Context:\n{historical_context}\n\nCapacity Data:\n{capacity_data}\n\n7-Day Weather Forecast:\n{weather_forecast}\n\nPlease generate the forecast."
        
        logger.info("Calling Forecaster Agent...")
        response = client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                response_mime_type="application/json",
                response_schema=ForecasterOutput,
                temperature=0.2,
            ),
        )
        return ForecasterOutput.model_validate_json(response.text)


class WatchdogAgent:
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name
        self.system_instruction = """You are an expert Operations Risk Analyst for Samsung Turkey's Marmara HVAC service network.

Your Task:
For EVERY ASC in Capacity Data, calculate its daily risk for ALL 7 days:
- Daily Capacity = Team Quantity * Job Completion Capacity
- If Predicted_Total_Jobs > Daily Capacity: Durum = 'Kırmızı'
- If Predicted_Total_Jobs >= 0.75 * Daily Capacity: Durum = 'Sarı'
- Otherwise: Durum = 'Yeşil'

IMPORTANT: You MUST include EVERY SINGLE ASC from the Capacity Data in the output for EACH of the 7 days. Do NOT skip or omit any ASC. If no forecast data exists for an ASC, use its most recent predicted value or assign a conservative estimate based on the city average.
You MUST return a structured JSON object with a 'seven_day_risk' key containing a list of 7 daily objects. Each daily object has a 'day' field (CRITICAL: This MUST be the exact actual date string from the forecast data, e.g. '2026-05-24', do NOT use 'Gün 1') and a 'risk_map' list of ASC entries. Each ASC entry must have: ASC_CODE, City, Predicted_Total_Jobs (number), Durum (string: Kırmızı/Sarı/Yeşil)."""

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate_risk_map(self, forecast_json: str, capacity_data: str) -> WatchdogOutput:
        if not client:
            raise ValueError("Gemini Client not initialized.")

        prompt = f"Predicted Jobs:\n{forecast_json}\n\nCapacity Data:\n{capacity_data}\n\nGenerate the 7-day risk map."

        logger.info("Calling Watchdog Agent...")
        response = client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self.system_instruction,
                response_mime_type="application/json",
                response_schema=WatchdogOutput,
                temperature=0.2,
            ),
        )
        return WatchdogOutput.model_validate_json(response.text)


class CommanderAgent:
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name
        self.system_instruction = """You are the Operations Commander for Samsung's Marmara Region. Your objective is to minimize installation waiting times by strategically reallocating service teams across cities.

Inputs provided:
- Target Day: The day from which the transfer strategy should start.
- Watchdog Risk Map: Contains for each ASC: ASC_CODE, ASC_NAME, City, Predicted_Total_Jobs, Daily_Capacity (= Team Quantity * Job Completion Capacity), Durum (Kırmızı/Sarı/Yeşil), and Capacity_Surplus (= Daily_Capacity - Predicted_Total_Jobs).

Donor Identification Rules (CRITICAL):
- A service center is a DONOR if it has a positive Capacity_Surplus AND its Durum is 'Yeşil'.
- A service center with 'Sarı' status CANNOT be a donor unless its Capacity_Surplus is large enough that donating 1-2 teams would still keep it in 'Yeşil' or 'Sarı' status.
- Always prefer geographic proximity: suggest transfers between neighboring cities (e.g., Bursa → Tekirdağ, İstanbul → Kocaeli, Edirne → Tekirdağ).

Your Task & Operational Rules:
1. Identify all Receiver ASCs: Durum = 'Kırmızı' or 'Sarı'
2. Identify all Donor ASCs: Yeşil status with meaningful surplus capacity
3. Propose SPECIFIC team transfers: [X] teams from [Donor ASC] to [Receiver ASC]
4. Block Deployment Rule: Transfers must be MINIMUM 3 consecutive days.
5. After each proposed transfer, recalculate the receiver's new daily backlog and estimate how many days until the queue returns to normal.
6. If a city has NO green donors nearby, say so explicitly and suggest hiring temporary contractors.

Output Format (MANDATORY EXACT STRUCTURE IN TURKISH):
Kritik Durumdaki Servis Merkezleri (Alıcılar):
- [ŞEHİR] (ASC_CODE: [KOD] / [ASC_NAME]): [Durum] Durum, Tahmini İş Yükü: [X], Günlük Kapasite: [Y], Kapasite Açığı: [Z].

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
            ),
        )
        return response.text
