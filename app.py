import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import io
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ------------------------------------------------------
# Seiteneinstellungen
# ------------------------------------------------------
st.set_page_config(page_title="📈 Aktien Scanner & Monitor", layout="wide")
st.title("📈 Aktien Scanner & Live Monitoring")

# ------------------------------------------------------
# Tabs
# ------------------------------------------------------
tab1, tab2 = st.tabs(["📊 Scanner", "📈 Monitor"])

# ------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------
def get_symbol_list(source: str):
    """Lädt Symbol-Listen von verschiedenen Quellen."""
    if source == "NASDAQ-100":
        df = pd.read_csv("https://datahub.io/core/nasdaq-100-companies/r/constituents.csv")
        return df["Symbol"].dropna().tolist()
    elif source == "S&P500":
        df = pd.read_csv("https://datahub.io/core/s-and-p-500-companies/r/constituents.csv")
        return df["Symbol"].dropna().tolist()
    elif source == "Gesamte NASDAQ":
        r = requests.get("https://datahub.io/core/nasdaq-listings/r/nasdaq-listed-symbols.csv")
        df = pd.read_csv(io.StringIO(r.text))
        return df["Symbol"].dropna().tolist()
    else:
        return []


def download_data(symbols, lookback=20):
    """Lädt Marktdaten und berechnet RVOL."""
    end = datetime.now()
    start = end - timedelta(days=2)
    results = []

    for sym in symbols:
        try:
            data = yf.download(sym, start=start, end=end, interval="1m", progress=False)
            if data.empty:
                continue

            close = data["Close"]
            volume = data["Volume"]
            last_close = close.iloc[-1]
            avg_vol = volume[-lookback:].mean()
            curr_vol = volume.iloc[-1]
            rvol = curr_vol / avg_vol if avg_vol > 0 else 0

            results.append({
                "Symbol": sym,
                "Preis": round(last_close, 2),
                "RVOL": round(rvol, 2),
                "Volumen": int(curr_vol),
                "Ø Volumen": int(avg_vol)
            })
        except Exception as e:
            st.sidebar.write(f"{sym}: Fehler ({e})")
    return pd.DataFrame(results)


# ------------------------------------------------------
# TAB 1 – Scanner
# ------------------------------------------------------
with tab1:
    st.subheader("📊 Universum-Scanner")

    col1, col2, col3 = st.columns(3)
    with col1:
        source = st.selectbox("Symbolquelle", ["Eigene Watchlist", "NASDAQ-100", "S&P500", "Gesamte NASDAQ"])
    with col2:
        min_price = st.number_input("Minimaler Preis ($)", 0.0, 1000.0, 2.0)
    with col3:
        max_price = st.number_input("Maximaler Preis ($)", 0.0, 1000.0, 20.0)

    lookback = st.number_input("Volumen-Durchschnitt (Perioden)", 5, 100, 20)
    min_rvol = st.number_input("Minimales RVOL", 0.5, 10.0, 2.0)

    symbols = []
    if source == "Eigene Watchlist":
        input_syms = st.text_area("Symbole (Komma getrennt)", "AAPL,TSLA,AMD,NIO,PLTR")
        symbols = [s.strip().upper() for s in input_syms.split(",") if s.strip()]
    else:
        with st.spinner("Lade Symbol-Liste..."):
            symbols = get_symbol_list(source)

    if st.button("🚀 Scan starten"):
        with st.spinner("Scanne Markt..."):
            df = download_data(symbols, lookback)
            df = df[(df["Preis"] >= min_price) & (df["Preis"] <= max_price) & (df["RVOL"] >= min_rvol)]
            if df.empty:
                st.warning("Keine Aktien erfüllen aktuell die Kriterien.")
            else:
                st.success(f"{len(df)} Aktien gefunden")
                st.dataframe(df, use_container_width=True)

                # Möglichkeit zur Übernahme in Monitor
                st.session_state["watchlist"] = df["Symbol"].tolist()
                st.info(f"✅ {len(df)} Symbole in Watchlist übernommen – wechsle zum Reiter 📈 Monitor.")

# ------------------------------------------------------
# TAB 2 – Monitoring
# ------------------------------------------------------
with tab2:
    st.subheader("📈 Live-Monitoring")

    # automatischer Refresh alle 60 Sekunden
    st_autorefresh(interval=60 * 1000, key="refresh")

    if "watchlist" not in st.session_state or not st.session_state["watchlist"]:
        st.info("⚠️ Noch keine Symbole in der Watchlist. Bitte zuerst im Scanner scannen.")
    else:
        watchlist = st.session_state["watchlist"]
        st.write(f"Überwache aktuell {len(watchlist)} Symbole:", ", ".join(watchlist))

        with st.spinner("Lade aktuelle Marktdaten..."):
            df = download_data(watchlist, lookback=20)

        if "prev_data" in st.session_state:
            prev = st.session_state["prev_data"].set_index("Symbol")
            df = df.set_index("Symbol")
            df["Δ Preis %"] = ((df["Preis"] - prev["Preis"]) / prev["Preis"] * 100).round(2)
            df["Δ RVOL"] = (df["RVOL"] - prev["RVOL"]).round(2)
            df.reset_index(inplace=True)
        else:
            df["Δ Preis %"] = 0.0
            df["Δ RVOL"] = 0.0

        st.session_state["prev_data"] = df.copy()

        # farbige Anzeige
        def color_cells(val):
            if isinstance(val, (float, int)):
                if val > 0:
                    return "background-color:#d1ffd1"  # grün
                elif val < 0:
                    return "background-color:#ffd1d1"  # rot
            return ""

        st.dataframe(df.style.applymap(color_cells, subset=["Δ Preis %", "Δ RVOL"]), use_container_width=True)
