import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
from datetime import datetime, timedelta

# --------------------------
# Einstellungen
# --------------------------
st.set_page_config(page_title="Aktien Breakout Scanner", layout="wide")

st.title("📈 Aktien Breakout Scanner ")

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
        url = "https://datahub.io/core/nasdaq-100-companies/r/constituents.csv"
        df = pd.read_csv(url)
        symbols = df["Symbol"].dropna().tolist()
        st.sidebar.success(f"{len(symbols)} NASDAQ-100 Symbole geladen")
    except Exception as e:
        st.sidebar.error(f"Fehler beim Laden: {e}")

elif symbol_source == "S&P500":
    try:
        url = "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv"
        df = pd.read_csv(url)
        symbols = df["Symbol"].dropna().tolist()
        st.sidebar.success(f"{len(symbols)} S&P500 Symbole geladen")
    except Exception as e:
        st.sidebar.error(f"Fehler beim Laden: {e}")

elif symbol_source == "Gesamte NASDAQ":
    try:
        url = "https://datahub.io/core/nasdaq-listings/r/nasdaq-listed-symbols.csv"
        r = requests.get(url)
        df = pd.read_csv(io.StringIO(r.text))
        symbols = df["Symbol"].dropna().tolist()
        st.sidebar.success(f"{len(symbols)} NASDAQ Symbole geladen")
    except Exception as e:
        st.sidebar.error(f"Fehler beim Laden: {e}")

# --------------------------
# Scanner Einstellungen
# --------------------------
st.sidebar.header("Scanner Einstellungen")
lookback = st.sidebar.number_input("Lookback Perioden (für Volumen)", min_value=5, max_value=100, value=20)
min_price = st.sidebar.number_input("Minimaler Preis ($)", min_value=0.0, value=2.0)
max_price = st.sidebar.number_input("Maximaler Preis ($)", min_value=0.0, value=20.0)
min_rvol = st.sidebar.number_input("Minimales RVOL (Relatives Volumen)", min_value=0.5, value=2.0)

# Refresh Button
if st.sidebar.button("🔄 Daten neu laden"):
    st.rerun()

# --------------------------
# Daten abrufen & Filtern
# --------------------------
results = []

if symbols:
    end = datetime.now()
    start = end - timedelta(days=7)  # wir brauchen einige Tage für Intraday-Daten
    
    progress = st.progress(0)
    st.sidebar.write(f"Scanne {len(symbols)} Symbole...")

    for i, sym in enumerate(symbols):
        try:
            # Versuche 1m-Daten, sonst fallback auf 5m
            data = yf.download(sym, start=start, end=end, interval="1m", progress=False)
            if data.empty:
                data = yf.download(sym, start=start, end=end, interval="5m", progress=False)
            
            if data.empty:
                st.sidebar.write(f"{sym}: ❌ keine Daten")
                continue

            last_close = data["Close"].iloc[-1]
            avg_vol = data["Volume"].iloc[-lookback:].mean()
            current_vol = data["Volume"].iloc[-1]
            rvol = current_vol / avg_vol if avg_vol > 0 else 0

            # Filter anwenden
            if min_price <= last_close <= max_price and rvol >= min_rvol:
                results.append({
                    "Symbol": sym,
                    "Preis": round(last_close, 2),
                    "RVOL": round(rvol, 2),
                    "Letztes Volumen": int(current_vol),
                    "Ø Volumen": int(avg_vol)
                })
            
            st.sidebar.write(f"{sym}: OK (Preis {round(last_close,2)} | RVOL {round(rvol,2)})")

        except Exception as e:
            st.sidebar.write(f"{sym}: Fehler ({e})")
            continue

        progress.progress((i + 1) / len(symbols))

# --------------------------
# Ergebnisse anzeigen
# --------------------------
st.subheader("📊 Scan-Ergebnisse")

if results:
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(by="RVOL", ascending=False)
    st.write(f"Gefundene Treffer: **{len(df_results)}** von insgesamt {len(symbols)} gescannten Symbolen")
    st.dataframe(df_results, use_container_width=True)
else:
    st.warning(f"Keine Aktien erfüllen aktuell die Kriterien. Gescannt: {len(symbols)} Symbole.")
    st.info("👉 Tipp: Filter lockern (z. B. RVOL auf 1.0 setzen oder Preisspanne erhöhen)")
