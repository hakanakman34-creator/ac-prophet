import pandas as pd
import json
import logging
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class CapacityAgent:
    def __init__(self, model_name="gemini-2.5-flash"):
        self.model_name = model_name
        self.client = None
        try:
            self.client = genai.Client(http_options=types.HttpOptions(timeout=300000))
        except Exception as e:
            logger.warning("Could not initialize Gemini Client. Make sure GEMINI_API_KEY is set in .env")

        self.system_instruction = '''You are a Capacity Optimization Analyst for Samsung's Marmara Region HVAC operations.
Your job is to analyze historical performance and recommend adjustments to the 'Job Completion Capacity' for each service center.

Inputs:
1. Current Capacity Configuration (Team Quantity, current Job Completion Capacity)
2. Historical Performance (completed jobs per day over a period)

Rules:
1. Standard capacity is usually around 4.0 jobs per team per day.
2. If a service consistently completes significantly more jobs than their theoretical capacity (Team Quantity * Job Completion Capacity), recommend increasing their Job Completion Capacity.
3. If a service consistently completes significantly fewer jobs and has a high backlog (meaning they had work but couldn't do it), recommend decreasing their capacity.
4. If performance is close to current settings, recommend keeping it the same.
5. Provide a specific new recommended value for Job Completion Capacity.

Output Format: You MUST output a JSON array of objects.
[
  {
    "ASC_CODE": "service code",
    "ASC_NAME": "service name",
    "Current_Capacity": current float value,
    "Recommended_Capacity": new float value,
    "Reasoning": "Brief explanation for the change"
  }
]
'''

    def analyze_capacity(self, current_config: str, historical_data: str) -> str:
        if not self.client:
            raise ValueError("Gemini Client not initialized.")

        prompt = f"Current Configuration:\n{current_config}\n\nHistorical Performance Data:\n{historical_data}\n\nPlease analyze and provide recommendations."

        logger.info("Calling Capacity Agent...")
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            return response.text
        except Exception as e:
            logger.error(f"Error in Capacity Agent: {e}")
            raise e
