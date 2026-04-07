import streamlit as st
import requests
import google.generativeai as genai
import os
import pandas as pd
import altair as alt
from streamlit_autorefresh import st_autorefresh
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURAZIONE ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

st.set_page_config(page_title="F1 Mission Control", page_icon="🏎️", layout="wide", initial_sidebar_state="collapsed")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name='gemini-3-flash-preview',
        system_instruction="Sei il Capo degli Ingegneri al muretto box di F1. Il tuo compito è analizzare la situazione in gara e rispondere al pilota o al Team Principal in modo tecnico, freddo e iper-realistico, usando il tipico gergo radiofonico (es. 'Copy', 'Box', 'Delta', 'Strat mode'). Argomenta le tue risposte creando discorsi fluidi e brevi paragrafi. È ASSOLUTAMENTE VIETATO USARE ELENCHI PUNTATI O NUMERATI. Sei sotto pressione: vai dritto al punto basandoti SOLO ED ESCLUSIVAMENTE sui dati live che ti vengono forniti nel contesto. Se ti vengono chiesti gap millimetrici o lo stato di usura delle gomme, e questi dati non sono presenti nel tuo contesto, NON INVENTARLI: comunica in modo realistico che sei in attesa di conferma dai sensori o dal server della telemetria. Sii conciso, spietato nell'analisi logica e fornisci sempre una raccomandazione chiara quando ti viene chiesta una strategia."
    )

# --- FUNZIONI DATI (OpenF1 & Jolpica/Ergast) ---

@st.cache_data(ttl=3600)
def get_sessions(year):
    """Scarica le sessioni e le raggruppa per Gran Premio (Nazione)"""
    try:
        url = f"https://api.openf1.org/v1/sessions?year={year}"
        res = requests.get(url, timeout=5).json()
        
        # SCUDO: Se l'API va offline o dà errore testuale, restituisci un fallback
        if not isinstance(res, list):
            return {"Offline - Riprova": {"Latest": "latest"}}

        meetings = {}
        for s in res:
            country = s.get('country_name', 'Sconosciuto')
            s_name = s.get('session_name', 'Sconosciuta')
            s_key = s.get('session_key', 'latest')
            
            # Crea il "cassetto" della nazione se non esiste
            if country not in meetings:
                meetings[country] = {}
                
            # Salva la sessione dentro la nazione
            meetings[country][s_name] = s_key
            
        # Se la lista è completamente vuota
        if not meetings:
            return {"Nessun GP trovato": {"Latest": "latest"}}
            
        return meetings
        
    except Exception as e: 
        print(f"Errore connessione sessioni: {e}")
        return {"Offline - Riprova tra poco": {"Latest": "latest"}}

@st.cache_data(ttl=300)
def get_ergast_data(path):
    """Funzione universale per Jolpica/Ergast (Risultati e Classifiche storiche)"""
    try:
        url = f"https://api.jolpi.ca/ergast/f1/{path}.json"
        headers = {'User-Agent': 'F1-Mission-Control/2.0'}
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get('MRData', None)
        return None
    except Exception: 
        return None

@st.cache_data(ttl=60)
def get_drivers(session_key):
    try:
        url = f"https://api.openf1.org/v1/drivers?session_key={session_key}"
        res = requests.get(url, timeout=5).json()
        drivers = {}
        for d in res:
            if d['last_name'] not in drivers:
                drivers[d['last_name']] = {
                    "full_name": f"{d['first_name']} {d['last_name']}",
                    "team": d['team_name'],
                    "color": f"#{d['team_colour']}",
                    "number": d['driver_number'],
                    "name_id": d['name_acronym']
                }
        return drivers
    except: return {}

@st.cache_data(ttl=30)
def get_openf1_race_status(session_key):
    """Calcola la Griglia di Partenza e l'Arrivo usando i transponder di OpenF1"""
    try:
        url = f"https://api.openf1.org/v1/position?session_key={session_key}"
        res = requests.get(url, timeout=15).json()
        
        start_grid = {}
        end_grid = {}
        
        # SCUDO: se l'API non restituisce una lista, interrompiamo per evitare il crash
        if not isinstance(res, list):
            return {}, {}
        
        for p in res:
            num = p.get('driver_number')
            pos = p.get('position')
            
            # Saltiamo i dati sporchi
            if num is None or pos is None:
                continue
                
            # La primissima posizione registrata è la partenza
            if num not in start_grid:
                start_grid[num] = pos
                
            # Sovrascriviamo continuamente: l'ultimo valore sarà l'arrivo (o il live)
            end_grid[num] = pos
            
        return start_grid, end_grid
    except Exception as e:
        print(f"Errore Sensori OpenF1: {e}")
        return {}, {}

