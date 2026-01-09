import streamlit as st
import pandas as pd
import plotly.express as px
import os

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

# ---------------- HELPERS ----------------
def _read_csv_safely(file_name: str) -> pd.DataFrame:
    """
    1) Сначала пробуем Excel-CSV с разделителем ';'
    2) Если не вышло — пробуем ',' (на всякий случай)
    """
    last_err = None

    for sep in [";", ","]:
        try:
            df = pd.read_csv(
                file_name,
                sep=sep,
                encoding="utf-8-sig",
                engine="python",
                dtype=str,
                keep_default_na=False
            )
            # Если файл случайно прочитался "в одну колонку" — это не наш sep
            if df.shape[1] < 3:
                raise ValueError(f"CSV parsed with sep='{sep}' but has too few columns: {df.shape[1]}")
            return df
        except Exception as e:
            last_err = e

    raise last_err


def _normalize_amount(series: pd.Series) -> pd.Series:
    """
    Приводим суммы типа:
    '2 908 937 442,38' -> 2908937442.38
    '3500000000' -> 3500000000
    """
    s = series.astype(str).str.strip()

    # убираем пробелы (разделители тысяч)
    s = s.str.replace(" ", "", regex=False)

    # превращаем десятичную запятую в точку
    s = s.str.replace(",", ".", regex=False)

    return pd.to_numeric(s, errors="coerce")


# ---------------- DATA LOAD ----------------
@st.cache_data
def load_data():
    file_name = "master_cashflow_data.csv"

    if not os.path.exists(file_name):
        st.error(f"❌ Файл {file_name} не найден в репозитории/директории приложения.")
        st.stop()

    try:
        df = _read_csv_safely(file_name)

        # чистим названия колонок
        df.columns = [c.strip() for c in df.columns]

        # проверяем обязательные колонки
        required = {"Item", "Date", "Scenario", "Amount"}
        missing = required - set(df.columns)
        if missing:
            st.error(f"❌ В CSV не хватает колонок: {', '.join(sorted(missing))}")
            st.stop()

        # приведение типов
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        df["Scenario"] = df["Scenario"].astype(str).str.strip()
        df["Amount"] = _normalize_amount(df["Amount"])

        # удаляем битые строки
        df = df.dropna(subset=["Date", "Scenario", "Amount"])

        return df

    except Exception as e:
        st.error("❌ Ошибка при чтении CSV (скорее всего разделитель/формат строки).")
        st.exception(e)
        st.stop()


df = load_data()

# ---------------- UI: TABS ----------------
tab1, tab2, tab3 = st.tabs([
    "🛡️ Executive Summary",
    "🚨 January Actions",
    "🧠 Scenarios"
])

# ---------------- TAB 1 ----------------
tab1, tab2, tab3 = st.tabs([
    "🛡 Executive Summary",
    "🚨 January Actions",
    "🧠 Scenarios"
])

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

    monthly = (
        df.groupby(["Date", "Scenario"], as_index=False)["Amount"]
        .sum()
    )

    monthly["Amount"] = monthly["Amount"].abs() / 1e9
    monthly["Date"] = pd.to_datetime(monthly["Date"])

    fig = px.line(
        monthly,
        x="Date",
        y="Amount",
        color="Scenario",
        markers=True,
        template="plotly_white"
    )

x_peak = pd.to_datetime("2026-06-30")

fig.add_shape(
    type="line",
    x0=x_peak, x1=x_peak,
    y0=0, y1=1,
    xref="x", yref="paper",
    line=dict(dash="dash")
)

fig.add_annotation(
    x=x_peak,
    y=1,
    xref="x", yref="paper",
    text="CRITICAL PEAK",
    showarrow=False,
    yanchor="bottom"
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





