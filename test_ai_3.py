import json
from agents import ForecasterAgent

from test_prompt import batch_hist, batch_cap
from test_prompt import recent_data

cities_str = "ÇANAKKALE"
batch_hist_str = batch_hist.to_string(index=False)
batch_cap_str = batch_cap[['ASC_CODE', 'ASC_NAME', 'Daily_Capacity']].to_string(index=False)
weather_str = "Tarih, City, Ortalama_Sicaklik\n2026-06-29, ÇANAKKALE, 30.0\n"
patterns_str = "No patterns"

prompt = (
    f"Historical Context for {cities_str}:\n{batch_hist_str}\n\n"
    f"Capacity Data for {cities_str}:\n{batch_cap_str}\n\n"
    f"7-Day Weather Forecast for {cities_str}:\n{weather_str}\n\n"
    f"Multi-Year Historical Patterns:\n{patterns_str}\n\n"
    f"CRITICAL: You must include every single ASC_CODE shown in the capacity data above in your output.\n"
    f"Please generate the forecast for the following cities: {cities_str}."
)

agent = ForecasterAgent()
import google.genai.types as types
from agents import client, ForecasterOutput

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

for day in out.seven_day_forecast:
    print(day.day)
    for f in day.forecasts:
        print(f"  ASC_CODE: {f.ASC_CODE} - Pred: {f.Predicted_Jobs} - Total: {f.Predicted_Total_Jobs}")
