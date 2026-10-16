from datetime import datetime
from pathlib import Path
import hashlib

import pandas as pd
import plotly.express as px
import streamlit as st

from recommendation_engine import add_recommendations, build_customer_features

st.set_page_config(page_title="CustomerIQ | Intelligent Retention", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
#MainMenu, footer {visibility:hidden;}
.block-container {max-width:1500px; padding-top:1.4rem; padding-bottom:3rem;}
.hero {padding:1.7rem 1.8rem; border:1px solid rgba(100,120,150,.20); border-radius:24px; background:linear-gradient(135deg, rgba(30,55,90,.07), rgba(30,160,150,.07)); margin-bottom:1rem;}
.hero h1 {font-size:2.5rem; margin:0; letter-spacing:-.03em;}
.hero p {margin:.4rem 0 0; opacity:.7; font-size:1rem;}
.card {padding:1rem 1.15rem; border:1px solid rgba(100,120,150,.18); border-radius:17px; min-height:105px; background:rgba(255,255,255,.025);}
.card .label {font-size:.72rem; text-transform:uppercase; letter-spacing:.1em; opacity:.6;}
.card .value {font-size:1.65rem; font-weight:750; margin-top:.25rem;}
.action-card {padding:1.2rem 1.35rem; border:1px solid rgba(100,120,150,.20); border-radius:20px; margin:.5rem 0;}
.muted {opacity:.68; font-size:.88rem;}
.pill {display:inline-block; padding:.28rem .65rem; border-radius:999px; border:1px solid rgba(100,120,150,.20); font-size:.78rem; margin-right:.35rem;}
.big-number {font-size:2.1rem; font-weight:800;}
</style>
""", unsafe_allow_html=True)

if "action_log" not in st.session_state:
    st.session_state.action_log = []
if "automation_enabled" not in st.session_state:
    st.session_state.automation_enabled = False
if "executed_ids" not in st.session_state:
    st.session_state.executed_ids = set()

st.markdown("""
<div class="hero">
<h1>🎯 CustomerIQ</h1>
<p>Intelligent customer retention • recommendation • action execution • outcome tracking</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Control Center")
    uploaded = st.file_uploader("Upload Online Retail Excel/CSV", type=["xlsx", "xls", "csv"])
    st.caption("Required: CustomerID, InvoiceNo, InvoiceDate, Quantity, UnitPrice")
    st.divider()
    st.subheader("⚡ Automation")
    st.session_state.automation_enabled = st.toggle("Enable auto-execution", value=st.session_state.automation_enabled)
    if st.session_state.automation_enabled:
        st.success("Automation mode ON")
        st.caption("Eligible HIGH/CRITICAL actions will be executed automatically for this demo session.")
    else:
        st.info("Approval mode ON")
        st.caption("Actions wait for a human click before execution.")
    st.divider()
    st.markdown("**Execution channels**")
    st.write("📧 Email campaigns")
    st.write("🎁 Personalized offers")
    st.write("📌 Follow-up tasks")
    st.caption("Demo-safe mode: actions are simulated and logged. No real emails are sent unless you later connect an email provider.")

@st.cache_data(show_spinner=False)
def load_uploaded(file):
    if file.name.lower().endswith(".csv"):
        return pd.read_csv(file)
    return pd.read_excel(file)

if uploaded is None:
    st.info("Upload your transaction dataset to activate CustomerIQ.")
    cols = st.columns(4)
    for col, title, desc in zip(cols, ["PREDICT", "DECIDE", "ACT", "LEARN"], [
        "Identify customers with elevated churn risk.",
        "Choose the most suitable retention action.",
        "Execute or approve the action directly from the website.",
        "Track what was executed and prepare for outcome-based optimization.",
    ]):
        with col:
            st.markdown(f'<div class="card"><div class="label">{title}</div><div class="value">→</div><div class="muted">{desc}</div></div>', unsafe_allow_html=True)
    st.markdown("### Closed-loop architecture")
    st.code("Transactions → Customer Profile → Risk → Recommendation → Action Center → Execution → Action Log → Outcome", language="text")
    st.stop()

try:
    raw = load_uploaded(uploaded)
    customers = add_recommendations(build_customer_features(raw))
except Exception as exc:
    st.error(f"Could not process the dataset: {exc}")
    st.stop()

# Stable ID lets action state survive Streamlit reruns for the same uploaded dataset.
dataset_signature = hashlib.md5(pd.util.hash_pandas_object(raw.head(1000), index=True).values.tobytes()).hexdigest()[:10]
customers["ActionID"] = customers["CustomerID"].astype(str).map(lambda x: f"{dataset_signature}-{x}")

# Automatically execute eligible actions when automation is enabled.

# Automatically log eligible actions when automation is enabled.
if st.session_state.automation_enabled:
    eligible = customers[
        customers["AutomationEligible"]
        & customers["ChurnRisk"].isin(["HIGH"])
    ]

    for _, row in eligible.iterrows():
        aid = row["ActionID"]

        if aid not in st.session_state.executed_ids:
            st.session_state.action_log.append({
                "ActionID": aid,
                "Timestamp": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "CustomerID": str(row["CustomerID"]),
                "Risk": row["ChurnRisk"],
                "Priority": row["Priority"],
                "Action": row["RecommendedAction"],
                "Channel": row["Channel"],
                "Status": "SIMULATED",
                "Mode": "Automation",
            })

            st.session_state.executed_ids.add(aid)


high = int(customers["ChurnRisk"].eq("HIGH").sum())
critical = int(customers["Priority"].eq("CRITICAL").sum())
executed = len(st.session_state.action_log)
revenue_at_risk = float(customers.loc[customers["ChurnRisk"].eq("HIGH"), "TotalSpend"].sum())
pending = max(0, int(customers["AutomationEligible"].sum()) - executed)

kpis = [("Customers", f"{len(customers):,}"), ("High risk", f"{high:,}"), ("Critical", f"{critical:,}"), ("Spend at risk", f"£{revenue_at_risk:,.0f}"), ("Actions executed", f"{executed:,}")]
cols = st.columns(len(kpis))
for col, (label, value) in zip(cols, kpis):
    with col:
        st.markdown(f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>', unsafe_allow_html=True)

st.divider()
overview, customer360, queue, action_center, history, analytics = st.tabs([
    "📊 Overview", "👤 Customer 360", "🎯 Recommendations", "⚡ Action Center", "📜 Action History", "📈 Analytics"
])

with overview:
    left, right = st.columns(2)
    with left:
        rc = customers["ChurnRisk"].value_counts().reindex(["LOW", "MEDIUM", "HIGH"], fill_value=0).reset_index()
        rc.columns = ["Risk", "Customers"]
        fig = px.bar(rc, x="Risk", y="Customers", title="Customer risk distribution", text="Customers")
        fig.update_layout(height=350, margin=dict(l=10,r=10,t=55,b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        ac = customers["RecommendedAction"].value_counts().reset_index()
        ac.columns = ["Action", "Customers"]
        fig = px.bar(ac, x="Customers", y="Action", orientation="h", title="Recommended intervention mix")
        fig.update_layout(height=350, margin=dict(l=10,r=10,t=55,b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("🚨 Highest-priority customers")
    top = customers.sort_values(["RecommendationScore", "TotalSpend"], ascending=False).head(12)
    st.dataframe(top[["CustomerID","Segment","ChurnRisk","RecommendationScore","TotalSpend","Recency","RecommendedAction","Priority"]], use_container_width=True, hide_index=True)

with customer360:
    ids = customers["CustomerID"].astype(str).tolist()
    selected = st.selectbox("Search / select customer", ids, key="customer_selector")
    row = customers[customers["CustomerID"].astype(str).eq(selected)].iloc[0]
    st.subheader(f"Customer {selected}")
    cols = st.columns(6)
    metrics = [("Segment", row["Segment"]), ("Risk", row["ChurnRisk"]), ("Risk score", f"{row['ChurnRiskScore']*100:.0f}%"), ("Spend", f"£{row['TotalSpend']:,.0f}"), ("Purchases", f"{int(row['PurchaseFrequency'])}"), ("Recency", f"{int(row['Recency'])} days")]
    for col, (label, value) in zip(cols, metrics):
        with col: st.metric(label, value)
    st.markdown(f"### 🎯 {row['RecommendedAction']}")
    st.write(row["RecommendationReason"])
    st.caption(f"Goal: {row['ExpectedGoal']} • Channel: {row['Channel']} • Automation eligible: {'Yes' if row['AutomationEligible'] else 'No'}")
    if row["AutomationEligible"]:
        st.info(f"Suggested intervention: {int(row['OfferPercent'])}% personalized offer via {row['Channel']}" if row['OfferPercent'] else f"Suggested intervention via {row['Channel']}")

with queue:
    st.subheader("🎯 Recommendation queue")
    f1, f2, f3 = st.columns(3)
    with f1: risk_filter = st.multiselect("Risk", ["HIGH","MEDIUM","LOW"], default=["HIGH","MEDIUM","LOW"])
    with f2: priority_filter = st.multiselect("Priority", ["CRITICAL","HIGH","MEDIUM","LOW"], default=["CRITICAL","HIGH","MEDIUM","LOW"])
    with f3: search = st.text_input("Customer ID contains")
    view = customers[customers["ChurnRisk"].isin(risk_filter) & customers["Priority"].isin(priority_filter)].copy()
    if search: view = view[view["CustomerID"].astype(str).str.contains(search, case=False, na=False)]
    view = view.sort_values("RecommendationScore", ascending=False)
    st.caption(f"Showing {len(view):,} recommendations")
    st.dataframe(view[["CustomerID","Segment","ChurnRisk","RecommendationScore","TotalSpend","Recency","RecommendedAction","Priority","AutomationEligible"]], use_container_width=True, hide_index=True)

with action_center:
    st.subheader("⚡ Action Center")
    st.write("This is the operational layer: recommendations can be approved and executed instead of remaining static dashboard text.")
    eligible_view = customers[(customers["AutomationEligible"]) & (customers["ChurnRisk"].isin(["HIGH", "MEDIUM"]))].sort_values("RecommendationScore", ascending=False).copy()
    if eligible_view.empty:
        st.success("No executable actions are currently waiting.")
    for _, row in eligible_view.head(30).iterrows():
        aid = row["ActionID"]
        already = aid in st.session_state.executed_ids
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.2, 2.5, 1.4])
            with c1:
                st.markdown(f"**Customer {row['CustomerID']}**")
                st.caption(f"{row['Priority']} • {row['ChurnRisk']} risk")
            with c2:
                st.markdown(f"**{row['RecommendedAction']}**")
                st.caption(row["RecommendationReason"])
            with c3:
                if already:
                    st.success("✓ Executed")
                elif st.button("⚡ Execute action", key=f"execute_{aid}"):
                    st.session_state.action_log.append({
                        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "CustomerID": str(row["CustomerID"]), "Risk": row["ChurnRisk"], "Priority": row["Priority"],
                        "Action": row["RecommendedAction"], "Channel": row["Channel"], "Status": "EXECUTED", "Mode": "Manual approval",
                    })
                    st.session_state.executed_ids.add(aid)
                    st.rerun()
                st.caption(f"Channel: {row['Channel']}")

with history:
    st.subheader("📜 Action history & audit trail")

    if st.session_state.action_log:
        log_df = pd.DataFrame(st.session_state.action_log)

        # Add missing columns so older records remain compatible.
        expected_columns = [
            "ActionID", "Timestamp", "CustomerID", "Risk",
            "Priority", "Action", "Channel", "Status", "Mode"
        ]

        for col in expected_columns:
            if col not in log_df.columns:
                log_df[col] = ""

        # Make the status clear: logged does not mean delivered.
        log_df["Status"] = log_df["Status"].replace({
            "AUTO-EXECUTED": "SIMULATED",
            "EXECUTED": "SIMULATED",
        })

        st.caption(
            "SIMULATED means the action was recorded in the demo. "
            "It does not confirm that an email was sent or an offer was delivered."
        )

        st.dataframe(
            log_df.iloc[::-1],
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Download action audit CSV",
            log_df.to_csv(index=False),
            "customeriq_action_history.csv",
            "text/csv"
        )
    else:
        st.info(
            "No actions have been logged yet. "
            "Enable automation or select an action in Action Center."
        )

with analytics:
    st.subheader("📈 Retention intelligence")
    c1, c2 = st.columns(2)
    with c1:
        seg = customers["Segment"].value_counts().reset_index(); seg.columns = ["Segment","Customers"]
        fig = px.pie(seg, names="Segment", values="Customers", hole=.55, title="Customer segments")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.scatter(customers, x="Recency", y="TotalSpend", size="PurchaseFrequency", color="ChurnRisk", hover_data=["CustomerID","Segment","RecommendedAction"], title="Value vs. inactivity")
        st.plotly_chart(fig, use_container_width=True)
    if st.session_state.action_log:
        log_df = pd.DataFrame(st.session_state.action_log)
        counts = log_df["Status"].value_counts().reset_index(); counts.columns = ["Status","Actions"]
        fig = px.bar(counts, x="Status", y="Actions", title="Execution activity")
        st.plotly_chart(fig, use_container_width=True)
    st.download_button("Download full recommendation dataset", customers.drop(columns=["ActionID"]).to_csv(index=False), "customeriq_recommendations.csv", "text/csv")
