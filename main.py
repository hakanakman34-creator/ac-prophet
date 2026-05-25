import logging
import json
import os
from data_processor import load_and_preprocess_data
from agents import ForecasterAgent, WatchdogAgent, CommanderAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    logger.info("--- Phase 1: Data Processing ---")
    df = load_and_preprocess_data('Jobsdata.xlsx', 'weatherdata.xlsx')
    
    # Take a sample of historical data for context (e.g. top days with high jobs vs temp)
    # We aggregate total jobs and avg temp per day across Marmara
    daily_stats = df.groupby('Tarih').agg({
        'Total_Jobs': 'sum',
        'Ortalama_Sicaklik': 'mean'
    }).reset_index().sort_values('Total_Jobs', ascending=False).head(10)
    
    historical_context_str = daily_stats.to_string(index=False)
    logger.info("Historical context generated (Top 10 highest demand days):\n" + historical_context_str)
    
    # Mocking a 7-day weather forecast (we take the last 7 unique days from weather data as a mock forecast)
    recent_forecast_df = df.groupby(['Tarih', 'Il']).agg({
        'Ortalama_Sicaklik': 'mean',
        'Maksimum_Sicaklik': 'mean'
    }).reset_index()
    last_7_days = recent_forecast_df['Tarih'].drop_duplicates().sort_values(ascending=False).head(7)
    forecast_df = recent_forecast_df[recent_forecast_df['Tarih'].isin(last_7_days)]
    forecast_str = forecast_df.to_string(index=False)
    logger.info("7-Day Forecast mock generated.")
    
    logger.info("\n--- Phase 2: Multi-Agent Execution ---")
    
    try:
        # 1. Forecaster Agent
        forecaster = ForecasterAgent()
        forecast_output = forecaster.predict(
            historical_context=historical_context_str,
            weather_forecast=forecast_str
        )
        forecast_json_str = forecast_output.model_dump_json(indent=2)
        logger.info(f"Forecaster Output:\n{forecast_json_str}")
        
        # 2. Watchdog Agent
        # Mock capacity data since it was not provided
        mock_capacity = "All ASCs have a capacity of 10 jobs per day. Assume any ASC predicted to have >10 jobs goes into 'Kırmızı' (Red) status."
        
        watchdog = WatchdogAgent()
        risk_map_str = watchdog.generate_risk_map(
            forecast_json=forecast_json_str,
            capacity_data=mock_capacity
        )
        logger.info(f"Watchdog Risk Map Output:\n{risk_map_str}")
        
        # 3. Commander Agent
        target_day = "Day 4"
        commander = CommanderAgent()
        tactical_orders = commander.generate_strategy(
            target_day=target_day,
            risk_map=risk_map_str
        )
        logger.info(f"Commander Tactical Orders:\n{tactical_orders}")
        
    except ValueError as ve:
        logger.error(f"Agent Execution aborted: {ve}. Please ensure GEMINI_API_KEY is configured in a .env file.")
    except Exception as e:
        logger.error(f"An error occurred during Agent Execution: {e}")

if __name__ == "__main__":
    main()
