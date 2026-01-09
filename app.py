import streamlit as st
import pandas as pd
import plotly.express as px

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="Executive Cash Flow Dashboard",
    layout="wide"
)

st.markdown("""
<style>
.metric-box {
    background-color: #f5f6fa;
    padding: 20px;
    border-radius: 10px;
    border-left: 6px solid #e74c3c;
}
</style>
""", unsafe_allow_html=True)

import os

# ---------------- DATA LOAD ----------------
@st.cache_data
def load_data():
    file_name = "master_cashflow_data.csv"

    st.write("📂 Файлы в текущей директории:")
    st.write(os.listdir("."))

    if not os.path.exists(file_name):
        st.error(f"❌ Файл {file_name} не найден")
        st.stop()

    try:
        df = pd.read_csv(file_name)

        df.columns = [c.strip() for c in df.columns]

        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        df["Scenario"] = df["Scenario"].astype(str).str.strip()

        df["Amount"] = (
            df["Amount"]
            .astype(str)
            .str.replace(" ", "", regex=False)
            .str.replace(",", "", regex=False)
        )
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

        df = df.dropna(subset=["Date", "Scenario", "Amount"])
        return df

    except Exception as e:
        st.error("❌ Ошибка при чтении CSV")
        st.exception(e)
        st.stop()

df = load_data()

# ---------------- TAB 1 ----------------
with tab1:
    st.title("🛡️ EXECUTIVE CASH FLOW SUMMARY")
    st.markdown("### 🔴 Critical liquidity risk by June")

    def val(date, scenario):
        d = pd.to_datetime(date).date()
        return df[(df["Date"] == d) & (df["Scenario"] == scenario)]["Amount"].sum()

    jan = val("2026-01-31", "No Partners")
    jun_np = val("2026-06-30", "No Partners")
    jun_wp = val("2026-06-30", "With Partners")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("January Need", f"{abs(jan)/1e9:.1f} Bn")
    c2.metric("June Peak (Base)", f"{abs(jun_np)/1e9:.1f} Bn")
    c3.metric("June Peak (Partners)", f"{abs(jun_wp)/1e9:.1f} Bn")
    c4.metric("Days to Peak", "150 days")

    st.divider()

    st.subheader("📉 Cash Outflow Projection")

    monthly = df.groupby(["Date", "Scenario"], as_index=False)["Amount"].sum()
    monthly["Amount"] = monthly["Amount"].abs() / 1e9

    fig = px.line(
        monthly,
        x="Date",
        y="Amount",
        color="Scenario",
        markers=True,
        template="plotly_white"
    )

    fig.add_vline(
        x=pd.to_datetime("2026-06-30").date(),
        line_dash="dash",
        annotation_text="CRITICAL PEAK"
    )

    st.plotly_chart(fig, use_container_width=True)

# ---------------- TAB 2 ----------------
with tab2:
    st.title("🚨 January: Immediate Actions")

    c1, c2 = st.columns(2)
    c1.warning("Must pay now: 7.3 Bn UZS")
    c2.error("Total January: 22.6 Bn UZS")

    st.subheader("Payment Priority")

    table = pd.DataFrame({
        "Category": ["K2 System", "VAT", "Leasing", "Electricity", "Salaries", "Fuel"],
        "Amount (Bn)": [2.9, 3.2, 5.0, 0.56, 0.28, 1.0],
        "Urgency": ["CRITICAL", "CRITICAL", "MONTH END", "MONTH END", "CRITICAL", "MONTH END"],
        "Action": ["Pay now", "Pay now", "Negotiate", "Pay", "Pay now", "Delay"]
    })

    st.dataframe(table, use_container_width=True)

# ---------------- TAB 3 ----------------
with tab3:
    st.title("🧠 Decision Scenarios")

    scenarios = pd.DataFrame({
        "Scenario": ["Do nothing", "Delay leasing", "Refinance", "Extend partner loans"],
        "January": ["❌ Gap", "✅ OK", "✅ OK", "❌ Gap"],
        "June": ["❌ Default", "⚠️ High load", "✅ Stable", "⚠️ Manageable"],
        "Risk": ["Critical", "High", "Low", "Medium"]
    })

    st.table(scenarios)

