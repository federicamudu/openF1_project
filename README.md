# 🏎️ F1 Mission Control

Benvenuto al muretto box! **F1 Mission Control** è una web app interattiva costruita in Python e Streamlit che trasforma i dati della Formula 1 in un vero e proprio hub strategico. 

Il progetto unisce la telemetria in tempo reale dei transponder ufficiali (tramite l'API di OpenF1), i dati storici e le classifiche mondiali (tramite Jolpica/Ergast) e l'intelligenza artificiale generativa (Google Gemini) per offrirti l'esperienza definitiva da Ingegnere di Pista.

## ✨ Funzionalità del Terminale

Il menu laterale offre l'accesso a 6 sistemi principali:

* **📡 Dashboard Live:** Panoramica in tempo reale dell'evento. Include un widget meteo dinamico, la griglia di partenza, le posizioni live in pista e una **Timeline Strategica (Gantt)** che mostra l'utilizzo delle mescole per ogni pilota. La pagina è dotata di *Auto-Refresh* (si aggiorna da sola ogni 30 secondi durante le gare in corso).
* **📈 Telemetria:** Analisi approfondita dei giri. Mostra i tempi dei singoli settori (formato F1) e affianca la velocità (km/h) del singolo giro all'**Analisi del Degrado Gomme**, tracciando una linea di tendenza del passo gara in base alla mescola utilizzata.
* **🏆 Classifiche:** Visualizza i punti del singolo round e il Campionato Mondiale Piloti. Se i dati ufficiali FIA non sono ancora disponibili per la gara in corso, il sistema genera una **proiezione live** calcolando i punti stimati in base alle posizioni attuali in pista.
* **🗺️ Mappa Circuito:** Disegna la mappa del tracciato estrapolando e unendo le coordinate spaziali satellitari (X, Y) dei transponder delle monoposto durante un giro lanciato.
* **🎙️ Radio Box:** Ascolta i team radio dei piloti (in formato "Best of TV" o per singolo pilota) e leggi in tempo reale i messaggi ufficiali della Direzione Gara (Bandiere Gialle, Safety Car, Investigazioni, Penalità).
* **💬 Chiacchera col muretto (Ingegnere di PistAI):** Un vero assistente AI conversazionale basato su Google Gemini. L'AI legge "di nascosto" i dati live per rispondere a domande tattiche simulando le comunicazioni radio. È dotato di memoria storica della chat, risposte in tempo reale (Streaming) e un *Toggle* manuale per passare dall'analisi della gara in corso a discussioni sulla storia generale della F1.

## 🎛️ Pannello di Controllo (Menu Laterale)

Il menu a scomparsa sulla sinistra è la vera cabina di regia dell'applicazione. Da qui puoi gestire le **Impostazioni Globali** prima di tuffarti nei dati:
* **Selezione Storica e Live:** Scegli l'Anno (dal 2023 alla stagione corrente) e seleziona lo specifico Evento (Prove Libere, Sprint, Qualifiche o Gara).
* **Auto-Focus sull'Attualità:** Appena accedi, il sistema scansiona i database e si sintonizza automaticamente sull'ultimissima sessione disponibile o in corso di svolgimento, evitandoti di dover scorrere decine di gare.
* **Mobile-Friendly:** Per garantire la massima leggibilità dei grafici e delle griglie anche da smartphone, il menu si nasconde automaticamente all'avvio, lasciando il 100% dello schermo dedicato alla telemetria.

## 🛠️ Stack Tecnologico

* **Linguaggio:** Python
* **Frontend:** [Streamlit](https://streamlit.io/)
* **Dati Live & Telemetria:** [OpenF1 API](https://api.openf1.org/)
* **Dati Storici:** [Jolpica/Ergast API](https://api.jolpi.ca/)
* **Intelligenza Artificiale:** [Google Gemini API](https://ai.google.dev/) (`gemini-3-flash-preview`)
* **Librerie Principali:** `pandas` (dati), `altair` (grafici), `requests` (chiamate HTTP), `python-dotenv` (gestione segreti).

## 🚀 Installazione Locale

Vuoi far girare il "Mission Control" sul tuo computer? Ecco come fare:

1. **Clona la repository:**
   ```bash
   git clone [https://github.com/federicamudu/openF1_project.git](https://github.com/federicamudu/openF1_project.git)
   cd openF1_project

2. **Crea e attiva un ambiente virtuale (Opzionale ma raccomandato):**
    ```bash
    python -m venv .venv
    # Su macOS/Linux:
    source .venv/bin/activate
    # Su Windows:
    .venv\Scripts\activate

3. **Installa le dipendenze richieste:**
    ```bash
    pip install -r requirements.txt

4. **Configura le chiavi API (Google Gemini):**
    Crea un file chiamato .env nella cartella principale del progetto e inserisci la tua API Key:
    ```Snippet di codice
    GEMINI_API_KEY="la_tua_chiave_api_qui"

5. **Avvia l'app:**
    ```bash
    streamlit run app.py


## ☁️ Deploy su Streamlit Cloud

Il progetto è ottimizzato per il tema chiaro/scuro di sistema ed è pronto per essere ospitato gratuitamente su Streamlit Cloud.

* Attenzione: Non caricare mai il file .env su GitHub (assicurati che sia nel tuo .gitignore).

* Una volta collegata la repository a Streamlit Cloud, inserisci la tua chiave Gemini nel pannello Advanced Settings > Secrets utilizzando questo formato:
    ```Ini, TOML
    GEMINI_API_KEY = "la_tua_chiave_api_qui"


## ⚠️ Avvertenze sui Dati e sull'App
* **Ritardo Radio & Gomme**: I file audio dei Team Radio e i dati degli Stints (mescole) non sono sempre istantanei. Vengono elaborati dai server della FOM/Pirelli e possono subire ritardi o essere consolidati a fine sessione.
* **Gare Annullate:** L'app include blocchi e avvisi personalizzati inseriti a codice per gestire specifici Gran Premi cancellati dal calendario (come Bahrain e Arabia Saudita nel 2026), evitando chiamate a vuoto verso i database.
* **Tempi di Risposta AI:** La chat con l'Ingegnere di Pista potrebbe richiedere qualche secondo di attesa per generare l'output. L'AI utilizza l'anno solare corrente per orientarsi. Se le vengono poste domande su strategie di una gara, si baserà sui dati passati dalla Dashboard, evitando allucinazioni (es. invenzioni su distacchi o usura gomme).