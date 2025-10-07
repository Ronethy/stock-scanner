import streamlit as st
import yfinance as yf
import pandas as pd
import time
from datetime import datetime, timedelta

# ------------------------------------------------------
# Seiteneinstellungen
# ------------------------------------------------------
st.set_page_config(page_title="Stock Scanner & Monitor", layout="wide")

# ------------------------------------------------------
# Utility-Funktion: Daten abrufen
# ------------------------------------------------------
@st.cache_data(ttl=60)
def get_data(symbol, period="1d", interval="1m"):
    try:
        data = yf.download(symbol, period=period, interval=interval, progress=False)
        if data is None or data.empty:
            return None
        data.reset_index(inplace=True)
        return data
    except Exception as e:
        return None

# ------------------------------------------------------
# Scanner-Seite
# ------------------------------------------------------
def stock_scanner():
    st.title("📊 Aktien-Scanner")

    st.write("Dieser Scanner sucht nach Aktien mit starkem Volumenanstieg im Vergleich zum Durchschnitt der letzten 50 Minuten.")
    st.info("🔁 Daten werden alle 60 Sekunden aktualisiert. Du kannst unten manuell neuladen.")

    # Nasdaq Top Symbole (Beispielhaft)
    default_symbols = ["AAPL", "TSLA", "AMD", "NVDA", "AMZN", "META", "MSFT", "NIO", "PLTR"]
    symbols = st.multiselect("Wähle Symbole aus (z. B. NASDAQ):", default_symbols, default=default_symbols)

    run_scan = st.button("🔍 Scan starten")

    if run_scan:
        results = []
        progress = st.progress(0)
        total = len(symbols)

        for i, sym in enumerate(symbols):
            progress.progress((i + 1) / total)
            data = get_data(sym)

            if data is None or "Volume" not in data.columns or len(data) < 51:
                continue

            data["AvgVol50"] = data["Volume"].rolling(window=50).mean()
            data["RelVol"] = data["Volume"] / data["AvgVol50"]

            last_row = data.iloc[-1]
            relvol = last_row["RelVol"]
            change = ((last_row["Close"] - data["Close"].iloc[-51]) / data["Close"].iloc[-51]) * 100

            if relvol > 2 and change > 5:
                results.append({
                    "Symbol": sym,
                    "Rel. Volumen": round(relvol, 2),
                    "Kursveränderung (%)": round(change, 2),
                    "Letzter Preis": round(last_row["Close"], 2)
                })

        if results:
            df = pd.DataFrame(results).sort_values(by="Kursveränderung (%)", ascending=False)
            st.dataframe(df, use_container_width=True)
            st.session_state["monitor_symbols"] = df["Symbol"].tolist()
            st.success("✅ Scan abgeschlossen. Diese Symbole werden jetzt im Monitoring beobachtet.")
        else:
            st.warning("Keine passenden Aktien gefunden.")

# ------------------------------------------------------
# Monitoring-Seite
# ------------------------------------------------------
def monitor_page():
    st.title("📈 Live Monitoring")

    if "monitor_symbols" not in st.session_state or not st.session_state["monitor_symbols"]:
        st.info("⚠️ Noch keine Symbole zum Beobachten. Bitte zuerst im Scanner finden.")
        return

    symbols = st.session_state["monitor_symbols"]
    refresh_interval = 60  # Sekunden

    placeholder = st.empty()
    last_update = datetime.now()

    # Endlosschleife im Streamlit-Modus (Timer)
    while True:
        data_rows = []
        for sym in symbols:
            data = get_data(sym)
            if data is None or data.empty:
                continue

            last = data.iloc[-1]
            prev = data.iloc[-2] if len(data) > 1 else last

            price_change = ((last["Close"] - prev["Close"]) / prev["Close"]) * 100
            color = "🟢" if price_change > 0 else "🔴" if price_change < 0 else "⚪"

            data_rows.append({
                "Symbol": sym,
                "Letzter Preis": round(last["Close"], 2),
                "Veränderung (%)": round(price_change, 2),
                "Volumen": int(last["Volume"]),
                "Trend": color
            })

        if data_rows:
            df = pd.DataFrame(data_rows)
            with placeholder.container():
                st.subheader(f"Letztes Update: {datetime.now().strftime('%H:%M:%S')}")
                st.dataframe(df, use_container_width=True)
        else:
            st.warning("Keine Daten verfügbar.")

        time.sleep(refresh_interval)
        st.rerun()

# ------------------------------------------------------
# Navigation
# ------------------------------------------------------
st.sidebar.title("📍 Navigation")
page = st.sidebar.radio("Seite auswählen", ["🔍 Scanner", "📈 Monitoring"])

if page == "🔍 Scanner":
    stock_scanner()
else:
    monitor_page()
