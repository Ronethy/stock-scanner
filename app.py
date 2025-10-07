import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
from datetime import datetime, timedelta
import time

# --------------------------
# Einstellungen
# --------------------------
st.set_page_config(page_title="📈 Aktien Breakout Scanner", layout="wide")
st.title("📊 Aktien Breakout Scanner (NASDAQ / S&P500)")

# --------------------------
# Sidebar: Symbol-Quelle
# --------------------------
st.sidebar.header("Symbol-Auswahl")
symbol_source = st.sidebar.selectbox(
    "Welche Symbol-Liste soll verwendet werden?",
    ["Eigene Watchlist", "NASDAQ-100", "S&P500", "Gesamte NASDAQ"]
)

symbols = []

if symbol_source == "Eigene Watchlist":
    symbols_input = st.sidebar.text_area("Symbole (Komma getrennt)", "AAPL,TSLA,AMD,NIO,PLTR")
    symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

elif symbol_source == "NASDAQ-100":
    try:
        df = pd.read_csv("https://datahub.io/core/nasdaq-100-companies/r/constituents.csv")
        symbols = df["Symbol"].dropna().tolist()
        st.sidebar.success(f"{len(symbols)} NASDAQ-100 Symbole geladen ✅")
    except Exception as e:
        st.sidebar.error(f"Fehler beim Laden: {e}")

elif symbol_source == "S&P500":
    try:
        df = pd.read_csv("https://datahub.io/core/s-and-p-500-companies/r/constituents.csv")
        symbols = df["Symbol"].dropna().tolist()
        st.sidebar.success(f"{len(symbols)} S&P500 Symbole geladen ✅")
    except Exception as e:
        st.sidebar.error(f"Fehler beim Laden: {e}")

elif symbol_source == "Gesamte NASDAQ":
    try:
        r = requests.get("https://datahub.io/core/nasdaq-listings/r/nasdaq-listed-symbols.csv")
        df = pd.read_csv(io.StringIO(r.text))
        symbols = df["Symbol"].dropna().tolist()
        st.sidebar.success(f"{len(symbols)} NASDAQ Symbole geladen ✅")
    except Exception as e:
        st.sidebar.error(f"Fehler beim Laden: {e}")

# --------------------------
# Scanner Einstellungen
# --------------------------
st.sidebar.header("Filter")
lookback = st.sidebar.number_input("Lookback Perioden (für Volumen)", min_value=5, max_value=100, value=20)
min_price = st.sidebar.number_input("Minimaler Preis ($)", min_value=0.0, value=2.0)
max_price = st.sidebar.number_input("Maximaler Preis ($)", min_value=0.0, value=20.0)
min_rvol = st.sidebar.number_input("Minimales RVOL (Relatives Volumen)", min_value=0.5, value=2.0)

if st.sidebar.button("🔄 Daten neu laden"):
    st.rerun()

# --------------------------
# Hilfsfunktion: robustes Spalten-Mapping
# --------------------------
def extract_columns(data, sym):
    close = None
    volume = None
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if (sym, "Close") in data.columns:
                close = data[(sym, "Close")]
            elif ("Close", sym) in data.columns:
                close = data[("Close", sym)]
            elif ("Close",) in data.columns:
                close = data[("Close",)]
            elif "Close" in data.columns:
                close = data["Close"]
            elif "Adj Close" in data.columns:
                close = data["Adj Close"]

            if (sym, "Volume") in data.columns:
                volume = data[(sym, "Volume")]
            elif ("Volume", sym) in data.columns:
                volume = data[("Volume", sym)]
            elif ("Volume",) in data.columns:
                volume = data[("Volume",)]
            elif "Volume" in data.columns:
                volume = data["Volume"]
        else:
            close = data.get("Close", data.get("Adj Close"))
            volume = data.get("Volume")
    except Exception:
        pass
    return close, volume


# --------------------------
# Daten abrufen & Filtern
# --------------------------
results = []

if symbols:
    end = datetime.now()
    start = end - timedelta(days=7)
    progress = st.progress(0)
    st.sidebar.write(f"Scanne {len(symbols)} Symbole...")

    for i, sym in enumerate(symbols):
        try:
            data = yf.download(sym, start=start, end=end, interval="1m", progress=False)
            if data.empty:
                data = yf.download(sym, start=start, end=end, interval="5m", progress=False)

            if data.empty:
                continue

            close, volume = extract_columns(data, sym)
            if close is None or volume is None:
                continue

            df = pd.DataFrame({"Close": close, "Volume": volume}).dropna()
            if df.empty:
                continue

            last_close = float(df["Close"].iloc[-1])
            avg_vol = float(df["Volume"].iloc[-lookback:].mean())
            current_vol = float(df["Volume"].iloc[-1])
            rvol = current_vol / avg_vol if avg_vol > 0 else 0.0

            if min_price <= last_close <= max_price and rvol >= min_rvol:
                results.append({
                    "Symbol": sym,
                    "Preis": round(last_close, 2),
                    "RVOL": round(rvol, 2),
                    "Letztes Volumen": int(current_vol),
                    "Ø Volumen": int(avg_vol)
                })

        except Exception:
            pass

        progress.progress((i + 1) / len(symbols))

# --------------------------
# Ergebnisse anzeigen
# --------------------------
st.subheader("📊 Scan-Ergebnisse")

if results:
    df = pd.DataFrame(results).sort_values(by="RVOL", ascending=False)
    st.write(f"Gefundene Treffer: **{len(df)}** von insgesamt {len(symbols)} gescannten Symbolen")
    st.dataframe(df, use_container_width=True)
    st.session_state["monitor_symbols"] = df["Symbol"].tolist()
else:
    st.warning("Keine Aktien erfüllen aktuell die Kriterien.")
    st.info("👉 Filter anpassen oder manuell Symbole unten eingeben.")
    st.session_state["monitor_symbols"] = []

# ============================================================
# 📈 MONITORING-FUNKTION – Echtzeitüberwachung der Treffer
# ============================================================
st.markdown("---")
st.header("📡 Live Monitoring der gefundenen Aktien")

# Manuelles Hinzufügen möglich
manual_symbols = st.text_input(
    "Symbole manuell hinzufügen (Komma getrennt)", 
    value=",".join(st.session_state.get("monitor_symbols", []))
)

if st.button("✅ Symbole übernehmen"):
    st.session_state["monitor_symbols"] = [s.strip().upper() for s in manual_symbols.split(",") if s.strip()]
    st.success("Symbole für Monitoring aktualisiert!")
    st.rerun()

monitor_symbols = st.session_state.get("monitor_symbols", [])
if not monitor_symbols:
    st.info("⚠️ Keine Symbole für das Monitoring vorhanden.")
else:
    refresh_rate = st.slider("⏱ Aktualisierung alle (Sekunden):", 30, 300, 60)
    st.write(f"Aktuell überwachte Symbole: {', '.join(monitor_symbols)}")

    data_rows = []
    for sym in monitor_symbols:
        try:
            data = yf.download(sym, period="1d", interval="1m", progress=False)
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
        except Exception:
            continue

    if data_rows:
        dfm = pd.DataFrame(data_rows)
        st.dataframe(dfm, use_container_width=True)
        st.caption(f"Letztes Update: {datetime.now().strftime('%H:%M:%S')}")
    else:
        st.warning("Keine Monitoring-Daten verfügbar.")

    if st.button("🔄 Jetzt aktualisieren"):
        st.rerun()
