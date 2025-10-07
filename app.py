import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time

# ------------------------------------------------------
# Streamlit Setup
# ------------------------------------------------------
st.set_page_config(page_title="Stock Scanner & Monitor", layout="wide")

# ------------------------------------------------------
# Utility: Flatten MultiIndex Columns
# ------------------------------------------------------
def flatten_columns(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if c[0] else c[1] for c in df.columns]
    return df

# ------------------------------------------------------
# Utility: Daten holen
# ------------------------------------------------------
@st.cache_data(ttl=60)
def get_data(symbol, period="1d", interval="1m"):
    try:
        data = yf.download(symbol, period=period, interval=interval, progress=False)
        if data is None or data.empty:
            return None
        data = flatten_columns(data)
        data.reset_index(inplace=True)
        return data
    except Exception:
        return None

# ------------------------------------------------------
# Symbolquellen laden
# ------------------------------------------------------
@st.cache_data
def load_symbol_lists():
    sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
    nasdaq100 = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[4]
    return sp500["Symbol"].tolist(), nasdaq100["Ticker"].tolist()

# ------------------------------------------------------
# Scanner
# ------------------------------------------------------
def stock_scanner():
    st.title("📊 Aktien-Scanner")

    st.write("Scanne Aktien mit hohem Volumenanstieg im Vergleich zum Durchschnitt der letzten 50 Minuten.")

    sp500_symbols, nasdaq_symbols = load_symbol_lists()

    source = st.selectbox("Symbolquelle auswählen:", ["S&P 500", "NASDAQ 100", "Eigene Auswahl"])
    if source == "S&P 500":
        symbols = sp500_symbols
    elif source == "NASDAQ 100":
        symbols = nasdaq_symbols
    else:
        symbols = st.text_area("Eigene Symbole (kommagetrennt):", "AAPL,TSLA,AMD").replace(" ", "").split(",")

    run_scan = st.button("🔍 Scan starten")

    if run_scan:
        st.info("⏳ Scan läuft... bitte warten.")
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

            last = data.iloc[-1]
            change = ((last["Close"] - data["Close"].iloc[-51]) / data["Close"].iloc[-51]) * 100

            if last["RelVol"] > 2 and change > 5:
                results.append({
                    "Symbol": sym,
                    "Rel. Volumen": round(last["RelVol"], 2),
                    "Kursveränderung (%)": round(change, 2),
                    "Letzter Preis": round(last["Close"], 2)
                })

        progress.empty()

        if results:
            df = pd.DataFrame(results).sort_values(by="Kursveränderung (%)", ascending=False)
            st.dataframe(df, use_container_width=True)
            st.session_state["monitor_symbols"] = df["Symbol"].tolist()
            st.success(f"✅ {len(df)} Aktien gefunden. Monitoring aktiviert.")
        else:
            st.warning("Keine passenden Aktien gefunden.")

# ------------------------------------------------------
# Monitoring
# ------------------------------------------------------
def monitor_page():
    st.title("📈 Live Monitoring")

    if "monitor_symbols" not in st.session_state or not st.session_state["monitor_symbols"]:
        st.info("⚠️ Noch keine Symbole zum Beobachten. Bitte zuerst den Scanner nutzen.")
        return

    symbols = st.session_state["monitor_symbols"]
    refresh_rate = st.slider("⏱ Aktualisierung alle (Sekunden):", 30, 300, 60)

    st.write(f"Überwachte Symbole: {', '.join(symbols)}")

    data_rows = []
    for sym in symbols:
        data = get_data(sym)
        if data is None or len(data) < 2:
            continue
        last, prev = data.iloc[-1], data.iloc[-2]
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
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("Keine Daten verfügbar.")

    st.caption(f"Letztes Update: {datetime.now().strftime('%H:%M:%S')}")
    st.experimental_rerun() if st.button("🔄 Jetzt aktualisieren") else time.sleep(refresh_rate)

# ------------------------------------------------------
# Navigation
# ------------------------------------------------------
st.sidebar.title("📍 Navigation")
page = st.sidebar.radio("Seite auswählen", ["🔍 Scanner", "📈 Monitoring"])

if page == "🔍 Scanner":
    stock_scanner()
else:
    monitor_page()
