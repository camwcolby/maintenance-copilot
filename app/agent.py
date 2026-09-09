from collections import Counter

try:
    from .tools import (
        get_asset_context,
        get_condition_assessment,
        get_pump_hydraulics,
        get_scada_trend,
        search_asset_work_orders,
        search_manuals,
    )
except ImportError:
    from tools import (
        get_asset_context,
        get_condition_assessment,
        get_pump_hydraulics,
        get_scada_trend,
        search_asset_work_orders,
        search_manuals,
    )


def summarize_scada(asset, scada):
    if scada.empty:
        return {"status": "No live/recent data available", "findings": [], "latest": {}}

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
            findings.append(f"Bearing temperature increased {end - start:.0f} F during the recent window.")

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

    if "suction_pressure_psi" in scada.columns:
        if latest["suction_pressure_psi"] < -4.0:
            findings.append(f"Suction pressure is strongly negative at {latest['suction_pressure_psi']:.1f} psi.")

    return {"status": "Attention" if findings else "Normal", "findings": findings, "latest": latest}


def _rank_causes(scada_summary, work_order_hits, hydraulics=None, condition=None):
    scores = Counter()
    findings_text = " ".join(scada_summary.get("findings", [])).lower()
    if "bearing temperature" in findings_text and "vibration" in findings_text:
        scores["Bearing degradation or lubrication issue"] += 3
    if "motor current" in findings_text:
        scores["Mechanical loading / obstruction"] += 2
    if "flow declined" in findings_text:
        scores["Suction or impeller obstruction"] += 2
    if "suction pressure" in findings_text:
        scores["Insufficient suction head / cavitation"] += 3

    hydraulics = hydraulics or {}
    if hydraulics.get("cavitation_risk") == "High":
        scores["Insufficient suction head / cavitation"] += 5
    elif hydraulics.get("cavitation_risk") == "Elevated":
        scores["Insufficient suction head / cavitation"] += 2
    if hydraulics.get("on_pump_curve") is False:
        scores["Hydraulic performance deviation / pump wear or sensor issue"] += 3
    if hydraulics.get("in_preferred_operating_region") is False:
        scores["Operation outside preferred region around BEP"] += 2

    condition = condition or {}
    visual = str(condition.get("visual_findings", "")).lower()
    if "cavitation" in visual or "impeller eye" in visual or "pitting" in visual:
        scores["Insufficient suction head / cavitation"] += 4
    if "alignment" in visual:
        scores["Coupling misalignment or looseness"] += 3
    if "bearing" in visual:
        scores["Bearing degradation or lubrication issue"] += 3

    for wo in work_order_hits:
        cause = str(wo.get("cause", "")).lower()
        problem = str(wo.get("problem", "")).lower()
        text = f"{cause} {problem}"
        weight = max(float(wo.get("score", 0.0)), 0.1)
        if "bearing" in text:
            scores["Bearing degradation or lubrication issue"] += 2 * weight
        if "obstruction" in text or "rag" in text or "impeller" in text:
            scores["Suction or impeller obstruction"] += 2 * weight
        if "coupling" in text or "alignment" in text:
            scores["Coupling misalignment or looseness"] += 1.5 * weight
        if "valve" in text or "discharge" in text:
            scores["Downstream restriction / increased discharge head"] += 1.5 * weight
        if "cavitation" in text or "npsh" in text or "suction head" in text:
            scores["Insufficient suction head / cavitation"] += 2.5 * weight

    return [{"cause": cause, "score": round(float(score), 2)} for cause, score in scores.most_common(5)]


def _confidence(ranked_causes, manual_hits, work_order_hits, scada_summary, hydraulics, condition):
    evidence_channels = sum([
        bool(scada_summary.get("findings")), bool(manual_hits), bool(work_order_hits), bool(hydraulics), bool(condition)
    ])
    if evidence_channels >= 4 and ranked_causes:
        return "HIGH"
    if evidence_channels >= 2:
        return "MODERATE"
    return "LOW"


