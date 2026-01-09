import streamlit as st
import pandas as pd
import plotly.express as px
import os

# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Executive Cash Flow Dashboard",
    layout="wide"
)

# ---------------- HELPERS ----------------
def find_excel_anywhere():
    for root, _, files in os.walk("."):
        for f in files:
            if f.lower().endswith(".xlsx"):
                return os.path.join(root, f)
    return None


def load_from_excel(path):
    xls = pd.ExcelFile(path)
    sheets = xls.sheet_names

    cash_df = pd.read_excel(xls, sheet_name=sheets[0])
    pay_df = pd.read_excel(xls, sheet_name=sheets[1]) if len(sheets) > 1 else pd.DataFrame()

    return prepare_cash_df(cash_df), pay_df


def load_from_csv(path):
    df = pd.read_csv(path)
    return prepare_cash_df(df), pd.DataFrame()


def prepare_cash_df(df):
    df.columns = [c.strip() for c in df.columns]

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Scenario"] = df["Scenario"].astype(str).str.strip()

    df["Amount"] = (
        df["Amount"]
        .astype(str)
        .str.replace("\u00a0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

    df = df.dropna(subset=["Date", "Scenario", "Amount"]).copy()
    df["AmountAbs"] = df["Amount"].abs()

    return df


# ---------------- DATA LOAD ----------------
excel_file = find_excel_anywhere()

if excel_file:
    cash_df, pay_df = load_from_excel(excel_file)
    source_name = excel_file
else:
    csv_file = "master_cashflow_data.csv"
    if not os.path.exists(csv_file):
        st.error("❌ Не найден ни Excel, ни master_cashflow_data.csv")
        st.stop()
    cash_df, pay_df = load_from_csv(csv_file)
    source_name = csv_file

if cash_df.empty:
    st.error("❌ Данные пустые — проверьте файл")
    st.stop()

# ---------------- UI ----------------
st.title("🛡️ EXECUTIVE CASH FLOW DASHBOARD")
st.caption(f"Источник данных: {source_name}")

tab1, tab2, tab3 = st.tabs([
    "📊 Executive Summary",
    "🚨 January Actions",
    "🧠 Scenarios"
])

# ---------------- TAB 1 ----------------
with tab1:
    st.subheader("Critical Liquidity Risk")

    def val(date, scenario):
        d = pd.to_datetime(date)
        return cash_df[
            (cash_df["Date"] == d) &
            (cash_df["Scenario"] == scenario)
        ]["AmountAbs"].sum()

    jan = val("2026-01-31", "No Partners")
    jun_np = val("2026-06-30", "No Partners")
    jun_wp = val("2026-06-30", "With Partners")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("January Need", f"{jan/1e9:.1f} Bn")
    c2.metric("June Peak (Base)", f"{jun_np/1e9:.1f} Bn")
    c3.metric("June Peak (Partners)", f"{jun_wp/1e9:.1f} Bn")
    c4.metric("Days to Peak", "150 days")

    st.divider()

    monthly = (
        cash_df
        .groupby(["Date", "Scenario"], as_index=False)["AmountAbs"]
        .sum()
    )
    monthly["AmountBn"] = monthly["AmountAbs"] / 1e9

    fig = px.line(
        monthly,
        x="Date",
        y="AmountBn",
        color="Scenario",
        markers=True,
        template="plotly_white",
        title="Cash Outflow Projection (Bn)"
    )

    x_peak = pd.to_datetime("2026-06-30")

    fig.add_shape(
        type="line",
        x0=x_peak,
        x1=x_peak,
        y0=0,
        y1=1,
        xref="x",
        yref="paper",
        line=dict(dash="dash")
    )

    fig.add_annotation(
        x=x_peak,
        y=1,
        xref="x",
        yref="paper",
        text="CRITICAL PEAK",
        showarrow=False,
        yanchor="bottom"
    )

    st.plotly_chart(fig, use_container_width=True)

# ---------------- TAB 2 ----------------
with tab2:
    st.subheader("January Priority Actions")

    c1, c2 = st.columns(2)
    c1.warning("Must pay immediately")
    c2.error(f"Total January Need: {jan/1e9:.1f} Bn UZS")

# ---------------- TAB 3 ----------------
with tab3:
    st.subheader("Scenario Risk Matrix")

    scenarios = pd.DataFrame({
        "Scenario": ["Do nothing", "Delay leasing", "Refinance", "Partner funding"],
        "January": ["❌ Gap", "✅ OK", "✅ OK", "⚠️ Risk"],
        "June": ["❌ Default", "⚠️ High load", "✅ Stable", "⚠️ Manageable"],
        "Risk Level": ["Critical", "High", "Low", "Medium"]
    })

    st.table(scenarios)












