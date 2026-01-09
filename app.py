import os
import re
import streamlit as st
import pandas as pd
import plotly.express as px

# =======================
# CONFIG
# =======================
st.set_page_config(page_title="Executive Cash Flow Dashboard", layout="wide")

st.markdown(
    """
    <style>
    .metric-box {
        background-color: #f5f6fa;
        padding: 16px;
        border-radius: 12px;
        border-left: 6px solid #e74c3c;
    }
    .small-muted { color:#6b7280; font-size: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# =======================
# HELPERS
# =======================
def _to_number(x):
    """Robust money parser: handles spaces, commas, strings like '1 234,56'."""
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s == "" or s.lower() == "nan":
        return None
    s = s.replace("\u00a0", " ").replace(" ", "")
    # If decimal comma exists and dot not, convert comma->dot
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    # Remove thousands separators if any leftover
    s = re.sub(r"[^\d\.\-]", "", s)
    try:
        return float(s)
    except:
        return None

def _fmt_bn_uzs(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{abs(v)/1e9:.1f} Bn"

def _pick_excel_file():
    """Pick the best xlsx from repo root."""
    xlsx = [f for f in os.listdir(".") if f.lower().endswith(".xlsx")]
    if not xlsx:
        return None
    # Prefer file that contains "потребность" or "upm"
    for key in ["потребность", "upm", "юпм"]:
        for f in xlsx:
            if key.lower() in f.lower():
                return f
    return xlsx[0]

# =======================
# LOAD FROM EXCEL (PRO)
# =======================
@st.cache_data
def load_from_excel(excel_path: str):
    xl = pd.ExcelFile(excel_path)

    # Expected sheets (based on your file)
    SHEET_WITH = "Версия с фин займ партнеров"
    SHEET_NO = "Версия без фин займ партнеров"
    SHEET_PAY = "Сводная"

    # --- Cashflow sheets are structured with header row at index 2
    def parse_cashflow(sheet_name: str, scenario_label: str):
        raw = xl.parse(sheet_name, header=2)

        # First row after header usually contains the month dates in columns
        # We detect date columns by looking at row 0 values
        date_cols = []
        for c in raw.columns:
            v = raw.loc[0, c]
            if isinstance(v, (pd.Timestamp,)):
                date_cols.append(c)

        if not date_cols:
            # Fallback: try columns that look like timestamps in header itself
            for c in raw.columns:
                if isinstance(c, (pd.Timestamp,)):
                    date_cols.append(c)

        # Build a tidy table:
        # We take the first meaningful label column (usually "Unnamed: 1") as Category
        label_col = None
        for c in raw.columns[:3]:
            if "Unnamed" in str(c) or str(c).strip() != "":
                label_col = c
                break
        if label_col is None:
            label_col = raw.columns[0]

        df = raw.copy()

        # Remove the "date header row" (row 0) and any empty rows
        df = df.iloc[1:].copy()

        # Keep only label + date columns
        keep_cols = [label_col] + date_cols
        keep_cols = [c for c in keep_cols if c in df.columns]
        df = df[keep_cols].copy()

        df.rename(columns={label_col: "Category"}, inplace=True)

        # Melt to long format
        long_df = df.melt(id_vars=["Category"], var_name="Date", value_name="Amount")

        # Clean
        long_df["Category"] = long_df["Category"].astype(str).str.strip()
        long_df["Date"] = pd.to_datetime(long_df["Date"], errors="coerce").dt.date
        long_df["Amount"] = long_df["Amount"].apply(_to_number)

        long_df = long_df.dropna(subset=["Date", "Amount"])
        long_df["Scenario"] = scenario_label

        # In your dashboard you use cash outflow as positive (abs)
        # But keep original sign too, for flexibility
        long_df["AmountSigned"] = long_df["Amount"]
        long_df["AmountAbs"] = long_df["Amount"].abs()

        return long_df

    # Parse cashflow for two scenarios
    cash_with = parse_cashflow(SHEET_WITH, "With Partners") if SHEET_WITH in xl.sheet_names else pd.DataFrame()
    cash_no = parse_cashflow(SHEET_NO, "No Partners") if SHEET_NO in xl.sheet_names else pd.DataFrame()

    cash = pd.concat([cash_with, cash_no], ignore_index=True)
    cash = cash.dropna(subset=["Date", "Scenario"]).copy()

    # --- Payables ("Сводная")
    pay = pd.DataFrame()
    if SHEET_PAY in xl.sheet_names:
        pay_raw = xl.parse(SHEET_PAY)
        # Keep first 6 columns: Расходы, Сумма, Оплаченная сумма, Уровень срочности, Крайний срок, К оплате
        cols = list(pay_raw.columns)
        if len(cols) >= 6:
            pay = pay_raw.iloc[:, :6].copy()
            pay.columns = ["Expense", "Amount", "Paid", "Urgency", "DueDate", "ToPay"]

            pay["Amount"] = pay["Amount"].apply(_to_number)
            pay["Paid"] = pay["Paid"].apply(_to_number)
            pay["ToPay"] = pay["ToPay"].apply(_to_number)
            pay["Urgency"] = pay["Urgency"].astype(str).str.strip()

            # Dates
            pay["DueDate"] = pd.to_datetime(pay["DueDate"], errors="coerce").dt.date

            # Remove empty lines
            pay = pay.dropna(subset=["Expense", "ToPay"], how="any")
            pay["Expense"] = pay["Expense"].astype(str).str.strip()

    return cash, pay

# =======================
# MAIN LOAD
# =======================
excel_file = _pick_excel_file()

if excel_file is None:
    st.error("❌ Не найден Excel (*.xlsx) в репозитории. Загрузите файл Excel в корень репо и сделайте Commit.")
    st.stop()

cash_df, pay_df = load_from_excel(excel_file)

if cash_df.empty:
    st.error("❌ Не удалось собрать Cashflow из Excel. Проверьте вкладки и структуру файла.")
    st.stop()

# =======================
# PREPARE AGGREGATES
# =======================
monthly = (
    cash_df.groupby(["Date", "Scenario"], as_index=False)
    .agg(Amount=("AmountAbs", "sum"))
)
monthly["Date"] = pd.to_datetime(monthly["Date"])  # for Plotly axis

# KPI: find peaks (max abs outflow) per scenario
def scenario_peak(scn):
    d = monthly[monthly["Scenario"] == scn].copy()
    if d.empty:
        return None, None
    row = d.sort_values("Amount", ascending=False).iloc[0]
    return row["Date"], row["Amount"]

peak_date_np, peak_np = scenario_peak("No Partners")
peak_date_wp, peak_wp = scenario_peak("With Partners")

# January metric (closest to Jan 2026 month end)
def value_on(date_str, scn):
    dt = pd.to_datetime(date_str)
    m = monthly[(monthly["Scenario"] == scn) & (monthly["Date"] == dt)]
    if m.empty:
        return 0.0
    return float(m["Amount"].sum())

jan_np = value_on("2026-01-31", "No Partners")
jan_wp = value_on("2026-01-31", "With Partners")

# =======================
# UI TABS
# =======================
tab1, tab2, tab3 = st.tabs(["🛡️ Executive Summary", "🚨 К оплате (январь)", "🧠 Сценарии"])

# =======================
# TAB 1: SUMMARY
# =======================
with tab1:
    st.title("🛡️ EXECUTIVE CASH FLOW SUMMARY")
    st.markdown("### 🔴 Critical liquidity risk")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("January Need (No Partners)", _fmt_bn_uzs(jan_np * 1e9 if jan_np < 1e6 else jan_np))
    c2.metric("Peak (No Partners)", f"{peak_np:.1f} Bn" if peak_np is not None else "—")
    c3.metric("Peak (With Partners)", f"{peak_wp:.1f} Bn" if peak_wp is not None else "—")

    # Days to peak (based on earliest date in dataset)
    start_date = monthly["Date"].min()
    end_date = peak_date_np if peak_date_np is not None else monthly["Date"].max()
    days_to_peak = int((end_date - start_date).days) if pd.notna(start_date) and pd.notna(end_date) else 0
    c4.metric("Days to Peak", f"{days_to_peak} days")

    st.divider()
    st.subheader("📉 Cash Outflow Projection (Bn UZS)")

    fig = px.line(
        monthly,
        x="Date",
        y="Amount",
        color="Scenario",
        markers=True,
        template="plotly_white",
    )

    # Add critical line (use add_shape to avoid Plotly add_vline timestamp bug)
    if peak_date_np is not None:
        x_peak = pd.to_datetime(peak_date_np)
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

    st.caption(f"Источник данных: {excel_file}")

# =======================
# TAB 2: PAYABLES
# =======================
with tab2:
    st.title("🚨 К оплате (оперативный контроль)")
    if pay_df.empty:
        st.warning("В Excel не найдена/не распознана вкладка 'Сводная'.")
    else:
        # Filters
        urgencies = sorted([u for u in pay_df["Urgency"].dropna().unique().tolist() if u.strip() != ""])
        colf1, colf2, colf3 = st.columns([1, 1, 1])

        urg_sel = colf1.multiselect("Фильтр: срочность", urgencies, default=urgencies[:])
        date_from = colf2.date_input("Срок с", value=pay_df["DueDate"].min() if pay_df["DueDate"].notna().any() else None)
        date_to = colf3.date_input("Срок по", value=pay_df["DueDate"].max() if pay_df["DueDate"].notna().any() else None)

        view = pay_df.copy()
        if urg_sel:
            view = view[view["Urgency"].isin(urg_sel)]

        if date_from:
            view = view[view["DueDate"].isna() | (view["DueDate"] >= date_from)]
        if date_to:
            view = view[view["DueDate"].isna() | (view["DueDate"] <= date_to)]

        total_to_pay = view["ToPay"].fillna(0).sum()
        st.metric("Итого к оплате (выбранные строки)", _fmt_bn_uzs(total_to_pay))

        st.dataframe(
            view.sort_values(["DueDate"], na_position="last"),
            use_container_width=True,
            hide_index=True
        )

# =======================
# TAB 3: SCENARIOS (PRO)
# =======================
with tab3:
    st.title("🧠 Decision Scenarios (PRO)")
    st.markdown("Сравнение сценариев по пиковым нагрузкам и датам пиков.")

    rows = []
    for scn in ["No Partners", "With Partners"]:
        dpk, apk = scenario_peak(scn)
        rows.append({
            "Scenario": scn,
            "Peak Date": dpk.date() if hasattr(dpk, "date") else dpk,
            "Peak Outflow (Bn UZS)": round(apk, 2) if apk is not None else None,
        })

    scn_table = pd.DataFrame(rows)
    st.table(scn_table)

    st.divider()
    st.subheader("📌 Рекомендованная управленческая логика (шаблон)")

    st.markdown(
        """
- **Если пик > 10 Bn** и срок до пика < 120 дней → нужен план: реструктуризация / партнёрские деньги / перенос платежей.
- **Если вкладка “Сводная” показывает CRITICAL платежи** в ближайшие 7–14 дней → приоритет: налоги/зарплаты/электро/ключевые подрядчики.
- Разделяйте: *обязательные платежи* vs *можно двигать* (лизинг/нештрафные поставщики).
        """
    )











