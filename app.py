import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
import time
from datetime import datetime, timedelta

# --------------------------
# Seiteneinstellungen
# --------------------------
st.set_page_config(page_title="📈 Aktien Breakout Scanner", layout="wide")
st.title("📊 Aktien Breakout Scanner (NASDAQ / S&P500)")

if "monitor_symbols" not in st.session_state:
    st.session_state["monitor_symbols"] = []

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
# Hilfsfunktion: Spalten-Mapping
# --------------------------
def extract_columns(data, sym):
    """Sucht Close- und Volume-Spalten robust."""
    try:
        if isinstance(data.columns, pd.MultiIndex):
            close = data.get((sym, "Close"), data.get(("Close", sym), data.get("Close")))
            volume = data.get((sym, "Volume"), data.get(("Volume", sym), data.get("Volume")))
        else:
            close = data.get("Close", data.get("Adj Close"))
            volume = data.get("Volume")
        return close, volume
    except Exception:
        return None, None

# --------------------------
# Scan durchführen
# --------------------------
results = []
if symbols:
    end = datetime.now()
    start = end - timedelta(days=7)
    progress = st.progress(0)
    st.sidebar.write(f"Scanne {len(symbols)} Symbole...")

    for i, sym in enumerate(symbols):
        try:
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
            continue

        progress.progress((i + 1) / len(symbols))

# --------------------------
# Ergebnisse anzeigen
# --------------------------
st.subheader("📊 Scan-Ergebnisse")

if results:
    df = pd.DataFrame(results).sort_values(by="RVOL", ascending=False)
    st.write(f"Gefundene Treffer: **{len(df)}** von {len(symbols)} Symbolen")
    st.dataframe(df, use_container_width=True)

    # Symbol hinzufügen zum Monitor
    add_symbol = st.selectbox("➡️ Symbol zum Monitor hinzufügen", ["–"] + df["Symbol"].tolist())
    if add_symbol != "–":
        if add_symbol not in st.session_state["monitor_symbols"]:
            st.session_state["monitor_symbols"].append(add_symbol)
            st.success(f"{add_symbol} wurde dem Monitor hinzugefügt ✅")
else:
    st.warning("Keine Aktien erfüllen aktuell die Kriterien.")

# --------------------------
# Monitor
# --------------------------
st.subheader("📺 Live Monitor")

col1, col2 = st.columns([3, 1])
with col2:
    manual_symbol = st.text_input("Manuell Symbol hinzufügen (z. B. NVDA)")
    if st.button("➕ Symbol hinzufügen"):
        if manual_symbol and manual_symbol.upper() not in st.session_state["monitor_symbols"]:
            st.session_state["monitor_symbols"].append(manual_symbol.upper())
            st.success(f"{manual_symbol.upper()} hinzugefügt ✅")

if not st.session_state["monitor_symbols"]:
    st.info("Noch keine Symbole im Monitor. Füge welche hinzu aus den Scan-Ergebnissen oder manuell.")
else:
    refresh_rate = st.sidebar.number_input("⏱️ Aktualisierungsrate (Sekunden)", min_value=10, max_value=300, value=60)
    data_list = []

    for sym in st.session_state["monitor_symbols"]:
        try:
            data = yf.download(sym, period="1d", interval="1m", progress=False)
            if data is not None and not data.empty:
                last = data["Close"].iloc[-1]
                prev = data["Close"].iloc[-2] if len(data) > 1 else last
                delta = ((last - prev) / prev) * 100 if prev != 0 else 0
                data_list.append({
                    "Symbol": sym,
                    "Kurs": round(float(last), 2),
                    "Δ%": round(float(delta), 2)
                })
        except Exception as e:
            st.write(f"{sym}: ❌ Fehler ({str(e)[:50]})")

    if len(data_list) > 0:
        dfm = pd.DataFrame(data_list).sort_values(by="Δ%", ascending=False)

        def color_change(val):
            try:
                val = float(val)
                if val > 0:
                    return "background-color: rgba(0,255,0,0.2); color: green;"
                elif val < 0:
                    return "background-color: rgba(255,0,0,0.2); color: red;"
                else:
                    return "color: gray;"
            except Exception:
                return "color: gray;"

        st.dataframe(dfm.style.applymap(color_change, subset=["Δ%"]), width="stretch")
        st.caption(f"🔄 Aktualisierung alle {refresh_rate} Sekunden – Stand: {datetime.now().strftime('%H:%M:%S')}")
    else:
        st.warning("Keine Kursdaten für die überwachten Symbole gefunden.")

    time.sleep(refresh_rate)
    st.rerun()
