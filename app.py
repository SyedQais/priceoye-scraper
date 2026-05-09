import io
import queue
import subprocess
import sys
import threading
import time

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="PriceOye Installment Scraper",
    page_icon="🏦",
    layout="wide",
)

# ─────────────────────────────────────────────
# INSTALL PLAYWRIGHT BROWSERS (once per deploy)
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner="Installing browser (first run only)...")
def install_browser():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
        capture_output=True,
    )
    return True


install_browser()

# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] {
            font-family: 'Syne', sans-serif;
        }

        .main-title {
            font-size: 2.6rem;
            font-weight: 800;
            letter-spacing: -1px;
            line-height: 1.1;
            margin-bottom: 0.2rem;
        }

        .sub-title {
            font-size: 1rem;
            opacity: 0.55;
            margin-bottom: 2rem;
            font-weight: 400;
        }

        .log-box {
            font-family: 'DM Mono', monospace;
            font-size: 0.78rem;
            background: #0e1117;
            color: #a8ff78;
            border-radius: 8px;
            padding: 1rem 1.2rem;
            max-height: 260px;
            overflow-y: auto;
            line-height: 1.7;
            white-space: pre-wrap;
            border: 1px solid #1e2a1e;
        }

        .metric-card {
            background: #1a1a2e;
            border-radius: 10px;
            padding: 1rem 1.4rem;
            text-align: center;
            border: 1px solid #2a2a4a;
        }

        .metric-num {
            font-size: 2rem;
            font-weight: 800;
            color: #a8ff78;
        }

        .metric-label {
            font-size: 0.75rem;
            opacity: 0.5;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        div[data-testid="stDataFrame"] {
            border-radius: 10px;
            overflow: hidden;
        }

        .stButton > button {
            font-family: 'Syne', sans-serif;
            font-weight: 700;
            letter-spacing: 0.5px;
            border-radius: 8px;
            padding: 0.6rem 2rem;
        }

        .stDownloadButton > button {
            font-family: 'Syne', sans-serif;
            font-weight: 700;
            background: #a8ff78;
            color: #0e1117;
            border: none;
            border-radius: 8px;
            padding: 0.6rem 2rem;
        }

        .stDownloadButton > button:hover {
            background: #8ade60;
            color: #0e1117;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown('<div class="main-title">🏦 PriceOye<br>Installment Scraper</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Paste any PriceOye product URL to extract bank installment plans in seconds.</div>', unsafe_allow_html=True)

st.divider()

# ─────────────────────────────────────────────
# INPUT
# ─────────────────────────────────────────────
col_input, col_btn = st.columns([5, 1], vertical_alignment="bottom")

with col_input:
    url = st.text_input(
        "Product URL",
        placeholder="https://priceoye.pk/mobiles/samsung/samsung-galaxy-s25",
        label_visibility="collapsed",
    )

with col_btn:
    run_btn = st.button("Scrape", type="primary", use_container_width=True)

# ─────────────────────────────────────────────
# SCRAPE LOGIC
# ─────────────────────────────────────────────
if run_btn:
    if not url.strip():
        st.warning("Please enter a product URL first.")
        st.stop()

    if "priceoye.pk" not in url:
        st.warning("This tool only works with priceoye.pk URLs.")
        st.stop()

    from scraper_core import run_scrape

    log_queue = queue.Queue()
    result_holder = {}

    def worker():
        def log_fn(msg):
            log_queue.put(msg)

        try:
            df = run_scrape(url.strip(), log=log_fn)
            result_holder["df"] = df
        except Exception as e:
            log_fn(f"❌ Fatal error: {e}")
            result_holder["df"] = None
        finally:
            log_queue.put("__DONE__")

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    # Live log display
    st.markdown("#### Live Log")
    log_placeholder = st.empty()
    log_lines = []

    while True:
        try:
            msg = log_queue.get(timeout=0.2)
            if msg == "__DONE__":
                break
            log_lines.append(msg)
            log_placeholder.markdown(
                f'<div class="log-box">{"<br>".join(log_lines)}</div>',
                unsafe_allow_html=True,
            )
        except queue.Empty:
            pass

    thread.join()

    df: pd.DataFrame | None = result_holder.get("df")

    # ─────────────────────────────────────────
    # RESULTS
    # ─────────────────────────────────────────
    if df is not None and not df.empty:
        st.divider()
        st.markdown("#### Results")

        # Metrics row
        tenure_cols = [c for c in df.columns if c != "Bank"]
        m1, m2, m3 = st.columns(3)

        with m1:
            st.markdown(
                f'<div class="metric-card"><div class="metric-num">{len(df)}</div>'
                f'<div class="metric-label">Banks</div></div>',
                unsafe_allow_html=True,
            )
        with m2:
            st.markdown(
                f'<div class="metric-card"><div class="metric-num">{len(tenure_cols)}</div>'
                f'<div class="metric-label">Tenures</div></div>',
                unsafe_allow_html=True,
            )
        with m3:
            total_plans = df[tenure_cols].notna().sum().sum()
            st.markdown(
                f'<div class="metric-card"><div class="metric-num">{total_plans}</div>'
                f'<div class="metric-label">Total Plans</div></div>',
                unsafe_allow_html=True,
            )

        st.write("")

        # Table
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Download
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)

        product_slug = url.rstrip("/").split("/")[-1]
        filename = f"{product_slug}_installments.xlsx"

        st.download_button(
            label="⬇ Download Excel",
            data=buffer,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=False,
        )

    else:
        st.error("No installment data could be extracted from that URL. Make sure the product page has an 'Installment Plans' section.")

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.divider()
st.markdown(
    '<p style="opacity:0.3; font-size:0.75rem; text-align:center;">Works with priceoye.pk product pages · Data scraped live on each request</p>',
    unsafe_allow_html=True,
)