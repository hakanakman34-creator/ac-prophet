import pandas as pd
from data_processor import load_marmara_services_config
import os
import streamlit as st

def get_recent_data():
    # replicate app.py logic
    df = pd.read_excel('Jobsdata_backup_old.xlsx')
    rename_map = {
        'Atanan Yeni İş': 'NEW_ASSIGNED_JOBS',
        'Devreden İş (Carryover)': 'CARRYOVER_JOBS',
        'İptal Edilen İş': 'CANCELLED_JOBS',
        'Tamamlanan İş': 'COMPLETED_JOBS',
        'Toplam İş (Backlog)': 'ACTIVE_BACKLOG'
    }
    df.rename(columns=rename_map, inplace=True)
    df.to_csv('scratch/temp_jobs.csv', index=False)
    
    from data_processor import load_and_preprocess_data
    df = load_and_preprocess_data('scratch/temp_jobs.csv', 'Istanbul_2023_Weather.xlsx')
    
    df['POSTING_DATE'] = pd.to_datetime(df['POSTING_DATE'])
    recent_data = df[df['POSTING_DATE'] >= df['POSTING_DATE'].max() - pd.Timedelta(days=10)].copy()
    print("Recent data size:", len(recent_data))
    print("UGUR data:", recent_data[recent_data['ASC_CODE'].astype(str) == '3367743'])
    
get_recent_data()
