import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
from datetime import datetime, timedelta

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
                st.sidebar.write(f"{sym}: ❌ Keine Daten")
                continue

            # Prüfen auf MultiIndex (manchmal mehrere Ebenen)
            if isinstance(data.columns, pd.MultiIndex):
                if (sym, "Close") in data.columns:
                    close = data[(sym, "Close")]
                    volume = data[(sym, "Volume")]
                else:
                    close = data.xs("Close", axis=1, level=-1).iloc[:, 0]
                    volume = data.xs("Volume", axis=1, level=-1).iloc[:, 0]
            else:
                # Fallbacks prüfen
                if "Close" in data.columns:
                    close = data["Close"]
                elif "Adj Close" in data.columns:
                    close = data["Adj Close"]
                else:
                    st.sidebar.write(f"{sym}: ⚠️ Keine 'Close'-Daten")
                    continue

                if "Volume" in data.columns:
                    volume = data["Volume"]
                else:
                    st.sidebar.write(f"{sym}: ⚠️ Keine 'Volume'-Daten")
                    continue

            # Bereinigen
            data = pd.DataFrame({"Close": close, "Volume": volume}).dropna()
            if data.empty:
                st.sidebar.write(f"{sym}: ⚠️ Keine gültigen Werte")
                continue

            last_close = float(data["Close"].iloc[-1])
            avg_vol = float(data["Volume"].iloc[-lookback:].mean())
            current_vol = float(data["Volume"].iloc[-1])
            rvol = current_vol / avg_vol if avg_vol > 0 else 0.0

            # Filter anwenden
            if min_price <= last_close <= max_price and rvol >= min_rvol:
                results.append({
                    "Symbol": sym,
                    "Preis": round(last_close, 2),
                    "RVOL": round(rvol, 2),
                    "Letztes Volumen": int(current_vol),
                    "Ø Volumen": int(avg_vol)
                })

            st.sidebar.write(f"{sym}: ✅ OK (Preis {round(last_close,2)} | RVOL {round(rvol,2)})")

        except Exception as e:
            st.sidebar.write(f"{sym}: Fehler ({str(e)[:80]})")

        progress.progress((i + 1) / len(symbols))

# --------------------------
# Ergebnisse anzeigen
# --------------------------
st.subheader("📊 Scan-Ergebnisse")

if results:
    df = pd.DataFrame(results).sort_values(by="RVOL", ascending=False)
    st.write(f"Gefundene Treffer: **{len(df)}** von insgesamt {len(symbols)} gescannten Symbolen")
    st.dataframe(df, use_container_width=True)
else:
    st.warning(f"Keine Aktien erfüllen aktuell die Kriterien. Gescannt: {len(symbols)} Symbole.")
    st.info("👉 Tipp: Filter lockern (z. B. RVOL auf 1.0 setzen oder Preisspanne erhöhen)")
