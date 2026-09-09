import pandas as pd

def summarize_scada(asset, scada):
    if scada.empty:
        return {
            "status": "No live/recent data available",
            "findings": [],
            "latest": {}
        }

    latest = scada.iloc[-1].to_dict()
    findings = []

    rated_amps = asset.get("rated_amps")
    if rated_amps and latest.get("motor_amps") is not None:
        pct = latest["motor_amps"] / rated_amps * 100
        if pct > 120:
            findings.append(f"Motor current is {pct:.0f}% of rated current.")
        elif pct > 110:
            findings.append(f"Motor current is elevated at {pct:.0f}% of rated current.")

    if "bearing_temp_f" in scada.columns:
        start = scada["bearing_temp_f"].iloc[0]
        end = scada["bearing_temp_f"].iloc[-1]
        if end - start >= 20:
            findings.append(f"Bearing temperature increased {end-start:.0f} F during the recent window.")

    if "vibration_ips" in scada.columns:
        start = scada["vibration_ips"].iloc[0]
        end = scada["vibration_ips"].iloc[-1]
        if end > start * 1.5:
            findings.append(f"Vibration increased from {start:.2f} to {end:.2f} in/s.")

    if "flow_mgd" in scada.columns:
        start = scada["flow_mgd"].iloc[0]
        end = scada["flow_mgd"].iloc[-1]
        if end < start * 0.98:
            findings.append(f"Pump flow declined from {start:.2f} to {end:.2f} MGD.")

    return {
        "status": "Attention" if findings else "Normal",
        "findings": findings,
        "latest": latest
    }

def build_answer(question, asset, scada_summary, manual_hits, work_order_hits):
    lines = []

    lines.append(
        f"For **{asset['asset_name']}**, the current evidence points first toward a mechanical-load issue rather than a process-flow increase."
    )

    if scada_summary["findings"]:
        lines.append("\n**What the operating data shows**")
        for item in scada_summary["findings"]:
            lines.append(f"- {item}")

    if manual_hits:
        lines.append("\n**Most relevant OEM troubleshooting guidance**")
        for i, hit in enumerate(manual_hits[:2], 1):
            short = hit["text"].replace("\n", " ")
            lines.append(f"- Manual evidence {i}: {short}")

    if work_order_hits:
        lines.append("\n**Similar history on this asset**")
        for wo in work_order_hits[:3]:
            lines.append(
                f"- {wo['work_order_id']} ({wo['date']}): {wo['problem']} "
                f"Cause: {wo['cause']}. Resolution: {wo['corrective_action']}."
            )

    lines.append("\n**Recommended troubleshooting sequence**")
    lines.append("1. Verify the pump can be inspected safely and follow lockout/tagout requirements before intrusive work.")
    lines.append("2. Check bearing temperature, noise, lubrication condition, and mechanical looseness.")
    lines.append("3. Verify coupling alignment and fastener torque.")
    lines.append("4. Check suction and impeller for ragging or debris.")
    lines.append("5. Verify downstream valve position and discharge pressure before concluding the pump itself is failing.")

    latest = scada_summary.get("latest", {})
    if latest:
        temp = latest.get("bearing_temp_f")
        vib = latest.get("vibration_ips")
        if temp is not None and vib is not None:
            lines.append(
                f"\nThe latest demo reading is **{temp:.0f} F bearing temperature** and "
                f"**{vib:.2f} in/s vibration**. Those values are close to the manual's escalation thresholds, "
                "so this should be treated as an active maintenance concern rather than routine monitoring."
            )

    lines.append("\n**Evidence used:** current/recent SCADA trend, asset troubleshooting manual, and prior work orders. This prototype does not issue control commands or bypass maintenance safety procedures.")

    return "\n".join(lines)
