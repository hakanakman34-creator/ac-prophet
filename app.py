import streamlit as st
import pandas as pd
import plotly.express as px
import json
import logging
import os
from dotenv import load_dotenv
load_dotenv()
from data_processor import load_and_preprocess_data, load_marmara_services_config, save_marmara_services_config, fetch_future_weather, extract_multi_year_patterns
from agents import ForecasterAgent, WatchdogAgent, CommanderAgent, WatchdogOutput
from capacity_agent import CapacityAgent

# Streamlit configurations
st.set_page_config(
    page_title="Samsung HVAC Peak Season Operations Control",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (sleek premium theme matching)
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .metric-card {
        background: #1e222b;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #2e333d;
        margin-bottom: 10px;
    }
    .status-red {
        background-color: rgba(220, 53, 69, 0.2);
        color: #ff4d4d;
        border: 1px solid #ff4d4d;
        padding: 8px;
        border-radius: 5px;
    }
    .status-green {
        background-color: rgba(40, 167, 69, 0.2);
        color: #2beb6d;
        border: 1px solid #2beb6d;
        padding: 8px;
        border-radius: 5px;
    }
    .status-yellow {
        background-color: rgba(255, 193, 7, 0.2);
        color: #ffc107;
        border: 1px solid #ffc107;
        padding: 8px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- PASSWORD PROTECTION -----------------
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    # Center the login form using columns
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 20px; margin-top: 80px;">
            <img src="https://upload.wikimedia.org/wikipedia/commons/b/b4/Samsung_wordmark.svg" style="width: 180px; filter: brightness(0) invert(1); margin-bottom: 15px;"/>
            <h3 style="color: #ffffff; font-family: 'Inter', sans-serif; font-weight: 500; font-size: 22px; margin-bottom: 5px;">SETK CS</h3>
            <p style="color: #888888; font-size: 14px;">Marmara Peak Season Operations Center</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("Kullanıcı Adı", placeholder="Kullanıcı adınızı girin")
            password = st.text_input("Şifre", type="password", placeholder="Şifrenizi girin")
            submit = st.form_submit_button("Giriş Yap", use_container_width=True)
            
            if submit:
                env_user = os.environ.get("APP_USERNAME", "admin")
                env_pass = os.environ.get("APP_PASSWORD", "samsung2026")
                
                if username == env_user and password == env_pass:
                    st.session_state["password_correct"] = True
                    st.rerun()
                else:
                    st.error("❌ Kullanıcı adı veya şifre hatalı!")
                    
    return False

if not check_password():
    st.stop()

st.title("❄️ Samsung HVAC Peak Season Operations Center")
st.markdown("### Marmara Region Multi-Agent Forecasting & Dispatch Optimizer")

def load_service_district_map():
    map_path = 'service_district_map.json'
    if os.path.exists(map_path):
        with open(map_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@st.cache_data
def fetch_data_v2():
    return load_and_preprocess_data('Jobsdata.xlsx', 'weatherdata.xlsx')

@st.cache_data
def fetch_services_data_v2():
    # Load freshly to avoid stale cached configurations
    return load_marmara_services_config('ServiceList.xlsx')

try:
    df = fetch_data_v2()
    services_df = fetch_services_data_v2()
    service_district_map = load_service_district_map()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# ----------------- SIDEBAR CONTROLS -----------------
st.sidebar.markdown(
    """
    <div style="text-align: left; margin-bottom: 10px;">
        <img src="https://upload.wikimedia.org/wikipedia/commons/b/b4/Samsung_wordmark.svg" style="width: 150px; filter: brightness(0) invert(1);"/>
        <h2 style="margin-top: 10px; margin-bottom: 15px; color: #e0e0e0; font-family: sans-serif; font-weight: 600; letter-spacing: 0.5px; font-size: 18px;">SETK CS</h2>
    </div>
    <hr style="margin-top: 0px; margin-bottom: 20px; border: 0; border-top: 1px solid #2e333d;"/>
    """,
    unsafe_allow_html=True
)

# Target Day Selector
current_date = pd.Timestamp.today().normalize()
target_date_options = [(current_date + pd.Timedelta(days=i)).strftime('%Y-%m-%d') for i in range(0, 7)]

target_day_str = st.sidebar.selectbox(
    "Commander Target Day",
    options=target_date_options,
    index=0
)

st.sidebar.markdown("---")

run_button = st.sidebar.button("🚀 Run Multi-Agent Optimizer", width='stretch')

# ----------------- UI TABS -----------------
tab1, tab2, tab3 = st.tabs(["📊 Operations Dashboard", "📁 Data Management", "⚙️ Admin (Marmara Services)"])

with tab2:
    st.header("📁 Data Management")
    
    # Section 1: Manual Daily Entry
    st.subheader("1. Günlük Manuel Veri Girişi")
    entry_date = st.date_input("Kayıt Tarihi Seçin")
    
    if 'manual_entry_df' not in st.session_state or st.session_state.get('last_entry_date') != entry_date:
        target_date_str = entry_date.strftime("%Y-%m-%d")
        has_existing = False
        try:
            if os.path.exists('Jobsdata.xlsx'):
                existing_data = pd.read_excel('Jobsdata.xlsx')
                if not existing_data.empty:
                    # Clean and standardise POSTING_DATE format
                    existing_data['POSTING_DATE_clean'] = pd.to_datetime(existing_data['POSTING_DATE']).dt.strftime('%Y-%m-%d')
                    date_records = existing_data[existing_data['POSTING_DATE_clean'] == target_date_str].copy()
                    if not date_records.empty:
                        cols_needed = ["POSTING_DATE", "ASC_CODE", "ASC_NAME", "City", "Region", 
                                       "CARRYOVER_JOBS", "NEW_ASSIGNED_JOBS", "CANCELLED_JOBS", "COMPLETED_JOBS"]
                        for c in cols_needed:
                            if c not in date_records.columns:
                                date_records[c] = 0 if c.endswith('JOBS') else ("İSTANBUL" if c == "Region" else "")
                        
                        active_codes = set(services_df['ASC_CODE'].dropna().astype(int).tolist())
                        date_records['ASC_CODE'] = date_records['ASC_CODE'].astype(int)
                        date_records = date_records[date_records['ASC_CODE'].isin(active_codes)]
                        
                        if not date_records.empty:
                            date_records['POSTING_DATE'] = target_date_str
                            st.session_state['manual_entry_df'] = date_records[cols_needed].reset_index(drop=True)
                            has_existing = True
        except Exception as e:
            logging.error(f"Error loading existing data for entry: {e}")

        if not has_existing:
            # Initialize with default zeros for this date
            entry_data = []
            for _, row in services_df.iterrows():
                entry_data.append({
                    "POSTING_DATE": target_date_str,
                    "ASC_CODE": int(row.get("ASC_CODE", 0)),
                    "ASC_NAME": row.get("ASC_NAME", ""),
                    "City": row.get("City", ""),
                    "Region": "İSTANBUL",
                    "CARRYOVER_JOBS": 0,
                    "NEW_ASSIGNED_JOBS": 0,
                    "CANCELLED_JOBS": 0,
                    "COMPLETED_JOBS": 0
                })
            st.session_state['manual_entry_df'] = pd.DataFrame(entry_data)
        st.session_state['last_entry_date'] = entry_date
        
    st.markdown("Aşağıdaki tabloya günlük verilerinizi girin. *ACTIVE_BACKLOG* otomatik hesaplanarak kaydedilecektir.")
    edited_entry_df = st.data_editor(st.session_state['manual_entry_df'], width='stretch', hide_index=True)
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("💾 Günlük Veriyi Kaydet", use_container_width=True):
            try:
                # Calculate ACTIVE_BACKLOG (cap negative values to 0)
                edited_entry_df['ACTIVE_BACKLOG'] = ((edited_entry_df['CARRYOVER_JOBS'] + edited_entry_df['NEW_ASSIGNED_JOBS']) - (edited_entry_df['CANCELLED_JOBS'] + edited_entry_df['COMPLETED_JOBS'])).clip(lower=0)
                
                existing_data = pd.read_excel('Jobsdata.xlsx')
                
                # Format existing POSTING_DATE column cleanly
                existing_data['POSTING_DATE_clean'] = pd.to_datetime(existing_data['POSTING_DATE']).dt.strftime('%Y-%m-%d')
                target_date_str = pd.to_datetime(entry_date).strftime('%Y-%m-%d')
                
                # Filter out the existing records for this target date
                existing_data = existing_data[existing_data['POSTING_DATE_clean'] != target_date_str].copy()
                existing_data.drop(columns=['POSTING_DATE_clean'], errors='ignore', inplace=True)
                
                # Ensure the entry date matches exactly
                edited_entry_df['POSTING_DATE'] = target_date_str
                
                # Combine existing and new data
                combined_data = pd.concat([existing_data, edited_entry_df], ignore_index=True)
                combined_data.to_excel('Jobsdata.xlsx', index=False)
                
                st.success(f"✅ {entry_date} tarihi için veriler başarıyla güncellendi!")
                st.cache_data.clear()
                
                st.session_state['manual_entry_df'] = edited_entry_df.copy()
                st.rerun()
            except Exception as e:
                st.error(f"Kayıt hatası: {e}")
                
    with col_btn2:
        try:
            # Prepare download data matching the template structure (cap negative values to 0)
            download_df = edited_entry_df.copy()
            download_df['ACTIVE_BACKLOG'] = ((download_df['CARRYOVER_JOBS'] + download_df['NEW_ASSIGNED_JOBS']) - (download_df['CANCELLED_JOBS'] + download_df['COMPLETED_JOBS'])).clip(lower=0)
            
            # Reorder columns to match the template exactly
            cols_order = ['POSTING_DATE', 'ASC_CODE', 'ASC_NAME', 'City', 'Region', 'CARRYOVER_JOBS', 'NEW_ASSIGNED_JOBS', 'CANCELLED_JOBS', 'COMPLETED_JOBS', 'ACTIVE_BACKLOG']
            for col in cols_order:
                if col not in download_df.columns:
                    if col == 'Region':
                        download_df['Region'] = 'İSTANBUL'
                    else:
                        download_df[col] = 0
            download_df = download_df[cols_order]
            
            # Generate Excel bytes in memory
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                download_df.to_excel(writer, index=False, sheet_name='JobsData')
            buffer.seek(0)
            
            st.download_button(
                label="📥 Tabloyu Excel (.xlsx) Olarak İndir",
                data=buffer,
                file_name=f"manual_veri_girisi_{entry_date.strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Excel indirme dosyası hazırlanırken hata oluştu: {e}")
            
    st.markdown("---")
    
    # Section 2: Upload Excel
    st.subheader("2. Toplu Excel Yükleme")
    st.markdown("Hazırlanan yeni şablona uygun toplu verileri `.xls` veya `.xlsx` olarak yükleyebilirsiniz.")
    uploaded_file = st.file_uploader("Excel Dosyası Seçin", type=['xls', 'xlsx'])
    if uploaded_file is not None:
        try:
            new_data = pd.read_excel(uploaded_file)
            st.success("Dosya okundu! Önizleme:")
            st.dataframe(new_data, width='stretch')
            if st.button("Tarihçeye Ekle (Append)"):
                try:
                    existing_data = pd.read_excel('Jobsdata.xlsx')
                    combined_data = pd.concat([existing_data, new_data], ignore_index=True)
                    combined_data.to_excel('Jobsdata.xlsx', index=False)
                    st.success("✅ Yüklenen veri başarıyla eklendi!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Ekleme hatası: {e}")
        except Exception as e:
            st.error(f"Dosya okuma hatası: {e}")



with tab3:
    st.header("⚙️ Admin: Service Centers & Capacities")
    
    st.subheader("🛠️ Commander Agent Ayarları")
    st.number_input(
        "Commander Destek İhtiyacı Eşiği (Gün)", 
        min_value=1.0, max_value=14.0, value=4.0, step=0.5,
        key="commander_threshold",
        help="Eğer bir servisin tahmini bekleme süresi bu gün sayısının altındaysa, Commander o servisin destek ihtiyacı olmadığını varsayar."
    )
    
    st.markdown("Edit team quantities and individual completion capacities for each ASC. Changes will automatically update predictions.")
    
    if 'Job Completion Capacity' in services_df.columns:
        services_df['Job Completion Capacity'] = services_df['Job Completion Capacity'].astype(float)

    edited_services_df = st.data_editor(
        services_df, 
        width='stretch',
        num_rows="dynamic"
    )
    
    if st.button("💾 Save Configurations"):
        try:
            save_marmara_services_config(edited_services_df)
            st.success("✅ Configurations successfully saved!")
            st.cache_data.clear() # Clear cache so changes reflect on reload
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save configurations: {e}")

    st.markdown("---")
    st.subheader("🔍 Yapay Zeka ile Kapasite Optimizasyonu")
    st.markdown("Mevcut kapasite ayarlarını ve son dönem (7 günlük) gerçekleşen iş bitirme performansını analiz ederek, günlük kişi başı kapasite hedeflerinde (Job Completion Capacity) artış/azalış önerilerini alın.")
    
    if st.button("🔍 Kapasite Optimizasyon Analizi Başlat", type="primary"):
        with st.spinner("⏳ Capacity Agent verileri inceliyor... Lütfen bekleyin."):
            try:
                # Prepare data for CapacityAgent
                current_config_str = edited_services_df[['ASC_CODE', 'ASC_NAME', 'Team Quantity', 'Job Completion Capacity']].to_string(index=False)
                
                # Fetch recent history (last 7 days of actual completion)
                history_df = pd.read_excel('Jobsdata.xlsx')
                history_df['POSTING_DATE'] = pd.to_datetime(history_df['POSTING_DATE'])
                recent_history = history_df[history_df['Region'] == 'İSTANBUL'].sort_values('POSTING_DATE', ascending=False)
                recent_7_days = recent_history.head(1000) # Give enough context
                
                # Aggregate total completions per service over this period
                perf_summary = recent_7_days.groupby(['ASC_CODE', 'ASC_NAME'])[['COMPLETED_JOBS', 'ACTIVE_BACKLOG']].sum().reset_index()
                perf_summary_str = perf_summary.to_string(index=False)
                
                capacity_agent = CapacityAgent()
                recommendations_json = capacity_agent.analyze_capacity(current_config_str, perf_summary_str)
                
                st.session_state['capacity_recommendations'] = json.loads(recommendations_json)
                st.success("✅ Analiz tamamlandı!")
            except Exception as e:
                st.error(f"Kapasite analizi sırasında hata oluştu: {e}")

    if 'capacity_recommendations' in st.session_state:
        recs = st.session_state['capacity_recommendations']
        if recs:
            st.markdown("#### Yapay Zeka Kapasite Önerileri")
            recs_df = pd.DataFrame(recs)
            st.dataframe(recs_df, use_container_width=True)
            
            st.warning("⚠️ Önerileri uygulamak için tablodan 'Job Completion Capacity' değerlerini manuel olarak güncelleyip yukarıdan 'Save Configurations' butonuna basınız.")
        else:
            st.info("Değişiklik önerilmedi.")
            
    st.markdown("---")
    st.header("🗺️ Service District Mapping")
    st.markdown("Aşağıdaki tablodan ilçelere atanan servisleri (`ATANAN_ASC_CODE` ve `ATANAN_ASC_ADI`) doğrudan güncelleyebilirsiniz. Değişiklikleriniz haritaya otomatik yansıyacaktır.")
    
    district_file_path = 'marmara_ilce_listesi.xlsx'
    try:
        if os.path.exists(district_file_path):
            dist_df = pd.read_excel(district_file_path)
            edited_dist_df = st.data_editor(dist_df, width='stretch', key='district_editor', num_rows="dynamic")
            
            if st.button("💾 İlçe-Servis Eşleşmesini Kaydet ve Uygula"):
                # Save to excel
                edited_dist_df.to_excel(district_file_path, index=False)
                
                # Apply to json
                dist_map = {}
                for _, row in edited_dist_df.iterrows():
                    asc_code = str(row.get('ATANAN_ASC_CODE', '')).strip()
                    if asc_code and asc_code != 'nan' and asc_code != 'None':
                        if asc_code not in dist_map:
                            dist_map[asc_code] = {"ASC_ADI": row.get('ATANAN_ASC_ADI', ''), "ilceler": []}
                        dist_map[asc_code]["ilceler"].append(row.get('İLÇE', ''))
                
                with open('service_district_map.json', 'w', encoding='utf-8') as f:
                    json.dump(dist_map, f, ensure_ascii=False, indent=2)
                    
                st.success(f"✅ Başarıyla {len(dist_map)} servise ilçe eşleşmeleri kaydedildi ve uygulandı!")
                st.cache_data.clear()
                st.rerun()
        else:
            st.warning("`marmara_ilce_listesi.xlsx` dosyası bulunamadı.")
            
    except Exception as e:
        st.error(f"Eşleşme dosyası yüklenirken hata oluştu: {e}")

    st.markdown("---")
    with st.expander("📂 Alternatif: Yeni Excel Listesi Yükle"):
        st.markdown("Eğer sıfırdan yeni bir ilçe listesi şablonu yüklemek isterseniz buradan yükleyebilirsiniz.")
        district_file = st.file_uploader("Excel Dosyası Yükle", type=['xls', 'xlsx'])
        if district_file:
            try:
                new_dist_df = pd.read_excel(district_file)
                st.dataframe(new_dist_df.head(), width='stretch')
                if st.button("Bu Dosyayı Varsayılan Olarak Ayarla ve Uygula"):
                    new_dist_df.to_excel(district_file_path, index=False)
                    dist_map = {}
                    for _, row in new_dist_df.iterrows():
                        asc_code = str(row.get('ATANAN_ASC_CODE', '')).strip()
                        if asc_code and asc_code != 'nan' and asc_code != 'None':
                            if asc_code not in dist_map:
                                dist_map[asc_code] = {"ASC_ADI": row.get('ATANAN_ASC_ADI', ''), "ilceler": []}
                            dist_map[asc_code]["ilceler"].append(row.get('İLÇE', ''))
                    
                    with open('service_district_map.json', 'w', encoding='utf-8') as f:
                        json.dump(dist_map, f, ensure_ascii=False, indent=2)
                        
                    st.success("✅ Yeni dosya kaydedildi ve uygulandı!")
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.error(f"Dosya okuma hatası: {e}")
            
    st.markdown("---")
    with st.expander("🛠️ Gelişmiş: Geçmiş Veri Düzenleyici (Data Fixer)"):
        st.warning("⚠️ **HAYATİ UYARI:** Bu alan yalnızca geçmiş veri girişindeki hataları düzeltmek veya veri tabanını manuel ameliyat etmek için kullanılmalıdır. Günlük operasyonel girişler için lütfen **'📁 Data Management'** sekmesini kullanın.")
        st.markdown("`Jobsdata.xlsx` içindeki tüm veriyi doğrudan düzenleyip anormallikleri düzeltebilirsiniz.")
        try:
            history_df = pd.read_excel('Jobsdata.xlsx')
            edited_history_df = st.data_editor(history_df, width='stretch', key="history_editor")
            if st.button("💾 Tüm Değişiklikleri Excel'e Kaydet"):
                edited_history_df.to_excel('Jobsdata.xlsx', index=False)
                st.success("✅ Geçmiş veriler başarıyla güncellendi!")
                st.cache_data.clear()
        except Exception as e:
            st.error(f"Geçmiş veriler yüklenemedi: {e}")
            
with tab1:
    # ----------------- DATA PRESENTATION -----------------
    st.subheader("🌦️ 7-Day Marmara Weather Forecast")
    
    try:
        cities_list = services_df['City'].dropna().unique().tolist()
        # Ensure Bilecik is included in the weather forecast list
        has_bilecik = any(str(c).upper() in ["BİLECİK", "BILECIK"] for c in cities_list)
        if not has_bilecik:
            cities_list.append("BİLECİK")
            
        forecast_df = fetch_future_weather(cities_list)
        
        if not forecast_df.empty:
            # Dropdown to filter by city
            st.markdown("### 🔍 İl Bazlı Sıcaklık Detayları")
            unique_forecast_cities = sorted(forecast_df['City'].unique())
            selected_city = st.selectbox(
                "Görüntülenecek İli Seçin:",
                options=["Tüm İller"] + unique_forecast_cities,
                index=0,
                key="weather_city_filter"
            )
            
            if selected_city != "Tüm İller":
                filtered_forecast_df = forecast_df[forecast_df['City'] == selected_city]
                chart_title = f"Predicted Average Temperature - {selected_city}"
            else:
                filtered_forecast_df = forecast_df
                chart_title = "Predicted Average Temperature by City"
                
            col1, col2 = st.columns([1, 1.5])
            with col1:
                st.dataframe(filtered_forecast_df, width='stretch', hide_index=True)
            with col2:
                fig_weather = px.line(
                    filtered_forecast_df, x="Tarih", y="Ortalama_Sicaklik", color="City",
                    title=chart_title,
                    labels={"Tarih": "Date", "Ortalama_Sicaklik": "Avg Temp (°C)"},
                    template="plotly_white"
                )
                fig_weather.update_layout(height=400)
                st.plotly_chart(fig_weather, width='stretch')
        else:
            st.warning("Forecast data is currently unavailable.")
    except Exception as e:
        st.warning(f"Failed to load forecast data: {e}")

    # ----------------- PIPELINE EXECUTION -----------------
    if run_button:
        # Check for Gemini API key
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            try:
                if st.secrets.get("GEMINI_API_KEY"):
                    gemini_key = st.secrets.get("GEMINI_API_KEY")
            except Exception:
                pass
        if not gemini_key:
            st.error("🔑 Gemini API Key is missing! Please configure it or add it to `.env` file.")
            st.stop()

        # Clear previous session results before new run
        st.session_state['pipeline_completed'] = False
        for key in ['pipeline_map_df', 'pipeline_geo_data', 'pipeline_tactical_orders', 'pipeline_forecast_df']:
            st.session_state.pop(key, None)

        with st.spinner("⏳ Forecaster correlate-predicting..."):
            cities_list = services_df['City'].dropna().unique().tolist()
            # Ensure Bilecik is included in the weather forecast list
            has_bilecik = any(str(c).upper() in ["BİLECİK", "BILECIK"] for c in cities_list)
            if not has_bilecik:
                cities_list.append("BİLECİK")
                
            forecast_df = fetch_future_weather(cities_list)
            
            if forecast_df.empty:
                st.warning("Could not fetch future weather. Please check your connection.")
                st.stop()
                
            # Combine history and forecast to calculate lags for the future
            last_2_days = df[['POSTING_DATE', 'City', 'Hissedilen_Sicaklik']].drop_duplicates().sort_values(by=['City', 'POSTING_DATE'])
            last_2_days = last_2_days.groupby('City').tail(2)
            last_2_days.rename(columns={'POSTING_DATE': 'Tarih'}, inplace=True)
            last_2_days['Tarih'] = last_2_days['Tarih'].astype(str)
            
            f_temp = forecast_df[['Tarih', 'City', 'Hissedilen_Sicaklik']].copy()
            f_temp['Tarih'] = f_temp['Tarih'].astype(str)
            
            combined_w = pd.concat([last_2_days, f_temp]).sort_values(by=['City', 'Tarih']).reset_index(drop=True)
            combined_w['Hissedilen_Sicaklik_Lag1'] = combined_w.groupby('City')['Hissedilen_Sicaklik'].shift(1)
            combined_w['Hissedilen_Sicaklik_Lag2'] = combined_w.groupby('City')['Hissedilen_Sicaklik'].shift(2)
            
            # Merge lags back into forecast_df
            forecast_df = pd.merge(forecast_df, combined_w[['Tarih', 'City', 'Hissedilen_Sicaklik_Lag1', 'Hissedilen_Sicaklik_Lag2']], on=['Tarih', 'City'], how='left')
            forecast_json_payload = forecast_df.to_json(orient='records', force_ascii=False)
            
            recent_days = sorted(df['POSTING_DATE'].unique())[-7:]
            recent_data = df[df['POSTING_DATE'].isin(recent_days)].copy()
            
            # Ensure the required columns exist, fill with 0 if they don't
            for col in ['NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS']:
                if col not in recent_data.columns:
                    recent_data[col] = 0
                    
            cols_to_keep = ['POSTING_DATE', 'Haftanin_Gunu', 'City', 'ASC_CODE', 'ASC_NAME', 'Total_Jobs', 
                            'Ortalama_Sicaklik', 'Hissedilen_Sicaklik', 'Hissedilen_Sicaklik_Lag1', 'Hissedilen_Sicaklik_Lag2',
                            'NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS']
            
            # Gracefully handle missing columns in case of old data
            for c in cols_to_keep:
                if c not in recent_data.columns:
                    recent_data[c] = ""
                    
            # Critical columns that must not be NaN to have a valid record
            critical_cols = ['POSTING_DATE', 'Haftanin_Gunu', 'City', 'ASC_CODE', 'ASC_NAME', 'Total_Jobs', 
                             'NEW_ASSIGNED_JOBS', 'CARRYOVER_JOBS', 'COMPLETED_JOBS']
            recent_data = recent_data[cols_to_keep].dropna(subset=critical_cols).copy()
            
            # Fill missing weather data with reasonable default values (e.g., 25 degrees) to prevent empty prompt
            weather_cols = ['Ortalama_Sicaklik', 'Hissedilen_Sicaklik', 'Hissedilen_Sicaklik_Lag1', 'Hissedilen_Sicaklik_Lag2']
            for wc in weather_cols:
                if wc in recent_data.columns:
                    recent_data[wc] = recent_data[wc].fillna(25.0)
                    
            historical_context_json_payload = recent_data.to_json(orient='records', force_ascii=False)
            
            try:
                # 1. Forecaster Agent
                capacity_info = edited_services_df[['ASC_CODE', 'ASC_NAME', 'City', 'Team Quantity', 'Job Completion Capacity']].copy()
                capacity_info['Daily_Capacity'] = capacity_info['Team Quantity'] * capacity_info['Job Completion Capacity']
                capacity_str = capacity_info[['ASC_CODE', 'ASC_NAME', 'City', 'Daily_Capacity']].to_json(orient='records', force_ascii=False)
                
                forecaster = ForecasterAgent()
                patterns_str = extract_multi_year_patterns('Jobsdata_backup_old.xlsx')
                
                forecast_output = forecaster.predict(
                    historical_context=historical_context_json_payload,
                    weather_forecast=forecast_json_payload,
                    capacity_data=capacity_str,
                    multi_year_patterns=patterns_str
                )
                forecast_json_str = forecast_output.model_dump_json(indent=2)
                
                # Build Forecaster dataframe for display
                forecast_rows = []
                
                # Robust helper to clean and normalize ASC_CODE types
                def clean_code(val):
                    try:
                        return str(int(float(val)))
                    except:
                        return str(val).strip()
                        
                # Also build an ASC name lookup for the table
                asc_lookup = {clean_code(row['ASC_CODE']): row.get('ASC_NAME', f"Servis {row['ASC_CODE']}") for _, row in edited_services_df.iterrows()}
                
                for daily in forecast_output.seven_day_forecast:
                    for item in daily.forecasts:
                        forecast_rows.append({
                            'Tarih': daily.day,
                            'Servis Adı': asc_lookup.get(clean_code(item.ASC_CODE), f"Servis {item.ASC_CODE}"),
                            'Carryover İş Adedi': item.Carryover_Jobs,
                            'Gelmesi Beklenen İş Adedi': item.Incoming_Jobs,
                            'Kapatılması Beklenen İş Adedi': item.Completed_Jobs,
                            "Backlog'a Düşecek İş Adedi": item.Predicted_Total_Jobs
                        })
                
                st.session_state['pipeline_forecast_df'] = pd.DataFrame(forecast_rows)
                st.success("🤖 **Forecaster Agent Completed**")

                # 2. Watchdog Agent
                with st.spinner("⏳ Watchdog calculating Risk Map..."):
                    # Watchdog needs Team Quantity and Job Completion Capacity
                    watchdog_capacity_str = capacity_info[['ASC_CODE', 'City', 'Team Quantity', 'Job Completion Capacity']].to_json(orient='records', force_ascii=False)
                    watchdog = WatchdogAgent()
                    risk_output = watchdog.generate_risk_map(
                        forecast_json=forecast_json_str,
                        capacity_data=watchdog_capacity_str
                    )

                    # POST-WATCHDOG FALLBACK
                    all_asc_codes = {str(row['ASC_CODE']): row for _, row in edited_services_df.iterrows()}
                    for daily_risk in risk_output.seven_day_risk:
                        existing_codes = {str(item.ASC_CODE) for item in daily_risk.risk_map}
                        for asc_code, row in all_asc_codes.items():
                            if asc_code not in existing_codes:
                                daily_cap = row.get('Team Quantity', 5) * row.get('Job Completion Capacity', 4)
                                city_avg = next(
                                    (item.Predicted_Total_Jobs for item in daily_risk.risk_map
                                     if str(item.City).strip().upper() in str(row.get('City', '')).upper()
                                     or str(row.get('City', '')).upper() in str(item.City).strip().upper()),
                                    daily_cap * 0.5
                                )
                                durum = 'Kırmızı' if city_avg > daily_cap else ('Sarı' if city_avg >= 0.75 * daily_cap else 'Yeşil')
                                from agents import WatchdogASCRisk
                                daily_risk.risk_map.append(WatchdogASCRisk(
                                    ASC_CODE=asc_code,
                                    City=str(row.get('City', '')),
                                    Predicted_Total_Jobs=int(round(city_avg)),
                                    Durum=durum
                                ))

                    st.success("🤖 **Watchdog Agent Completed**")

                    # Build district-level map_df
                    try:
                        with open(r'marmara_ilce_geojson.json', 'r', encoding='utf-8') as f:
                            geo_data = json.load(f)
                    except Exception as e:
                        st.error(f"Failed to load district GeoJSON: {e}")
                        geo_data = {"type": "FeatureCollection", "features": []}

                    all_ilceler = [feat['properties']['ilce'] for feat in geo_data.get('features', [])]
                    daily_capacities = {}
                    for _, row in edited_services_df.iterrows():
                        daily_capacities[str(row['ASC_CODE'])] = row.get('Team Quantity', 5) * row.get('Job Completion Capacity', 4)

                    district_records = []
                    for daily_risk in risk_output.seven_day_risk:
                        day_label = daily_risk.day
                        day_records = {ilce: {'Day': day_label, 'ILCE': ilce, 'WaitDays': -1.0, 'Service': 'Atanmamış'} for ilce in all_ilceler}
                        for item in daily_risk.risk_map:
                            asc_code = str(item.ASC_CODE)
                            predicted_jobs = item.Predicted_Total_Jobs
                            capacity = daily_capacities.get(asc_code, 20)
                            wait_days = max(0.0, predicted_jobs / capacity) if capacity > 0 else 7.0
                            if asc_code in service_district_map:
                                mapping = service_district_map[asc_code]
                                service_name = mapping.get('ASC_ADI', asc_code)
                                for ilce in mapping.get('ilceler', []):
                                    if ilce in day_records:
                                        current_wait = day_records[ilce]['WaitDays']
                                        if current_wait == -1.0 or wait_days > current_wait:
                                            day_records[ilce]['WaitDays'] = round(wait_days, 1)
                                            day_records[ilce]['Service'] = service_name
                        district_records.extend(list(day_records.values()))

                    map_df = pd.DataFrame(district_records)
                    def _map_wait_label(wd):
                        if wd < 0: return '⬜ Veri Yok'
                        if wd <= 3: return f'🟢 {wd} Gün'
                        if wd <= 6: return f'🟡 {wd} Gün'
                        return f'🔴 {wd} Gün'
                    map_df['Durum'] = map_df['WaitDays'].apply(_map_wait_label)
                    map_df['Durum'] = map_df['WaitDays'].apply(_map_wait_label)
                    map_df = map_df.sort_values('Day')

                    # SAVE TO SESSION STATE
                    st.session_state['pipeline_map_df'] = map_df
                    st.session_state['pipeline_geo_data'] = geo_data

                # 3. Commander Agent
                with st.spinner("⏳ Commander formulating Dispatch strategy..."):
                    cap_lookup = {str(row['ASC_CODE']): row for _, row in edited_services_df.iterrows()}
                    enriched_risk = risk_output.model_dump()
                    
                    filtered_daily_risk = None
                    
                    for daily in enriched_risk.get('seven_day_risk', []):
                        if str(daily.get('day', '')).strip() == str(target_day_str).strip():
                            for item in daily.get('risk_map', []):
                                asc_code = str(item.get('ASC_CODE', ''))
                                if asc_code in cap_lookup:
                                    row = cap_lookup[asc_code]
                                    daily_cap = row.get('Team Quantity', 5) * row.get('Job Completion Capacity', 4)
                                    item['ASC_NAME'] = str(row.get('ASC_NAME', 'Bilinmeyen Servis'))
                                    item['Daily_Capacity'] = daily_cap
                                    item['Capacity_Surplus'] = round(daily_cap - item.get('Predicted_Total_Jobs', 0), 1)
                            filtered_daily_risk = daily
                            break
                            
                    import json as _json
                    enriched_risk_str = _json.dumps(filtered_daily_risk, ensure_ascii=False, indent=2) if filtered_daily_risk else "No data for target day"

                    commander_threshold = st.session_state.get('commander_threshold', 4.0)
                    commander = CommanderAgent()
                    tactical_orders = commander.generate_strategy(
                        target_day=target_day_str,
                        risk_map=enriched_risk_str,
                        threshold_days=commander_threshold
                    )
                    # SAVE TO SESSION STATE
                    st.session_state['pipeline_tactical_orders'] = tactical_orders
                    st.session_state['pipeline_completed'] = True

            except Exception as api_err:
                st.error(f"Failed to execute LLM Agents: {api_err}")
                st.info("Ensure your API key in `.env` is valid and has sufficient quota.")

    # RENDER FROM SESSION STATE — persists across all widget interactions
    if st.session_state.get('pipeline_completed', False) and 'pipeline_map_df' in st.session_state and 'pipeline_geo_data' in st.session_state:
        map_df = st.session_state['pipeline_map_df']
        geo_data = st.session_state['pipeline_geo_data']

        st.markdown("---")
        st.header("⚡ Multi-Agent Pipeline Output")
        st.subheader("🛡️ Risk Map Visualizer")

        ordered_days = map_df.drop_duplicates('Day').sort_values('Day')['Day'].tolist()

        color_scale = [
            [0.0, '#cccccc'],
            [0.05, '#a8f0a8'],
            [0.25, '#2ea82e'],
            [0.4, '#1a6e1a'],
            [0.55, '#ffef5e'],
            [0.7, '#ffbc2e'],
            [0.85, '#ff8c00'],
            [1.0, '#ff3300']
        ]

        # Use Plotly's native animation frame with Play button
        fig_map = px.choropleth(
            map_df,
            geojson=geo_data,
            locations='ILCE',
            featureidkey='id',
            color='WaitDays',
            animation_frame='Day',
            category_orders={'Day': ordered_days},
            hover_name='ILCE',
            hover_data={'Day': False, 'ILCE': False, 'WaitDays': True, 'Service': True, 'Durum': True},
            color_continuous_scale=color_scale,
            range_color=[-1, 8],
            title="🗺️ 7-Günlük İlçe Bazlı Hizmet Bekleme Günü Tahmini",
            projection="mercator"
        )
        
        # Lock bounds so map doesn't zoom out across frames
        fig_map.update_geos(
            visible=False,
            lonaxis=dict(range=[25.5, 32.0]),
            lataxis=dict(range=[39.4, 42.2])
        )
        
        # Ensure every animation frame also locks the geo layout
        for frame in fig_map.frames:
            frame.layout = dict(
                geo=dict(
                    visible=False,
                    lonaxis=dict(range=[25.5, 32.0]),
                    lataxis=dict(range=[39.4, 42.2])
                )
            )

        fig_map.update_layout(
            template='plotly_dark',
            paper_bgcolor='rgba(14,17,23,1)',
            plot_bgcolor='rgba(14,17,23,1)',
            margin={"r": 0, "t": 50, "l": 0, "b": 0},
            coloraxis_colorbar=dict(
                title="Bekleme<br>Günü",
                tickvals=[0, 3, 5, 8],
                ticktext=["0 Gün", "3 Gün", "5 Gün", "8+ Gün"],
                thickness=15,
                len=0.7
            ),
            height=680,
            updatemenus=[dict(
                type='buttons',
                showactive=False,
                y=-0.1,
                x=0.5,
                xanchor='center',
                yanchor='top',
                direction='left',
                buttons=[
                    dict(label='▶ Oynat', method='animate',
                         args=[None, dict(frame=dict(duration=1000, redraw=True), fromcurrent=True, mode='immediate')]),
                    dict(label='⏸ Duraklat', method='animate',
                         args=[[None], dict(frame=dict(duration=0, redraw=False), mode='immediate')])
                ]
            )]
        )
        
        st.plotly_chart(fig_map, width='stretch', key='risk_map_chart')

        # Day summary bar (Static overview)
        st.markdown("---")
        nav_cols = st.columns(len(ordered_days))
        for i, day_lbl in enumerate(ordered_days):
            with nav_cols[i]:
                day_data = map_df[map_df['Day'] == day_lbl]
                max_wait = day_data['WaitDays'].max()
                emoji = "🔴" if max_wait > 6 else ("🟡" if max_wait > 3 else ("🟢" if max_wait >= 0 else "⬜"))
                st.markdown(f"<div style='text-align:center; font-size:12px; padding:4px;'>{emoji}<br><b>{day_lbl}</b></div>", unsafe_allow_html=True)

        # Forecaster Details Table
        if 'pipeline_forecast_df' in st.session_state:
            st.markdown("---")
            st.subheader("📊 7-Günlük Forecaster Projeksiyon Tablosu")
            f_df = st.session_state['pipeline_forecast_df']
            
            fc1, fc2 = st.columns(2)
            with fc1:
                service_options = ["Tümünü Göster"] + sorted(f_df['Servis Adı'].unique().tolist())
                selected_service = st.selectbox("Servis Adı Filtresi:", service_options, key="f_service")
            with fc2:
                # To sort dates correctly if they are 'Day 1', 'Day 2', etc.
                import re
                def sort_key(x):
                    m = re.search(r'\d+', x)
                    return int(m.group()) if m else 0
                date_options = ["Tümünü Göster"] + sorted(f_df['Tarih'].unique().tolist(), key=sort_key)
                selected_date = st.selectbox("Tarih Filtresi:", date_options, key="f_date")
                
            filtered_f_df = f_df.copy()
            if selected_service != "Tümünü Göster":
                filtered_f_df = filtered_f_df[filtered_f_df['Servis Adı'] == selected_service]
            if selected_date != "Tümünü Göster":
                filtered_f_df = filtered_f_df[filtered_f_df['Tarih'] == selected_date]
                
            st.dataframe(filtered_f_df, width='stretch', hide_index=True)

        # Commander Orders
        if 'pipeline_tactical_orders' in st.session_state:
            st.markdown("---")
            st.success("🤖 **Commander Agent Completed**")
            st.subheader("♞ Tactical Commander Orders")
            st.info(st.session_state['pipeline_tactical_orders'])

    elif not run_button:
        st.info("👈 Use the parameters on the sidebar and click **Run Multi-Agent Optimizer** to test the system!")
