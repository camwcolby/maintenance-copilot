import streamlit as st
import pandas as pd

from data_service import load_assets, load_asset, load_work_orders, load_recent_scada, load_manual
from retrieval import search_text, search_work_orders
from agent import summarize_scada, build_answer

st.set_page_config(page_title="Maintenance Copilot", layout="wide")

st.title("Maintenance Copilot")
st.caption("Prototype: asset-aware troubleshooting using operating data, manuals, and maintenance history.")

assets = load_assets()
asset_labels = {f"{a['asset_name']} | {a['facility']}": a["asset_id"] for a in assets}

selected_label = st.sidebar.selectbox("Asset", list(asset_labels.keys()))
asset_id = asset_labels[selected_label]
asset = load_asset(asset_id)

st.sidebar.markdown("### Asset context")
st.sidebar.write(f"**ID:** {asset['asset_id']}")
st.sidebar.write(f"**Process:** {asset['process']}")
st.sidebar.write(f"**Type:** {asset['asset_type']}")
st.sidebar.write(f"**Model:** {asset['manufacturer']} {asset['model']}")
st.sidebar.write(f"**Criticality:** {asset['criticality']}")

scada = load_recent_scada(asset_id)
work_orders = load_work_orders(asset_id)
manual = load_manual(asset)

left, right = st.columns([1.2, 1])

with left:
    st.subheader("Ask Maintenance Copilot")
    default_q = "The pump is rattling and motor amps keep increasing. What should I check?"
    question = st.text_area("Question", value=default_q, height=100)

    if st.button("Investigate", type="primary"):
        manual_hits = search_text(question, manual, top_k=3)
        wo_hits = search_work_orders(question, work_orders, top_k=3)
        summary = summarize_scada(asset, scada)
        answer = build_answer(question, asset, summary, manual_hits, wo_hits)

        st.markdown(answer)

        with st.expander("Retrieved manual evidence"):
            for hit in manual_hits:
                st.write(hit["text"])
                st.caption(f"retrieval score: {hit['score']:.3f}")

        with st.expander("Retrieved work orders"):
            if wo_hits:
                st.dataframe(pd.DataFrame(wo_hits), use_container_width=True)
            else:
                st.info("No similar work orders found.")

with right:
    st.subheader("Recent operating condition")
    if not scada.empty:
        latest = scada.iloc[-1]
        m1, m2, m3 = st.columns(3)
        m1.metric("Motor amps", f"{latest['motor_amps']:.1f} A")
        m2.metric("Bearing temp", f"{latest['bearing_temp_f']:.0f} F")
        m3.metric("Vibration", f"{latest['vibration_ips']:.2f} in/s")

        st.line_chart(
            scada.set_index("timestamp")[["motor_amps", "bearing_temp_f"]],
            use_container_width=True
        )

        st.line_chart(
            scada.set_index("timestamp")[["vibration_ips"]],
            use_container_width=True
        )
    else:
        st.info("No SCADA demo data exists for this asset.")

    st.subheader("Maintenance history")
    if not work_orders.empty:
        st.dataframe(
            work_orders[["work_order_id", "date", "problem", "cause", "corrective_action"]],
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No work-order history found.")