@st.cache_data(ttl=30)
def get_live_positions(session_key):
    """Recupera l'ultima posizione in pista di ogni pilota dai sensori OpenF1"""
    try:
        url = f"https://api.openf1.org/v1/position?session_key={session_key}"
        res = requests.get(url, timeout=10).json()
        
        # SCUDO: se l'API risponde con un errore testuale, ci fermiamo
        if not isinstance(res, list):
            return {}
        
        latest_positions = {}
        for p in res:
            if 'driver_number' in p and 'position' in p:
                latest_positions[p['driver_number']] = p['position']
            
        return latest_positions
    except Exception as e:
        print(f"Errore Live Positions: {e}")
        return {}

@st.cache_data(ttl=120)
def get_laps(driver_num, session_key):
    try:
        url = f"https://api.openf1.org/v1/laps?driver_number={driver_num}&session_key={session_key}"
        res = requests.get(url, timeout=10).json()
        return [lap for lap in res if lap.get('lap_duration')]
    except: return []

@st.cache_data(ttl=300)
def get_telemetry_full(driver_num, session_key):
    try:
        url = f"https://api.openf1.org/v1/car_data?driver_number={driver_num}&session_key={session_key}"
        return requests.get(url, timeout=10).json()
    except: return []

@st.cache_data(ttl=30)
def get_race_msgs(session_key):
    try:
        url = f"https://api.openf1.org/v1/race_control?session_key={session_key}"
        res = requests.get(url, timeout=5).json()
        return res[-10:]
    except: return []

@st.cache_data(ttl=3600)
def get_lap_location(driver_num, session_key, start_date, end_date):
    """Scarica le coordinate X e Y esatte di un singolo giro per disegnare la pista"""
    try:
        # Usiamo i filtri > e < di OpenF1 per scaricare solo i dati di un giro specifico!
        url = f"https://api.openf1.org/v1/location?driver_number={driver_num}&session_key={session_key}&date>={start_date}&date<={end_date}"
        res = requests.get(url, timeout=10).json()
        return res
    except Exception as e:
        return []

@st.cache_data(ttl=60)
def get_team_radio(session_key, driver_num=None):
    """Recupera le comunicazioni audio, creando una compilation per il Best Of"""
    try:
        if driver_num:
            url = f"https://api.openf1.org/v1/team_radio?session_key={session_key}&driver_number={driver_num}"
            res = requests.get(url, timeout=10).json()
            if isinstance(res, list):
                return res[-10:] # Ultimi 10 per il singolo pilota
        else:
            url = f"https://api.openf1.org/v1/team_radio?session_key={session_key}"
            res = requests.get(url, timeout=10).json()
            if isinstance(res, list):
                return res[-30:] # Ultimi 30 per la compilation TV!
        return []
    except Exception as e:
        print(f"Errore Radio: {e}")
        return []

