import pandas as pd
import streamlit as st

from data_service import calculate_pump_hydraulics, load_assets, load_asset, load_condition_assessment, load_recent_scada, load_work_orders
from llm_agent import llm_available, run_copilot

st.set_page_config(page_title="Maintenance Copilot", page_icon="🔧", layout="wide")

st.title("🔧 Maintenance Copilot")
st.caption("Asset-aware troubleshooting using operating data, pump hydraulics, condition assessment, equipment guidance, maintenance history, and optional AI tool use.")

assets = load_assets()
facilities = sorted({a["facility"] for a in assets})
selected_facility = st.sidebar.selectbox("Facility", facilities)
facility_assets = [a for a in assets if a["facility"] == selected_facility]
asset_labels = {f"{a['asset_name']} | {a['asset_id']}": a["asset_id"] for a in facility_assets}
selected_label = st.sidebar.selectbox("Asset", list(asset_labels.keys()))
asset_id = asset_labels[selected_label]
asset = load_asset(asset_id)

use_ai = st.sidebar.toggle("Use AI agent", value=True, disabled=not llm_available())
if llm_available():
    st.sidebar.success("OpenAI API key detected")
else:
    st.sidebar.info("AI key not configured. Running deterministic evidence engine.")

st.sidebar.markdown("### Asset context")
st.sidebar.write(f"**ID:** {asset['asset_id']}")
st.sidebar.write(f"**Process:** {asset['process']}")
st.sidebar.write(f"**Type:** {asset['asset_type']}")
st.sidebar.write(f"**Model:** {asset['manufacturer']} {asset['model']}")
st.sidebar.write(f"**Criticality:** {asset['criticality']}")
st.sidebar.write(f"**Demo scenario:** {asset.get('scenario', 'n/a').title()}")

scada = load_recent_scada(asset_id)
work_orders = load_work_orders(asset_id)
condition = load_condition_assessment(asset_id)
hydraulics = calculate_pump_hydraulics(asset_id)

left, right = st.columns([1.25, 1])

with left:
    st.subheader("Ask Maintenance Copilot")
    default_q = "The pump is rattling and motor amps keep increasing. What should I check?"
    question = st.text_area("Question", value=default_q, height=105)
    st.caption('Try: "Why is this pump cavitating?" or "Is this pump operating on its pump curve?"')

    if st.button("Investigate", type="primary", width="stretch"):
        with st.spinner("Investigating asset condition..."):
            result = run_copilot(asset_id, question, prefer_llm=use_ai)

        st.caption(f"Response engine: {result.get('provider', 'Maintenance Copilot')}")
        if result.get("llm_error"):
            category = result.get("llm_error_category", "AI request")
            detail = result.get("llm_error_detail", "See Render logs for the server-side exception.")
            st.warning(f"AI synthesis was unavailable ({category}). {detail} The deterministic evidence engine answered instead.")

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
            st.markdown("### Deterministic evidence ranking")
            causes_df = pd.DataFrame(result["ranked_causes"]).rename(columns={"cause": "Failure mode", "score": "Evidence score"})
            st.dataframe(causes_df, hide_index=True, width="stretch")
            st.caption("This ranking remains available as a transparent safety rail even when AI synthesis is enabled.")

        with st.expander("Evidence: condition assessment"):
            st.json(result.get("condition_assessment", {}))
        with st.expander("Evidence: pump curve and NPSH"):
            st.json(result.get("pump_hydraulics", {}))
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
                st.dataframe(pd.DataFrame(result["work_order_hits"]), hide_index=True, width="stretch")
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
    latest = scada.iloc[-1]
    m1, m2, m3 = st.columns(3)
    m1.metric("Motor amps", f"{latest['motor_amps']:.1f} A")
    m2.metric("Bearing temp", f"{latest['bearing_temp_f']:.0f} °F")
    m3.metric("Vibration", f"{latest['vibration_ips']:.2f} in/s")
    st.line_chart(scada.set_index("timestamp")[["motor_amps", "bearing_temp_f"]], width="stretch")
    st.line_chart(scada.set_index("timestamp")[["vibration_ips"]], width="stretch")

    st.subheader("Hydraulic snapshot")
    h1, h2, h3 = st.columns(3)
    h1.metric("Flow", f"{hydraulics['flow_mgd']:.2f} MGD")
    h2.metric("TDH", f"{hydraulics['actual_tdh_ft']:.1f} ft")
    h3.metric("NPSH margin", f"{hydraulics['npsh_margin_ft']:.1f} ft")
    curve_label = "On curve" if hydraulics["on_pump_curve"] else "Off curve"
    por_label = "Inside POR" if hydraulics["in_preferred_operating_region"] else "Outside POR"
    st.caption(f"{curve_label} | {hydraulics['curve_deviation_pct']:+.1f}% head deviation | {hydraulics['bep_flow_pct']:.0f}% of BEP | {por_label} | Cavitation risk: {hydraulics['cavitation_risk']}")

    st.subheader("Latest condition assessment")
    c1, c2, c3 = st.columns(3)
    c1.metric("Score", f"{condition.get('condition_score', 'n/a')}/100")
    c2.metric("Risk", str(condition.get("risk_level", "n/a")))
    c3.metric("Est. RUL", f"{condition.get('estimated_rul_months', 'n/a')} mo")
    st.write(condition.get("visual_findings", "No assessment available."))
    st.caption("Demo source: dummy condition-assessment dataset")

    st.subheader("Maintenance history")
    st.dataframe(work_orders[["work_order_id", "date", "problem", "cause", "corrective_action"]], hide_index=True, width="stretch")
    if "source" in work_orders.columns:
        st.caption("Data source: " + ", ".join(sorted(work_orders["source"].dropna().astype(str).unique())))

st.divider()
st.caption("Prototype decision support only. Hydraulic and condition-assessment values are synthetic demo data and should be confirmed against real OEM and site information.")