def build_answer(question, asset, scada_summary, manual_hits, work_order_hits, hydraulics, condition, ranked_causes=None, confidence=None):
    ranked_causes = ranked_causes or _rank_causes(scada_summary, work_order_hits, hydraulics, condition)
    confidence = confidence or _confidence(ranked_causes, manual_hits, work_order_hits, scada_summary, hydraulics, condition)
    q = question.lower()
    lines = []

    if "curve" in q or "bep" in q or "operating point" in q:
        status = "YES" if hydraulics.get("on_pump_curve") else "NO"
        por = "inside" if hydraulics.get("in_preferred_operating_region") else "outside"
        lines.append(f"### Pump curve check\n**On the expected speed-adjusted curve: {status}**")
        lines.append(
            f"Current point: **{hydraulics.get('flow_mgd')} MGD at {hydraulics.get('actual_tdh_ft')} ft TDH** versus "
            f"**{hydraulics.get('expected_curve_head_ft')} ft expected** ({hydraulics.get('curve_deviation_pct')}% deviation)."
        )
        lines.append(
            f"The pump is operating at **{hydraulics.get('bep_flow_pct')}% of BEP flow**, {por} the dummy preferred operating region. "
            f"Estimated efficiency is **{hydraulics.get('estimated_efficiency_pct')}%**."
        )
    elif "cavitat" in q or "npsh" in q or "gravel" in q:
        lines.append(f"### Cavitation assessment\nCurrent cavitation risk: **{hydraulics.get('cavitation_risk', 'Unknown').upper()}**")
        lines.append(
            f"NPSHa is approximately **{hydraulics.get('npsha_ft')} ft** versus NPSHr of **{hydraulics.get('npshr_ft')} ft**, "
            f"leaving a margin of **{hydraulics.get('npsh_margin_ft')} ft**."
        )
        if hydraulics.get("cavitation_evidence"):
            lines.append("Evidence pointing toward cavitation: " + "; ".join(hydraulics["cavitation_evidence"]) + ".")
        if condition.get("visual_findings"):
            lines.append(f"The latest condition assessment also reports: **{condition['visual_findings']}**.")
    elif ranked_causes:
        lines.append(f"### Most likely issue\n**{ranked_causes[0]['cause']}**  \nConfidence: **{confidence}**")
    else:
        lines.append("### Most likely issue\nInsufficient evidence to rank a specific failure mode.")

    if ranked_causes and not ("curve" in q or "cavitat" in q or "npsh" in q):
        if len(ranked_causes) > 1:
            lines.append("\n**Other plausible causes**")
            for item in ranked_causes[1:]:
                lines.append(f"- {item['cause']}")

    if scada_summary["findings"]:
        lines.append("\n**What the operating data shows**")
        for item in scada_summary["findings"]:
            lines.append(f"- {item}")

    if condition:
        lines.append("\n**Latest condition assessment**")
        lines.append(
            f"- Score **{condition.get('condition_score')}/100 ({condition.get('condition_rating')})**, risk **{condition.get('risk_level')}**, "
            f"estimated remaining life **{condition.get('estimated_rul_months')} months**."
        )
        lines.append(f"- Finding: {condition.get('visual_findings')}")
        lines.append(f"- Recommended action: {condition.get('recommended_action')}")

    if work_order_hits:
        lines.append("\n**Similar history on this asset**")
        for wo in work_order_hits[:3]:
            lines.append(f"- **{wo['work_order_id']}** ({wo['date']}): {wo['problem']} Cause: {wo['cause']}. Resolution: {wo['corrective_action']}.")

    lines.append("\n**Recommended troubleshooting sequence**")
    if hydraulics.get("cavitation_risk") in {"High", "Elevated"} or "cavitat" in q:
        lines.append("1. Verify safe inspection conditions and follow site lockout/tagout requirements before intrusive work.")
        lines.append("2. Check wet-well level/submergence and confirm the suction path is unobstructed.")
        lines.append("3. Verify suction pressure instrumentation and inspect for plugged strainers, partially closed valves, or excessive suction losses.")
        lines.append("4. Check for air ingress at suction joints, seals, vortexing, or entrained gas.")
        lines.append("5. Compare actual flow/TDH and NPSH margin with the OEM curve before changing the operating point.")
    else:
        lines.append("1. Verify the equipment can be inspected safely and follow facility lockout/tagout requirements before intrusive work.")
        lines.append("2. Check bearing temperature, noise, lubrication condition, and mechanical looseness.")
        lines.append("3. Verify coupling alignment and fastener torque.")
        lines.append("4. Check suction and impeller for ragging or debris.")
        lines.append("5. Verify downstream valve position, suction condition, and actual operating point against the pump curve.")

    lines.append("\n*Prototype decision support using synthetic/demo data, including dummy pump curves and condition assessments. Confirm against actual OEM curves, calibrated instruments, site procedures, and qualified maintenance judgment before operational decisions.*")
    return "\n".join(lines)


def run_investigation(asset_id, question):
    trace = []
    asset_result = get_asset_context(asset_id)
    trace.append(asset_result)
    asset = asset_result.data

    scada_result = get_scada_trend(asset_id)
    trace.append(scada_result)
    scada_summary = summarize_scada(asset, scada_result.data)

    hydraulics_result = get_pump_hydraulics(asset_id)
    trace.append(hydraulics_result)
    condition_result = get_condition_assessment(asset_id)
    trace.append(condition_result)
    manual_result = search_manuals(asset_id, question, top_k=3)
    trace.append(manual_result)
    work_orders_result = search_asset_work_orders(asset_id, question, top_k=3)
    trace.append(work_orders_result)

    ranked_causes = _rank_causes(scada_summary, work_orders_result.data, hydraulics_result.data, condition_result.data)
    confidence = _confidence(ranked_causes, manual_result.data, work_orders_result.data, scada_summary, hydraulics_result.data, condition_result.data)
    answer = build_answer(question, asset, scada_summary, manual_result.data, work_orders_result.data, hydraulics_result.data, condition_result.data, ranked_causes, confidence)

    return {
        "asset": asset,
        "question": question,
        "trace": trace,
        "scada_summary": scada_summary,
        "pump_hydraulics": hydraulics_result.data,
        "condition_assessment": condition_result.data,
        "manual_hits": manual_result.data,
        "work_order_hits": work_orders_result.data,
        "ranked_causes": ranked_causes,
        "confidence": confidence,
        "answer": answer,
    }