@st.cache_data(ttl=60) 
def format_time(seconds):
    """Converte i secondi in formato F1 (Min:Sec.Millesimi)"""
    if not seconds or pd.isna(seconds):
        return "N/A"
    
    m = int(seconds // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    
    if m > 0:
        return f"{m}:{s:02d}.{ms:03d}"
    return f"{s}.{ms:03d}"

@st.cache_data(ttl=60)
def get_stints(session_key):
    """Scarica le strategie e le mescole utilizzate dai piloti"""
    try:
        url = f"https://api.openf1.org/v1/stints?session_key={session_key}"
        res = requests.get(url, timeout=10).json()
        return res if isinstance(res, list) else []
    except Exception as e:
        print(f"Errore Stints: {e}")
        return []
    
@st.cache_data(ttl=60)
def get_weather(session_key):
    """Recupera l'ultimo bollettino meteo della sessione"""
    try:
        url = f"https://api.openf1.org/v1/weather?session_key={session_key}"
        res = requests.get(url, timeout=5).json()
        if isinstance(res, list) and len(res) > 0:
            return res[-1] # Prendiamo l'ultima lettura, che è la più aggiornata
        return None
    except: return None

# --- INTERFACCIA E SIDEBAR ---

st.markdown("""
    <style>
    /* Usiamo le variabili dinamiche di Streamlit per adattarci a Light/Dark Mode */
    .stMetric { 
        background-color: var(--secondary-background-color); 
        color: var(--text-color); 
        padding: 10px; 
        border-radius: 10px; 
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.title("🏁 F1 Pro Terminal")
    st.markdown("---")
    
    st.subheader("⚙️ Impostazioni Gara")
    selected_year = st.selectbox("📅 Stagione Mondiale:", [2026, 2025, 2024, 2023], index=0)
    
    # Recupera le sessioni (ora divise per nazione!)
    meetings = get_sessions(selected_year)
    
    if meetings:
        # 1. MENU A TENDINA: Scelta della Nazione
        countries = list(meetings.keys())
        default_country_index = len(countries) - 1 if countries else 0
        selected_country = st.selectbox("📍 Gran Premio:", countries, index=default_country_index)
        
        # Mostriamo visivamente il Round calcolando l'indice
        curr_round = countries.index(selected_country) + 1
        st.info(f"🏆 **Round {curr_round}** del {selected_year}")
        
        # 2. PULSANTIERA ORIZZONTALE: Scelta della Sessione (Sprint, Gara, ecc.)
        sessions_in_country = meetings[selected_country]
        session_names = list(sessions_in_country.keys())
        default_session_index = len(session_names) - 1 if session_names else 0
        
        # MAGIC TRICK: horizontal=True mette i radio button in riga!
        selected_session = st.radio("🏎️ Sessione:", session_names, index=default_session_index, horizontal=True)
        
        # Variabili che servono al resto dell'app
        curr_session_key = sessions_in_country[selected_session]
        session_name = f"{selected_country} - {selected_session}"
    else:
        st.warning("Nessun dato disponibile.")
        curr_session_key = "latest"
        session_name = "Sconosciuta"
        curr_round = 1

page = st.radio(
    "Navigazione Terminale:", 
    [
        "📡 Dashboard", 
        "📈 Telemetria", 
        "🏆 Classifiche", 
        "🗺️ Mappa Circuito", 
        "🎙️ Radio Box", 
        "💬 Chiacchera col muretto"
    ], 
    horizontal=True, 
    label_visibility="collapsed"
)
st.markdown("---")

# --- LOGICA DELLE PAGINE ---

# 1. DASHBOARD IBRIDA (TUTTA IN OPENF1)
if page == "📡 Dashboard":
    if selected_year == datetime.now().year:
        st_autorefresh(interval=30000, key="live_dashboard_updater")
    head_col1, head_col2 = st.columns([2, 1.5])
    
    with head_col1:
        st.header(f"Dashboard: {session_name}")
        
    with head_col2:
        weather = get_weather(curr_session_key)
        if weather:
            # Scegliamo l'icona in base alla pioggia
            rain_icon = "🌧️ Pioggia" if weather.get('rainfall', 0) > 0 else "☀️ Asciutto"
            air_t = weather.get('air_temperature', '--')
            track_t = weather.get('track_temperature', '--')
            hum = weather.get('humidity', '--')
            
            # CSS magico per spingere tutto a destra e creare un badge elegante
            st.markdown(f"""
            <div style='text-align: right; padding-top: 25px;'>
                <span style='background-color: var(--secondary-background-color); color: var(--text-color); padding:10px 15px; border-radius:8px; font-size:14px; border-left: 3px solid #3498db; box-shadow: 0 2px 4px rgba(0,0,0,0.2);'>
                    {rain_icon} &nbsp;|&nbsp; 🌡️ Aria: <b>{air_t}°C</b> &nbsp;|&nbsp; 🛣️ Pista: <b>{track_t}°C</b> &nbsp;|&nbsp; 💧 Umidità: <b>{hum}%</b>
                </span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("<div style='text-align: right; padding-top: 25px; color: gray;'>Meteo Live non disponibile</div>", unsafe_allow_html=True)
            
    st.markdown("---")
    
    # 1. SCARICA I DATI DEI PILOTI
    drivers_dict = get_drivers(curr_session_key)
    
    # 2. CONTROLLO PROATTIVO E AUTOMATICO (Il nostro vanto!)
    if not drivers_dict:
        st.error("🚫 **DATI ASSENTI / SESSIONE ANNULLATA:** I transponder delle monoposto risultano spenti. Questo evento potrebbe essere stato cancellato dal calendario, non essere ancora iniziato, oppure i server FIA non hanno trasmesso la telemetria.")
        
    start_grid, live_grid = get_openf1_race_status(curr_session_key)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🚦 Griglia di Partenza")
        if drivers_dict and start_grid:
            # Ordiniamo i piloti per la loro prima posizione rilevata
            starting_list = sorted(drivers_dict.values(), key=lambda d: start_grid.get(d['number'], 99))
            
            for d in starting_list:
                pos = start_grid.get(d['number'], 'Pit')
                st.markdown(f"""
                <div style='padding:8px; border-left:4px solid {d['color']}; background-color: var(--secondary-background-color); color: var(--text-color); margin-bottom:5px; border-radius:3px;'>
                    <b>{pos}°</b> {d['full_name']} <span style='float:right;color:gray;font-size:12px;'>{d['team']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("I transponder non hanno ancora registrato l'allineamento in griglia.")

    with col2:
        st.subheader("🏁 Arrivo / Posizioni Live")
        if drivers_dict and live_grid:
            # Ordiniamo per l'ultima posizione nota
            arrival_list = sorted(drivers_dict.values(), key=lambda d: live_grid.get(d['number'], 99))
            
            for d in arrival_list:
                pos = live_grid.get(d['number'], 'RIT')
                st.markdown(f"""
                <div style='padding:8px; border-left:4px solid {d['color']}; background-color: var(--secondary-background-color); color: var(--text-color); margin-bottom:5px; border-radius:3px;'>
                    <b>{pos}°</b> {d['full_name']} <span style='float:right;color:gray;font-size:12px;'>#{d['number']}</span>
                </div>
                """, unsafe_allow_html=True)
            
            # Messaggio dinamico: visto che usiamo dati live, copriamo sia la gara in corso che quella finita
            st.caption("ℹ️ *Se la gara non è conclusa, queste sono le posizioni in tempo reale (Gara in corso).*")
        else:
            st.warning("🏎️ Gara non ancora iniziata o auto ferme ai box.")
    st.markdown("---")
    st.subheader("Strategia Pneumatici (Timeline)")
    
    stints_data = get_stints(curr_session_key)
    
    if stints_data and drivers_dict:
        df_stints = pd.DataFrame(stints_data)
        
        # 1. FIX DEI NOMI: Creiamo un dizionario per associare il Numero all'Acronimo (es. 1 -> VER)
        num_to_name = {info['number']: info['name_id'] for info in drivers_dict.values()}
        df_stints['Pilota'] = df_stints['driver_number'].map(lambda x: num_to_name.get(x, str(x)))
        
        # Pulizia dati
        df_stints = df_stints.dropna(subset=['lap_start', 'lap_end', 'compound'])
        
        if not df_stints.empty:
            color_scale = alt.Scale(
                domain=['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET', 'UNKNOWN'],
                range=['#e74c3c', '#f1c40f', '#ecf0f1', '#2ecc71', '#3498db', '#95a5a6']
            )
            
            # 2. FIX DESIGN: Usiamo size=6 per fare una riga sottile invece del blocco pesante
            chart = alt.Chart(df_stints).mark_bar(size=6, cornerRadius=3).encode(
                x=alt.X('lap_start:Q', title='Numero di Giro'),
                x2='lap_end:Q',
                # MAGIA QUI: labelOverlap=False ordina al grafico di NON nascondere i nomi!
                y=alt.Y('Pilota:N', sort='-x', title='', axis=alt.Axis(labelOverlap=False)), 
                color=alt.Color('compound:N', scale=color_scale, legend=alt.Legend(title="Mescola", orient="top", columns=3, labelLimit=0)),
                tooltip=['Pilota', 'compound', 'lap_start', 'lap_end']
            ).properties(height=600) # Alziamo un po' il grafico per fare spazio a tutti i 20 nomi
            
            st.altair_chart(chart, width="stretch")
        else:
            st.info("I dati sulle mescole non sono ancora stati elaborati dai sensori.")
            
elif page == "📈 Telemetria":
    st.header(f"Telemetria: {session_name}")
    drivers_dict = get_drivers(curr_session_key)
    
    if drivers_dict:
        col1, col2 = st.columns(2)
        with col1:
            selected_name = st.selectbox("🏎️ Pilota", list(drivers_dict.keys()))
            driver_num = drivers_dict[selected_name]['number']
        
        laps = get_laps(driver_num, curr_session_key)
        
        if laps:
            laps = sorted(laps, key=lambda x: x.get('lap_number', 0))
            max_laps = len(laps)
            
            with col2:
                lap_num = st.slider("⏱️ Scorri i giri", min_value=1, max_value=max_laps, value=1)
                
                selected_lap = laps[lap_num - 1]
                selected_lap_name = f"Giro {selected_lap.get('lap_number')} ({format_time(selected_lap.get('lap_duration'))})"
            
            st.subheader("Tempi per Settore")
            sec1, sec2, sec3 = st.columns(3)
            
            # Applichiamo la formattazione F1 ai settori
            sec1.metric("Settore 1", f"{format_time(selected_lap.get('duration_sector_1'))} s")
            sec2.metric("Settore 2", f"{format_time(selected_lap.get('duration_sector_2'))} s")
            sec3.metric("Settore 3", f"{format_time(selected_lap.get('duration_sector_3'))} s")
            
            data = get_telemetry_full(driver_num, curr_session_key)
            
            # --- CREIAMO LE DUE COLONNE PER I GRAFICI AFFIANCATI ---
            chart_col1, chart_col2 = st.columns(2)
            
            # GRAFICO 1: VELOCITÀ DEL GIRO (A SINISTRA)
            with chart_col1:
                if data:
                    df = pd.DataFrame(data)
                    df['date'] = pd.to_datetime(df['date'], format='ISO8601', utc=True)
                    start_time = pd.to_datetime(selected_lap['date_start'], format='ISO8601', utc=True)
                    end_time = start_time + pd.Timedelta(seconds=selected_lap['lap_duration'])
                    
                    df_lap = df[(df['date'] >= start_time) & (df['date'] <= end_time)].copy()
                    
                    if not df_lap.empty:
                        df_lap['speed'] = pd.to_numeric(df_lap['speed'], errors='coerce')
                        df_lap['elapsed'] = (df_lap['date'] - start_time).dt.total_seconds()
                        
                        st.subheader(f"Velocità: {selected_lap_name}")
                        
                        line_chart = alt.Chart(df_lap).mark_line(color='#3498db').encode(
                            x=alt.X('elapsed:Q', title='Tempo del Giro (s)'),
                            y=alt.Y('speed:Q', title='Velocità (km/h)'),
                            tooltip=['elapsed', 'speed']
                        )
                        
                        s1_time = selected_lap.get('duration_sector_1') or 0
                        s2_time = s1_time + (selected_lap.get('duration_sector_2') or 0)
                        
                        sectors_df = pd.DataFrame({'elapsed': [s1_time, s2_time]})
                        rules = alt.Chart(sectors_df).mark_rule(color='#e74c3c', strokeDash=[5, 5]).encode(x='elapsed:Q')
                        
                        st.altair_chart(line_chart + rules, width="stretch") 
                    else:
                        st.warning("Dati telemetrici mancanti per questo giro.")
            
            # GRAFICO 2: ANDAMENTO GOMME / PASSO GARA (A DESTRA)
            with chart_col2:
                st.subheader("Degrado Gomme (Passo Gara)")
                stints_data = get_stints(curr_session_key)
                
                if stints_data and laps:
                    df_laps = pd.DataFrame(laps)
                    # Filtriamo gli stint solo per il pilota selezionato
                    df_stints = pd.DataFrame([s for s in stints_data if s.get('driver_number') == driver_num])
                    
                    if not df_stints.empty:
                        # INCROCIO DATI ROBUSTO: Assegniamo la mescola guardando i giri di inizio e fine
                        def get_compound(lap_num):
                            for _, stint in df_stints.iterrows():
                                if stint.get('lap_start', 0) <= lap_num <= stint.get('lap_end', 999):
                                    return stint.get('compound', 'UNKNOWN')
                            return 'UNKNOWN'
                            
                        # Applichiamo la funzione a tutti i giri
                        df_laps['compound'] = df_laps['lap_number'].apply(get_compound)
                        
                        # Filtro di pulizia: teniamo solo i giri veloci (entro il 115% del giro più veloce)
                        min_lap = df_laps['lap_duration'].min()
                        df_laps_filtered = df_laps[df_laps['lap_duration'] <= min_lap * 1.15].dropna(subset=['lap_duration'])
                        
                        # Colori ufficiali Pirelli
                        color_scale = alt.Scale(
                            domain=['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET', 'UNKNOWN'],
                            range=['#e74c3c', '#f1c40f', '#ecf0f1', '#2ecc71', '#3498db', '#95a5a6']
                        )
                        
                        # Disegniamo i punti dei giri
                        pace_chart = alt.Chart(df_laps_filtered).mark_circle(size=60, opacity=0.8).encode(
                            x=alt.X('lap_number:Q', title='Numero Giro', scale=alt.Scale(zero=False)),
                            y=alt.Y('lap_duration:Q', title='Tempo (s)', scale=alt.Scale(zero=False)),
                            color=alt.Color('compound:N', scale=color_scale, legend=alt.Legend(title="Mescola", orient="bottom", columns=3, labelLimit=0)),
                            tooltip=['lap_number', 'lap_duration', 'compound']
                        ).properties(height=350)
                        
                        # Disegniamo la linea di tendenza del degrado
                        trend = pace_chart.transform_regression('lap_number', 'lap_duration', groupby=['compound']).mark_line(size=3)
                        
                        st.altair_chart(pace_chart + trend, width='stretch')
                    else:
                        st.info("Dati mescole non ancora disponibili per l'analisi.")
                else:
                    st.info("Gara non avviata o dati mancanti.")
        else:
            st.info("Nessun giro valido trovato.")
    else:
        st.error("Connessione ai piloti fallita.")

elif page == "🏆 Classifiche":
    st.header(f"Punteggi e Campionato - {selected_year}")
    
    st.subheader(f"🏁 Punti Assegnati nel Round {curr_round}")
    
    # 1. PROVIAMO A CHIEDERE I DATI UFFICIALI AD ERGAST
    res_data = get_ergast_data(f"{selected_year}/{curr_round}/results")
    
    if res_data and 'Table' in res_data.get('RaceTable', {}) and res_data['RaceTable']['Races']:
        st.caption("✅ Dati Ufficiali Archiviati FIA")
        results = res_data['RaceTable']['Races'][0]['Results']
        points_df = pd.DataFrame([{
            "Pos": r['position'],
            "Pilota": f"{r['Driver']['familyName']}",
            "Team": r['Constructor']['name'],
            "Punti": float(r['points'])
        } for r in results if float(r['points']) > 0])
        
        if not points_df.empty:
            st.table(points_df.set_index("Pos"))
            
    else:
        # 2. PIANO B: PROIEZIONE LIVE CON OPENF1
        st.warning("⚠️ Dati ufficiali FIA non ancora disponibili. Calcolo la proiezione in base alle posizioni in pista (OpenF1).")
        
        # Dizionario del regolamento F1 per la Top 10
        f1_points_system = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
        
        drivers_dict = get_drivers(curr_session_key)
        live_positions = get_live_positions(curr_session_key)
        
        if drivers_dict and live_positions and "Race" in session_name:
            projected_points = []
            
            for last_name, info in drivers_dict.items():
                pos = live_positions.get(info['number'], 99)
                if pos <= 10: # Diamo punti solo ai primi 10
                    projected_points.append({
                        "Pos (Live)": pos,
                        "Pilota": info['full_name'],
                        "Team": info['team'],
                        "Punti Stimati": f1_points_system.get(pos, 0)
                    })
            
            if projected_points:
                # Ordiniamo per posizione
                projected_points = sorted(projected_points, key=lambda x: x['Pos (Live)'])
                st.table(pd.DataFrame(projected_points).set_index("Pos (Live)"))
            else:
                st.info("Nessuna proiezione disponibile al momento.")
        else:
            st.info("Seleziona una 'Race' (Gara) dal menu a tendina per vedere la proiezione punti. Le prove libere non danno punti!")

    st.markdown("---")
    st.subheader("🌍 Classifica Mondiale Piloti (Attuale)")
    stand_data = get_ergast_data(f"{selected_year}/driverStandings")
    if stand_data and stand_data['StandingsTable']['StandingsLists']:
        standings = stand_data['StandingsTable']['StandingsLists'][0]['DriverStandings']
        final_standings = []
        for s in standings:
            final_standings.append({
                "Pos": s['position'],
                "Pilota": f"{s['Driver']['givenName']} {s['Driver']['familyName']}",
                "Team": s['Constructors'][0]['name'],
                "Punti Totali": float(s['points']),
                "Vittorie": int(s['wins'])
            })
        st.dataframe(pd.DataFrame(final_standings).set_index("Pos"), width="stretch")

elif page == "🗺️ Mappa Circuito":
    st.header(f"Tracciato GPS: {session_name}")
    
    drivers_dict = get_drivers(curr_session_key)
    if drivers_dict:
        # Prendiamo un pilota a caso (il primo della lista) per tracciare la pista
        first_driver = list(drivers_dict.values())[0]
        driver_num = first_driver['number']
        
        # Recuperiamo i suoi giri
        laps = get_laps(driver_num, curr_session_key)
        
        if laps:
            # Prendiamo il suo secondo giro (per evitare il giro di uscita dai box)
            target_lap = laps[1] if len(laps) > 1 else laps[0]
            
            # Calcoliamo orario di inizio e fine del giro
            start_time = target_lap['date_start']
            end_time = (pd.to_datetime(start_time) + pd.Timedelta(seconds=target_lap['lap_duration'])).isoformat()
            
            with st.spinner("Scaricando coordinate satellitari..."):
                location_data = get_lap_location(driver_num, curr_session_key, start_time, end_time)
            
            if location_data:
                df_loc = pd.DataFrame(location_data)
                
                # --- DISEGNAMO LA PISTA CON ALTAIR ---
                # ERRORE CORRETTO: Si usa mark_line() invece di mark_path()
                track_map = alt.Chart(df_loc).mark_line(
                    strokeWidth=4,
                    color='#FF1E00', 
                    interpolate='monotone' 
                ).encode(
                    x=alt.X('x:Q', scale=alt.Scale(zero=False), axis=None), 
                    y=alt.Y('y:Q', scale=alt.Scale(zero=False), axis=None),
                    order='date:T', # FONDAMENTALE: unisce i punti in base all'orario del GPS
                    tooltip=['date']
                ).properties(
                    height=500,
                    title="Tracciato Generato da Telemetria (Sensori X/Y)"
                ).configure_view(
                    strokeWidth=0 
                )
                
                st.altair_chart(track_map, width="stretch")
                
                st.caption(f"Tracciato rilevato usando il transponder di {first_driver['full_name']} durante il giro {target_lap['lap_number']}.")
            else:
                st.warning("Dati GPS non disponibili per questa sessione.")
        else:
            st.info("Nessun giro registrato per mappare la pista.")

elif page == "🎙️ Radio Box":
    st.header(f"🎙️ Radio Box: {session_name}")
    
    drivers_dict = get_drivers(curr_session_key)
    msgs = get_race_msgs(curr_session_key)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📻 Sintonizzatore Radio")
        if drivers_dict:
            # Creiamo le opzioni per il menu a tendina
            driver_options = {"📻 Best of: Highlights TV": None}
            for name, d in drivers_dict.items():
                driver_options[f"{d['full_name']} (#{d['number']})"] = d['number']
            
            # Il Dropdown per scegliere chi ascoltare
            selected_radio_driver = st.selectbox("Seleziona Canale Radio", list(driver_options.keys()))
            selected_num = driver_options[selected_radio_driver]
            
            # Scarichiamo gli ultimi 10 messaggi per la selezione
            radios = get_team_radio(curr_session_key, selected_num)
            
            st.markdown("---")
            if selected_num is None:
                st.markdown("**Playlist: Best of Team Radio 🎧**")
            else:
                st.markdown(f"**Ultimi 10 messaggi di {selected_radio_driver}:**")
            
            if radios:
                for r in reversed(radios):
                    driver = next((d for d in drivers_dict.values() if d['number'] == r['driver_number']), None)
                    if driver:
                        time_str = r['date'][11:19]
                        st.markdown(f"**{driver['full_name']}** <span style='color:gray;font-size:12px;'>({driver['team']}) - {time_str}</span>", unsafe_allow_html=True)
                        st.audio(r['recording_url'])
            else:
                st.info("🔇 Nessun messaggio radio registrato per questa selezione.")
        else:
            st.warning("Connessione ai canali radio fallita.")
            
    with col2:
        st.subheader("🚩 Direzione Gara")
        if msgs:
            for m in reversed(msgs):
                text = m.get('message', '')
                time = m.get('date', '')[11:19]
                
                if any(word in text.upper() for word in ["FLAG", "PENALTY", "SAFETY", "INVESTIGATION"]):
                    st.error(f"⚠️ **{time}** - {text}")
                else:
                    st.info(f"ℹ️ **{time}** - {text}")
        else:
            st.write("Nessun messaggio dalla Direzione Gara.")

elif page == "💬 Chiacchera col muretto":
    st.header("🤖 Ingegnere di PistAI")
    
    # 1. INTERRUTTORE DI VELOCITÀ / CONTESTO
    st.markdown("💡 *Spegni il collegamento telemetrico per chat fulminee e generali sulla F1.*")
    use_live_data = st.toggle("📡 Analizza i dati live di questa gara (Richiede qualche secondo)", value=False)
    
    context = ""
    if use_live_data:
        with st.spinner("Scaricamento telemetria in corso..."):
            drivers_dict = get_drivers(curr_session_key)
            _, live_grid = get_openf1_race_status(curr_session_key)
            recent_msgs = get_race_msgs(curr_session_key)
            weather = get_weather(curr_session_key)
            
            live_standings = "Dati posizioni non disponibili."
            if drivers_dict and live_grid:
                sorted_indices = sorted(drivers_dict.values(), key=lambda d: live_grid.get(d['number'], 99))
                live_standings = ", ".join([f"{live_grid.get(d['number'])}° {d['full_name']}" for d in sorted_indices[:5]])
                
            weather_info = "Dati meteo non disponibili."
            if weather:
                weather_info = f"Aria {weather.get('air_temperature')}°C, Pista {weather.get('track_temperature')}°C, Umidità {weather.get('humidity')}%."

            race_control = " | ".join([m.get('message', '') for m in recent_msgs[-3:]]) if recent_msgs else "Nessuna anomalia."
            
            # Pacchetto segreto da passare a Gemini
            context = f"[DATI DI GARA ATTUALI: {session_name} | Top 5: {live_standings} | Meteo: {weather_info} | Direzione Gara: {race_control}]"

    # 2. GESTIONE DELLA MEMORIA CHAT
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Disegna a schermo i messaggi vecchi
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 3. INVIO DEL NUOVO MESSAGGIO
    if prompt := st.chat_input("Inge, analizza la situazione..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            if GEMINI_API_KEY:
                # Recupero della memoria
                history = []
                for m in st.session_state.messages[:-1]: 
                    role = "user" if m["role"] == "user" else "model"
                    history.append({"role": role, "parts": [m["content"]]})
                
                chat = model.start_chat(history=history)
                
                # 2. Iniezione forzata della linea temporale
                anno_attuale = datetime.now().year
                
                if use_live_data:
                    full_prompt = f"[CONTESTO TEMPORALE: Oggi siamo nel {anno_attuale}. L'utente ha selezionato l'evento '{session_name}' della stagione {selected_year}. DATI TELEMETRICI LIVE IN CORSO:]\n{context}\n\nDOMANDA: {prompt}"
                else:
                    full_prompt = f"[CONTESTO TEMPORALE: Oggi siamo nel {anno_attuale}. L'utente sta analizzando l'evento '{session_name}' della stagione {selected_year}. COLLEGAMENTO TELEMETRICO SPENTO. Rispondi usando la tua conoscenza storica. Se ti chiedono dettagli su gare recenti del {selected_year} o {anno_attuale} che non fanno parte del tuo database di addestramento, sii onesto, non inventare risultati e chiedi all'utente di accendere l'interruttore dei dati live per analizzare la telemetria di questa sessione.]\n\nDOMANDA: {prompt}"
                
                # 3. Invio del messaggio in streaming
                response = chat.send_message(full_prompt, stream=True)
                
                def stream_chunks():
                    for chunk in response:
                        if chunk.text:
                            yield chunk.text
                
                full_text = st.write_stream(stream_chunks())
                st.session_state.messages.append({"role": "assistant", "content": full_text})
                
            else:
                st.error("Inserisci la Gemini API Key!")