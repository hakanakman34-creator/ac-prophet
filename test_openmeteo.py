"""
Open-Meteo API test script - mimics the exact call in app.py/data_processor.py
"""
import requests
import json
import time

cities = {
    'İSTANBUL': (41.0082, 28.9784),
    'TEKİRDAĞ': (41.2825, 27.5118),
}

for city, (lat, lon) in cities.items():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&past_days=14&daily=temperature_2m_max,temperature_2m_min,relative_humidity_2m_max&timezone=auto"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    print(f"\n--- Testing {city} ({lat}, {lon}) ---")
    print(f"URL: {url[:80]}...")
    
    try:
        start = time.time()
        res = requests.get(url, headers=headers, timeout=15)
        elapsed = time.time() - start
        
        print(f"Status Code: {res.status_code}")
        print(f"Response Time: {elapsed:.2f}s")
        print(f"Content-Type: {res.headers.get('Content-Type', 'N/A')}")
        print(f"Response Size: {len(res.text)} bytes")
        
        if res.status_code == 200:
            data = res.json()
            daily = data.get('daily', {})
            dates = daily.get('time', [])
            print(f"Dates returned: {len(dates)} days")
            if dates:
                print(f"Range: {dates[0]} -> {dates[-1]}")
        else:
            print(f"ERROR Response Body: {res.text[:500]}")
            
    except requests.exceptions.Timeout:
        print("ERROR: Request timed out after 15 seconds")
    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: Connection failed - {e}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
