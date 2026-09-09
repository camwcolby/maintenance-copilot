import pandas as pd
import streamlit as st

from agent import run_investigation
from data_service import load_assets, load_asset, load_recent_scada, load_work_orders

st.set_page_config(page_title="Maintenance Copilot", layout="wide")

st.title("Maintenance Copilot")
st.caption(
    "Asset-aware troubleshooting using operating data, equipment guidance, and maintenance history."
)

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

left, right = st.columns([1.2, 1])

with left:
    st.subheader("Ask Maintenance Copilot")
    default_q = "The pump is rattling and motor amps keep increasing. What should I check?"
    question = st.text_area("Question", value=default_q, height=100)

    if st.button("Investigate", type="primary"):
        with st.spinner("Investigating asset condition..."):
            result = run_investigation(asset_id, question)

        st.markdown("### Investigation path")
        for tool_result in result["trace"]:
            if tool_result.status == "complete":
                st.success(f"✓ {tool_result.label}")
            elif tool_result.status == "no_data":
                st.warning(f"△ {tool_result.label}: no recent data available")
            else:
                st.info(f"○ {tool_result.label}: no strong match found")

        st.markdown(result["answer"])

        if result["ranked_causes"]:
            st.markdown("### Ranked failure modes")
            causes_df = pd.DataFrame(result["ranked_causes"])
            causes_df = causes_df.rename(columns={"cause": "Failure mode", "score": "Evidence score"})
            st.dataframe(causes_df, hide_index=True, use_container_width=True)

        with st.expander("Evidence: equipment guidance"):
            if result["manual_hits"]:
                for i, hit in enumerate(result["manual_hits"], 1):
                    st.markdown(f"**Manual evidence {i}**")
                    st.write(hit["text"])
                    st.caption(f"Retrieval score: {hit['score']:.3f}")
            else:
                st.info("No relevant equipment guidance found.")

        with st.expander("Evidence: similar work orders"):
            if result["work_order_hits"]:
                st.dataframe(
                    pd.DataFrame(result["work_order_hits"]),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No similar work orders found.")

        with st.expander("Evidence: operating findings"):
            if result["scada_summary"]["findings"]:
                for finding in result["scada_summary"]["findings"]:
                    st.write(f"• {finding}")
            else:
                st.info("No abnormal operating findings were identified in the available window.")

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
            use_container_width=True,
        )

        st.line_chart(
            scada.set_index("timestamp")[["vibration_ips"]],
            use_container_width=True,
        )
    else:
        st.info("No SCADA demo data exists for this asset.")

    st.subheader("Maintenance history")
    if not work_orders.empty:
        st.dataframe(
            work_orders[
                ["work_order_id", "date", "problem", "cause", "corrective_action"]
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No work-order history found.")
