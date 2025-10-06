"""
app.py

Ein Single-File Streamlit-App mit zwei Tabs:
 - Scanner: scannt Symbol-Listen (Eigene Watchlist / NASDAQ-100 / S&P500 / Gesamte NASDAQ)
   und zeigt Treffer (RVOL / Preis). Du kannst Treffer auswählen und mit einem Klick
   in die Monitor-Watchlist übernehmen.

 - Monitor: überwacht die übernommene Watchlist im 1-Minuten-Takt (Auto-Refresh).
   Zeigt aktuelle Werte + Veränderungen gegenüber dem letzten Monitor-Check
   (Δ Preis %, Δ RVOL) und markiert positive/negative Veränderungen farbig.

Wichtig:
- Diese App nutzt yfinance für 1m/5m Daten. Yahoo liefert nicht immer 1m für alle Symbole.
- In Streamlit Cloud ist das Schreiben ins GitHub-Repo nicht möglich. Diese App speichert
  alles im Session-State (kein CSV nötig).
- Installations-Requirements:
    pip install streamlit yfinance pandas numpy requests streamlit-autorefresh
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import io
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import time

# ---------------------------
# App-Setup
# ---------------------------
st.set_page_config(page_title="Scanner + Monitor", layout="wide")
st.title("📈 RVOL Breakout Scanner & Live Monitor")

# Initialize session state containers
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []               # list of symbols the user wants to monitor
if "monitor_data" not in st.session_state:
    st.session_state.monitor_data = {}            # symbol -> last snapshot dict {price, rvol, time}
if "last_scan_results" not in st.session_state:
    st.session_state.last_scan_results = []       # last scan results list of dicts

# ---------------------------
# Helper: robust column extraction from yfinance output
# ---------------------------
def extract_close_volume(df, sym):
    """
    Given a DataFrame returned by yfinance for a *single symbol* request,
    return (close_series, volume_series) robustly handling MultiIndex variants.
    Returns (None, None) if not found.
    """
    # Some yfinance responses use MultiIndex columns in different orders:
    # - (sym, 'Close') or ('Close', sym) or ('Close',) or 'Close'
    try:
        cols = df.columns
    except Exception:
        return None, None

    # Quick debug (only when debugging, otherwise comment out)
    # st.sidebar.write(f"{sym} columns: {list(cols)}")

    # If MultiIndex
    if isinstance(cols, pd.MultiIndex):
        # Try common patterns
        # (sym, 'Close')
        if (sym, "Close") in cols:
            close = df[(sym, "Close")]
        elif ("Close", sym) in cols:
            close = df[("Close", sym)]
        else:
            # try pick all close-level columns and take first
            try:
                close_all = df.xs("Close", axis=1, level=-1, drop_level=False)
                # if multiple, try to pick column containing sym
                if (sym,) in close_all.columns:
                    close = close_all[(sym,)]
                else:
                    close = close_all.iloc[:, 0]
            except Exception:
                close = None

        # Volume
        if (sym, "Volume") in cols:
            vol = df[(sym, "Volume")]
        elif ("Volume", sym) in cols:
            vol = df[("Volume", sym)]
        else:
            try:
                vol_all = df.xs("Volume", axis=1, level=-1, drop_level=False)
                vol = vol_all.iloc[:, 0]
            except Exception:
                vol = None

    else:
        # Normal columns
        if "Close" in df.columns:
            close = df["Close"]
        elif "Adj Close" in df.columns:
            close = df["Adj Close"]
        else:
            close = None

        vol = df.get("Volume", None)

    return close, vol

# ---------------------------
# Helper: get data safe
# ---------------------------
def fetch_intraday(symbol, period_days=7, interval_try=["1m", "5m"]):
    """
    Try to fetch intraday data with preferred intervals until success.
    Returns a DataFrame or None.
    """
    end = datetime.utcnow()  # yfinance server expects UTC-ish times; it accepts start/end or period
    start = end - timedelta(days=period_days)
    for interval in interval_try:
        try:
            # use period + interval is also possible, but using start/end reduces ambiguity
            df = yf.download(symbol, start=start, end=end, interval=interval, progress=False, threads=False)
            if df is None:
                continue
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception:
            # network/format errors -> try next
            time.sleep(0.1)
            continue
    return None

# ---------------------------
# Sidebar: global controls
# ---------------------------
st.sidebar.markdown("## App-Steuerung")
st.sidebar.markdown("Wähle Tab oben: **Scanner** zum Finden von Kandidaten, **Monitor** zum Überwachen der übernommenen Symbole.")

# ---------------------------
# Tabs for UI
# ---------------------------
tab = st.tabs(["Scanner", "Monitor"])
scanner_tab = tab[0]
monitor_tab = tab[1]

# ---------------------------
# Scanner Tab
# ---------------------------
with scanner_tab:
    st.header("📊 Scanner")
    st.markdown("Scanne Symbollisten nach RVOL-/Preis-Filtern. Wähle Treffer aus und übernehme sie in den Monitor.")

    # Symbol source selection
    source = st.selectbox("Symbol-Quelle", ["Eigene Watchlist", "NASDAQ-100", "S&P500", "Gesamte NASDAQ"])
    symbols = []
    if source == "Eigene Watchlist":
        input_text = st.text_area("Symbole (Komma getrennt)", value="AAPL,TSLA,AMD,NIO,PLTR", height=80)
        symbols = [s.strip().upper() for s in input_text.split(",") if s.strip()]
    elif source == "NASDAQ-100":
        st.write("Lade NASDAQ-100 Liste...")
        try:
            df_n100 = pd.read_csv("https://datahub.io/core/nasdaq-100-companies/r/constituents.csv")
            symbols = df_n100["Symbol"].dropna().tolist()
            st.success(f"NASDAQ-100 geladen ({len(symbols)} Symbole)")
        except Exception as e:
            st.error(f"Fehler beim Laden NASDAQ-100: {e}")
    elif source == "S&P500":
        st.write("Lade S&P500 Liste...")
        try:
            df_sp = pd.read_csv("https://datahub.io/core/s-and-p-500-companies/r/constituents.csv")
            symbols = df_sp["Symbol"].dropna().tolist()
            st.success(f"S&P500 geladen ({len(symbols)} Symbole)")
        except Exception as e:
            st.error(f"Fehler beim Laden S&P500: {e}")
    elif source == "Gesamte NASDAQ":
        st.write("Lade NASDAQ-Liste (groß)...")
        try:
            r = requests.get("https://datahub.io/core/nasdaq-listings/r/nasdaq-listed-symbols.csv", timeout=20)
            df_all = pd.read_csv(io.StringIO(r.text))
            symbols = df_all["Symbol"].dropna().tolist()
            st.success(f"Gesamte NASDAQ geladen ({len(symbols)} Symbole)")
        except Exception as e:
            st.error(f"Fehler beim Laden NASDAQ-Liste: {e}")

    # Scanner Filters
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        lookback = st.number_input("Volumen-Durchschnitt über N Bars", min_value=5, max_value=300, value=50)
        min_rvol = st.number_input("Mindest-RVOL (current / avg)", min_value=0.5, value=2.0, step=0.1)
    with col2:
        min_price = st.number_input("Min Preis ($)", min_value=0.0, value=2.0)
        max_price = st.number_input("Max Preis ($)", min_value=0.0, value=20.0)
    with col3:
        max_symbols = st.number_input("Max Symbole zum Scannen (Performance)", min_value=10, max_value=5000, value=200)
        run_scan_btn = st.button("🔎 Scan starten")

    # Scan results area
    results_container = st.container()

    if run_scan_btn:
        if not symbols:
            st.warning("Keine Symbole ausgewählt. Bitte eine Symbol-Liste auswählen oder eingeben.")
        else:
            # limit symbols for performance
            symbols_to_scan = symbols[:int(max_symbols)]
            st.info(f"Starte Scan für {len(symbols_to_scan)} Symbole (dies kann eine Weile dauern)...")
            progress_bar = st.progress(0)
            scan_results = []
            for idx, s in enumerate(symbols_to_scan):
                df = fetch_intraday(s, period_days=7, interval_try=["1m","5m"])
                if df is None or df.empty:
                    # mark in sidebar (light) - but avoid flooding for large lists
                    if idx < 20:
                        st.sidebar.write(f"{s}: keine Daten")
                    progress_bar.progress((idx+1)/len(symbols_to_scan))
                    continue

                close_ser, vol_ser = extract_close_volume(df, s)
                if close_ser is None or vol_ser is None:
                    if idx < 20:
                        st.sidebar.write(f"{s}: keine Close/Volume-Spalten")
                    progress_bar.progress((idx+1)/len(symbols_to_scan))
                    continue

                # build cleaned frame
                tmp = pd.DataFrame({"Close": close_ser, "Volume": vol_ser}).dropna()
                if tmp.empty or len(tmp) < lookback+1:
                    if idx < 20:
                        st.sidebar.write(f"{s}: zu wenige gültige Bars ({len(tmp)})")
                    progress_bar.progress((idx+1)/len(symbols_to_scan))
                    continue

                last_close = float(tmp["Close"].iloc[-1])
                curr_vol = float(tmp["Volume"].iloc[-1])
                avg_vol = float(tmp["Volume"].iloc[-lookback:-1].mean()) if lookback>0 else float(tmp["Volume"].iloc[:-1].mean())
                if avg_vol <= 0:
                    progress_bar.progress((idx+1)/len(symbols_to_scan))
                    continue
                rvol = curr_vol / avg_vol

                # filters
                if (min_price <= last_close <= max_price) and (rvol >= min_rvol):
                    scan_results.append({
                        "Symbol": s,
                        "Price": round(last_close, 4),
                        "%Change": round((tmp["Close"].iloc[-1] - tmp["Close"].iloc[-2]) / tmp["Close"].iloc[-2] * 100, 3) if len(tmp)>=2 else 0.0,
                        "RVOL": round(rvol, 2),
                        "CurrentVolume": int(curr_vol),
                        "AvgVolume": int(avg_vol)
                    })

                progress_bar.progress((idx+1)/len(symbols_to_scan))

            # store last scan results in session_state
            st.session_state.last_scan_results = scan_results

            with results_container:
                st.subheader("Scan-Ergebnisse")
                if not scan_results:
                    st.info("Keine Treffer. Filter anpassen.")
                else:
                    df_res = pd.DataFrame(scan_results).sort_values(by=["%Change","RVOL"], ascending=[False, False]).reset_index(drop=True)
                    # allow user to select rows to add to monitor
                    st.write("Wähle Symbole aus, die du in den Monitor übernehmen möchtest:")
                    # show with checkboxes
                    picks = []
                    cols = st.columns([1,1,1,1,1,1])
                    # Build a table-like layout with checkboxes per row
                    selected = []
                    for i, row in df_res.iterrows():
                        c0, c1, c2, c3, c4, c5 = st.columns([0.5,1.2,1,1,1,1])
                        with c0:
                            sel = st.checkbox("", key=f"pick_{row['Symbol']}")
                        with c1:
                            st.write(f"**{row['Symbol']}**")
                        with c2:
                            st.write(f"Price: ${row['Price']}")
                        with c3:
                            st.write(f"%Δ: {row['%Change']}%")
                        with c4:
                            st.write(f"RVOL: {row['RVOL']}x")
                        with c5:
                            st.write(f"Vol: {row['CurrentVolume']}")
                        if sel:
                            selected.append(row["Symbol"])

                    if st.button("➡️ Ausgewählte Symbole in Monitor übernehmen"):
                        # Add selected to session_state.watchlist & initialize monitor_data if missing
                        added = 0
                        for sym in selected:
                            if sym not in st.session_state.watchlist:
                                st.session_state.watchlist.append(sym)
                                # initialize monitor_data entry
                                st.session_state.monitor_data[sym] = {
                                    "price": None,
                                    "rvol": None,
                                    "last_checked": None
                                }
                                added += 1
                        st.success(f"{added} Symbole zur Watchlist hinzugefügt.")
                        st.experimental_rerun()

# ---------------------------
# Monitor Tab
# ---------------------------
with monitor_tab:
    st.header("📈 Live Monitor")
    st.markdown("Zeigt die Überwachten Symbole (Watchlist). Aktualisiert jede Minute automatisch.")
    st.write("Watchlist (manuell editierbar):")
    # display & allow manual edit of watchlist
    wl = st.session_state.watchlist
    wl_text = st.text_area("Watchlist (Komma getrennt) — ändere hier und klicke 'Update Watchlist'", value=",".join(wl))
    if st.button("Update Watchlist"):
        new_wl = [s.strip().upper() for s in wl_text.split(",") if s.strip()]
        st.session_state.watchlist = new_wl
        # ensure monitor_data keys exist
        for sym in new_wl:
            if sym not in st.session_state.monitor_data:
                st.session_state.monitor_data[sym] = {"price": None, "rvol": None, "last_checked": None}
        st.experimental_rerun()

    if not st.session_state.watchlist:
        st.info("Deine Watchlist ist leer. Gehe zum Scanner-Tab, scanne Symbole und übernehme Treffer in den Monitor.")
    else:
        # auto-refresh every 60 sec (clientside)
        count = st_autorefresh(interval=60*1000, key="monitor_refresh")
        st.write(f"Letzte Aktualisierung: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC (Auto refresh every 60s)")

        # Fetch current data for watchlist
        monitor_results = []
        watch = list(st.session_state.watchlist)  # copy
        progress = st.progress(0)
        for i, sym in enumerate(watch):
            df = fetch_intraday(sym, period_days=2, interval_try=["1m","5m"])
            if df is None or df.empty:
                progress.progress((i+1)/len(watch))
                st.sidebar.write(f"{sym}: keine Daten")
                continue

            close_ser, vol_ser = extract_close_volume(df, sym)
            if close_ser is None or vol_ser is None:
                progress.progress((i+1)/len(watch))
                st.sidebar.write(f"{sym}: keine Close/Volume")
                continue

            tmp = pd.DataFrame({"Close": close_ser, "Volume": vol_ser}).dropna()
            if tmp.empty:
                progress.progress((i+1)/len(watch))
                st.sidebar.write(f"{sym}: keine gültigen Werte")
                continue

            # compute metrics for current minute
            curr_price = float(tmp["Close"].iloc[-1])
            curr_vol = float(tmp["Volume"].iloc[-1])
            # for avg vol, prefer lookback bars (but ensure enough bars)
            look = min(len(tmp)-1, lookback)
            if look < 1:
                avg_vol = float(tmp["Volume"].iloc[:-1].mean()) if len(tmp) > 1 else curr_vol
            else:
                avg_vol = float(tmp["Volume"].iloc[-look-1:-1].mean()) if look>0 else curr_vol
            curr_rvol = curr_vol / avg_vol if avg_vol>0 else 0.0

            prev = st.session_state.monitor_data.get(sym, {"price": None, "rvol": None})
            prev_price = prev.get("price")
            prev_rvol = prev.get("rvol")

            # compute deltas (relative)
            delta_price_pct = None
            delta_rvol = None
            trend = "—"
            if prev_price is not None:
                try:
                    delta_price_pct = (curr_price - prev_price) / prev_price * 100.0
                    if delta_price_pct > 0:
                        trend = "↑"
                    elif delta_price_pct < 0:
                        trend = "↓"
                    else:
                        trend = "—"
                except Exception:
                    delta_price_pct = None
            else:
                delta_price_pct = 0.0
                trend = "—"

            if prev_rvol is not None:
                try:
                    delta_rvol = curr_rvol - prev_rvol
                except Exception:
                    delta_rvol = None
            else:
                delta_rvol = 0.0

            # update session_state snapshot for next comparison
            st.session_state.monitor_data[sym] = {
                "price": curr_price,
                "rvol": curr_rvol,
                "last_checked": datetime.utcnow().isoformat()
            }

            monitor_results.append({
                "Symbol": sym,
                "Price": round(curr_price, 4),
                "Δ Price %": round(delta_price_pct, 3) if delta_price_pct is not None else None,
                "Δ RVOL": round(delta_rvol, 3) if delta_rvol is not None else None,
                "RVOL": round(curr_rvol, 3),
                "CurrentVol": int(curr_vol),
                "AvgVol": int(avg_vol),
                "Trend": trend,
                "LastChecked": st.session_state.monitor_data[sym]["last_checked"]
            })

            progress.progress((i+1)/len(watch))

        # present monitor_results as dataframe with coloring
        if monitor_results:
            dfm = pd.DataFrame(monitor_results).set_index("Symbol")
            # style function for Δ Price %
            def style_delta_price(val):
                try:
                    v = float(val)
                except Exception:
                    return ""
                if v > 0.0:
                    return "background-color: #d4f7d4; color: #025f02"  # light green
                elif v < 0.0:
                    return "background-color: #ffd6d6; color: #7f0000"  # light red
                else:
                    return ""

            def style_delta_rvol(val):
                try:
                    v = float(val)
                except Exception:
                    return ""
                if v > 0.0:
                    return "background-color: #e6f7e6"
                elif v < 0.0:
                    return "background-color: #fff0f0"
                else:
                    return ""

            sty = dfm.style.format({
                "Price": "${:,.4f}",
                "Δ Price %": "{:+.3f}%",
                "Δ RVOL": "{:+.3f}",
                "RVOL": "{:.3f}",
                "CurrentVol": "{:,}",
                "AvgVol": "{:,}"
            }).applymap(style_delta_price, subset=["Δ Price %"]).applymap(style_delta_rvol, subset=["Δ RVOL"])

            st.subheader("Live Watchlist")
            st.write("Tabelle aktualisiert jede Minute (Auto-refresh). Grün = Anstieg, Rot = Rückgang.")
            st.dataframe(sty, use_container_width=True)

            # small controls: remove selected symbols
            st.write("Verwalten der Watchlist")
            remove = st.multiselect("Aus Watchlist entfernen (Mehrfachauswahl möglich):", options=list(dfm.index))
            if st.button("Entfernen"):
                for r in remove:
                    if r in st.session_state.watchlist:
                        st.session_state.watchlist.remove(r)
                    if r in st.session_state.monitor_data:
                        del st.session_state.monitor_data[r]
                st.experimental_rerun()
        else:
            st.info("Keine aktuellen Monitor-Daten. Stelle sicher, dass die Watchlist Items enthält und Daten verfügbar sind.")
