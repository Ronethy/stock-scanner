import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Stock Scanner & Monitor", layout="wide")

# =========================================================
# Symbol-Listen laden (S&P500 + NASDAQ)
# =========================================================
@st.cache_data
def load_symbol_lists():
    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        nasdaq = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")[0]
        sp500_symbols = sp500["Symbol"].to_list()
        nasdaq_symbols = nasdaq["Ticker"].to_list()
    except Exception:
        sp500_symbols, nasdaq_symbols = [], []
    return sp500_symbols, nasdaq_symbols


# =========================================================
# Daten abrufen
# =========================================================
def get_data(symbol, days=5):
    try:
        end = datetime.now()
        start = end - timedelta(days=days)
        data = yf.download(symbol, start=start, end=end, interval="1d", progress=False)
        if data.empty:
            return None

        data["RelVol"] = data["Volume"] / data["Volume"].rolling(50).mean()
        data["Δ%"] = (data["Close"] - data["Open"]) / data["Open"] * 100
        return data.iloc[-1]
    except Exception:
        return None


# =========================================================
# Symbol-Scanner
# =========================================================
def symbol_scanner(symbols, min_price, max_price, min_relvol):
    found = []
    for sym in symbols:
        data = get_data(sym)
        if data is None:
            continue
        if (
            min_price <= data["Close"] <= max_price
            and data["RelVol"] >= min_relvol
        ):
            found.append({
                "Symbol": sym,
                "Close": round(data["Close"], 2),
                "Δ%": round(data["Δ%"], 2),
                "RelVol": round(data["RelVol"], 2)
            })
    return found


# =========================================================
# App-Layout
# =========================================================
def main():
    st.title("📊 Realtime Stock Scanner & Monitor")

    tab1, tab2 = st.tabs(["🔍 Scanner", "🖥️ Monitor"])

    sp500_symbols, nasdaq_symbols = load_symbol_lists()
    all_symbols = sorted(list(set(sp500_symbols + nasdaq_symbols)))

    # ------------------ TAB 1: SCANNER ------------------
    with tab1:
        st.header("🔎 Symbol-Scanner")

        min_price = st.number_input("Minimaler Preis", 0.0, 10000.0, 5.0)
        max_price = st.number_input("Maximaler Preis", 0.0, 10000.0, 200.0)
        min_relvol = st.number_input("Min. Relatives Volumen", 0.0, 50.0, 1.5)

        if st.button("🚀 Scan starten"):
            with st.spinner("Scanne Märkte..."):
                found = symbol_scanner(all_symbols, min_price, max_price, min_relvol)

            if len(found) > 0:
                df = pd.DataFrame(found)
                st.success(f"{len(df)} Symbole gefunden!")
                st.dataframe(df.sort_values(by="Δ%", ascending=False), use_container_width=True)
            else:
                st.warning("Keine Symbole gefunden. Passe deine Filter an.")

    # ------------------ TAB 2: MONITOR ------------------
    with tab2:
        st.header("🖥️ Live-Monitor")

        if "monitor_symbols" not in st.session_state:
            st.session_state.monitor_symbols = []

        # Eingabefeld zum Hinzufügen
        new_symbol = st.text_input("Symbol hinzufügen (z. B. AAPL, MSFT):").upper()
        if st.button("➕ Hinzufügen"):
            if new_symbol and new_symbol not in st.session_state.monitor_symbols:
                st.session_state.monitor_symbols.append(new_symbol)
            else:
                st.info("Symbol bereits vorhanden oder ungültig.")

        if st.session_state.monitor_symbols:
            refresh_rate = st.slider("⏱️ Aktualisierungsrate (Sekunden)", 10, 300, 60)
            st.write("Aktive Symbole:", ", ".join(st.session_state.monitor_symbols))

            data_list = []
            for sym in st.session_state.monitor_symbols:
                data = get_data(sym, days=2)
                if data is not None:
                    data_list.append({
                        "Symbol": sym,
                        "Kurs": round(data["Close"], 2),
                        "Δ%": round(data["Δ%"], 2),
                        "RelVol": round(data["RelVol"], 2)
                    })

            if len(data_list) > 0:
                dfm = pd.DataFrame.from_records(data_list)
                dfm = dfm.sort_values(by="Δ%", ascending=False)

                # --- Heatmap ---
                def color_change(val):
                    try:
                        v = float(val)
                        if v > 0:
                            return "background-color: rgba(0,255,0,0.15); color: green;"
                        elif v < 0:
                            return "background-color: rgba(255,0,0,0.15); color: red;"
                        else:
                            return "color: gray;"
                    except Exception:
                        return "color: gray;"

                st.dataframe(
                    dfm.style.applymap(color_change, subset=["Δ%"]),
                    use_container_width=True,
                )
                st.caption(f"🔄 Aktualisierung alle {refresh_rate}s – Stand: {datetime.now().strftime('%H:%M:%S')}")

                time.sleep(refresh_rate)
                st.rerun()

            else:
                st.warning("Keine Kursdaten für die überwachten Symbole gefunden.")
        else:
            st.info("Füge Symbole hinzu, um den Monitor zu starten.")


# =========================================================
# Start
# =========================================================
if __name__ == "__main__":
    main()
