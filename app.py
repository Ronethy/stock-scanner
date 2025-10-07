import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
from datetime import datetime, timedelta

# --------------------------
# App-Einstellungen
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
# Session-State für Monitor
# --------------------------
if "monitor" not in st.session_state:
    st.session_state.monitor = []

# --------------------------
# Hilfsfunktion: Spalten finden (robust)
# --------------------------
def extract_columns(data):
    """
    Extrahiert Close- und Volume-Spalten aus yfinance-DataFrame.
    Funktioniert mit einfachem oder MultiIndex.
    """
    close, volume = None, None
    try:
        if isinstance(data.columns, pd.MultiIndex):
            # Alle möglichen Varianten prüfen
            for col in data.columns:
                if "close" in str(col).lower():
                    close = data[col]
                if "volume" in str(col).lower():
                    volume = data[col]
        else:
            if "Close" in data.columns:
                close = data["Close"]
            elif "Adj Close" in data.columns:
                close = data["Adj Close"]
            if "Volume" in data.columns:
                volume = data["Volume"]

    except Exception as e:
        st.sidebar.warning(f"Spaltenproblem: {e}")

    return close, volume

# --------------------------
# Daten abrufen & filtern
# --------------------------
results = []

if symbols:
    end = datetime.now()
    start = end - timedelta(days=7)
    progress = st.progress(0)
    st.sidebar.write(f"Scanne {len(symbols)} Symbole...")

    for i, sym in enumerate(symbols):
        try:
            data = yf.download(sym, start=start, end=end, interval="1h", progress=False, auto_adjust=False)
            if data.empty:
                continue

            close, volume = extract_columns(data)
            if close is None or volume is None:
                st.sidebar.write(f"{sym}: ⚠️ Keine Close/Volume-Daten")
                continue

            df = pd.DataFrame({"Close": close, "Volume": volume}).dropna()
            if df.empty:
                continue

            last_close = df["Close"].iloc[-1]
            avg_vol = df["Volume"].iloc[-lookback:].mean()
            current_vol = df["Volume"].iloc[-1]
            rvol = current_vol / avg_vol if avg_vol > 0 else 0.0

            if min_price <= last_close <= max_price and rvol >= min_rvol:
                results.append({
                    "Symbol": sym,
                    "Preis": round(last_close, 2),
                    "RVOL": round(rvol, 2),
                    "Letztes Volumen": int(current_vol),
                    "Ø Volumen": int(avg_vol)
                })

        except Exception as e:
            st.sidebar.write(f"{sym}: ❌ Fehler ({str(e)[:80]})")

        progress.progress((i + 1) / len(symbols))

# --------------------------
# Ergebnisse anzeigen
# --------------------------
st.subheader("📊 Scan-Ergebnisse")

if results:
    df = pd.DataFrame(results).sort_values(by="RVOL", ascending=False)
    st.write(f"Gefundene Treffer: **{len(df)}** von {len(symbols)} gescannten Symbolen")

    # Heatmap mit Farbverlauf
    def color_rvol(val):
        color = "green" if val >= 2 else "orange" if val >= 1 else "red"
        return f"background-color: {color}; color: white; font-weight: bold;"

    st.dataframe(df.style.applymap(color_rvol, subset=["RVOL"]), width="stretch")

    # Buttons für Monitor
    for sym in df["Symbol"]:
        if st.button(f"📈 {sym} zum Monitor hinzufügen"):
            if sym not in st.session_state.monitor:
                st.session_state.monitor.append(sym)
                st.success(f"{sym} wurde dem Monitor hinzugefügt ✅")
                st.rerun()
else:
    st.warning("Keine Aktien erfüllen aktuell die Kriterien.")

# --------------------------
# Live-Monitor
# --------------------------
st.subheader("🖥️ Echtzeit-Monitor")

if st.session_state.monitor:
    refresh_rate = st.slider("Aktualisierungsrate (Sekunden)", 10, 120, 30)
    monitor_data = []

    for sym in st.session_state.monitor:
        try:
            data = yf.download(sym, period="1d", interval="1m", progress=False, auto_adjust=False)
            if data.empty:
                continue
            close = data["Close"] if "Close" in data else data["Adj Close"]
            last = close.iloc[-1]
            prev = close.iloc[-2]
            change = ((last - prev) / prev) * 100
            monitor_data.append({"Symbol": sym, "Preis": round(last, 2), "Δ%": round(change, 2)})
        except Exception as e:
            st.write(f"{sym}: ❌ Fehler ({e})")

    if monitor_data:
        dfm = pd.DataFrame(monitor_data)
        def color_change(val):
            color = "green" if val > 0 else "red" if val < 0 else "gray"
            return f"background-color: {color}; color: white; font-weight: bold;"

        st.dataframe(dfm.style.applymap(color_change, subset=["Δ%"]), width="stretch")
    else:
        st.info("Keine aktuellen Daten verfügbar.")

    if st.button("🔄 Jetzt aktualisieren"):
        st.rerun()
else:
    st.info("Noch keine Symbole im Monitor. Füge oben welche hinzu mit dem Button „📈 zum Monitor hinzufügen“.")
