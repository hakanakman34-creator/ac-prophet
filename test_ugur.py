import pandas as pd
from data_processor import load_and_preprocess_data

df = load_and_preprocess_data('Jobsdata_backup_old.xlsx', 'Istanbul_2023_Weather.xlsx')
print(df[df['ASC_CODE'].astype(str) == '3367743'].tail(10))
