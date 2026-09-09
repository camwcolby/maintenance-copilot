from collections import Counter

from tools import (
    get_asset_context,
    get_scada_trend,
    search_asset_work_orders,
    search_manuals,
)


def summarize_scada(asset, scada):
    if scada.empty:
        return {
            "status": "No live/recent data available",
            "findings": [],
            "latest": {},
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
            findings.append(
                f"Bearing temperature increased {end - start:.0f} F during the recent window."
            )

    if "vibration_ips" in scada.columns:
        start = scada["vibration_ips"].iloc[0]
        end = scada["vibration_ips"].iloc[-1]
        if end > start * 1.5:
            findings.append(
                f"Vibration increased from {start:.2f} to {end:.2f} in/s."
            )

    if "flow_mgd" in scada.columns:
        start = scada["flow_mgd"].iloc[0]
        end = scada["flow_mgd"].iloc[-1]
        if end < start * 0.98:
            findings.append(
                f"Pump flow declined from {start:.2f} to {end:.2f} MGD."
            )

    return {
        "status": "Attention" if findings else "Normal",
        "findings": findings,
        "latest": latest,
    }


def _rank_causes(scada_summary, work_order_hits):
    scores = Counter()

    findings_text = " ".join(scada_summary.get("findings", [])).lower()
    if "bearing temperature" in findings_text and "vibration" in findings_text:
        scores["Bearing degradation or lubrication issue"] += 3
    if "motor current" in findings_text:
        scores["Mechanical loading / obstruction"] += 2
    if "flow declined" in findings_text:
        scores["Suction or impeller obstruction"] += 2

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

    ranked = [
        {"cause": cause, "score": round(float(score), 2)}
        for cause, score in scores.most_common(4)
    ]
    return ranked


def _confidence(ranked_causes, manual_hits, work_order_hits, scada_summary):
    evidence_channels = sum(
        [
            bool(scada_summary.get("findings")),
            bool(manual_hits),
            bool(work_order_hits),
        ]
    )
    if evidence_channels == 3 and ranked_causes:
        return "HIGH"
    if evidence_channels >= 2:
        return "MODERATE"
    return "LOW"


def build_answer(question, asset, scada_summary, manual_hits, work_order_hits, ranked_causes=None, confidence=None):
    ranked_causes = ranked_causes or _rank_causes(scada_summary, work_order_hits)
    confidence = confidence or _confidence(
        ranked_causes, manual_hits, work_order_hits, scada_summary
    )
    lines = []

    if ranked_causes:
        lines.append(
            f"### Most likely issue\n**{ranked_causes[0]['cause']}**  \nConfidence: **{confidence}**"
        )
    else:
        lines.append("### Most likely issue\nInsufficient evidence to rank a specific failure mode.")

    if len(ranked_causes) > 1:
        lines.append("\n**Other plausible causes**")
        for item in ranked_causes[1:]:
            lines.append(f"- {item['cause']}")

    if scada_summary["findings"]:
        lines.append("\n**What the operating data shows**")
        for item in scada_summary["findings"]:
            lines.append(f"- {item}")

    if work_order_hits:
        lines.append("\n**Similar history on this asset**")
        for wo in work_order_hits[:3]:
            lines.append(
                f"- **{wo['work_order_id']}** ({wo['date']}): {wo['problem']} "
                f"Cause: {wo['cause']}. Resolution: {wo['corrective_action']}."
            )

    if manual_hits:
        lines.append("\n**Relevant equipment guidance**")
        for i, hit in enumerate(manual_hits[:2], 1):
            short = hit["text"].replace("\n", " ")
            lines.append(f"- Manual evidence {i}: {short}")

    lines.append("\n**Recommended troubleshooting sequence**")
    lines.append(
        "1. Verify the equipment can be inspected safely and follow facility lockout/tagout requirements before intrusive work."
    )
    lines.append(
        "2. Check bearing temperature, noise, lubrication condition, and mechanical looseness."
    )
    lines.append("3. Verify coupling alignment and fastener torque.")
    lines.append("4. Check suction and impeller for ragging or debris.")
    lines.append(
        "5. Verify downstream valve position and discharge pressure before concluding the pump itself is failing."
    )

    latest = scada_summary.get("latest", {})
    if latest:
        temp = latest.get("bearing_temp_f")
        vib = latest.get("vibration_ips")
        if temp is not None and vib is not None:
            lines.append(
                f"\nLatest reading: **{temp:.0f} F bearing temperature** and "
                f"**{vib:.2f} in/s vibration**. Continue to compare these values with OEM and site-specific alarm limits."
            )

    lines.append(
        "\n*This prototype provides decision support only. It does not issue equipment commands or replace OEM procedures, site safety requirements, or qualified maintenance judgment.*"
    )

    return "\n".join(lines)


def run_investigation(asset_id, question):
    """Run an asset-aware maintenance investigation through explicit tools.

    The orchestrator is deterministic for the MVP so its evidence path is transparent
    and testable. A future LLM can choose among these same tools without changing the
    underlying data interfaces.
    """
    trace = []

    asset_result = get_asset_context(asset_id)
    trace.append(asset_result)
    asset = asset_result.data

    scada_result = get_scada_trend(asset_id)
    trace.append(scada_result)
    scada_summary = summarize_scada(asset, scada_result.data)

    manual_result = search_manuals(asset_id, question, top_k=3)
    trace.append(manual_result)

    work_orders_result = search_asset_work_orders(asset_id, question, top_k=3)
    trace.append(work_orders_result)

    ranked_causes = _rank_causes(scada_summary, work_orders_result.data)
    confidence = _confidence(
        ranked_causes,
        manual_result.data,
        work_orders_result.data,
        scada_summary,
    )

    answer = build_answer(
        question,
        asset,
        scada_summary,
        manual_result.data,
        work_orders_result.data,
        ranked_causes=ranked_causes,
        confidence=confidence,
    )

    return {
        "asset": asset,
        "question": question,
        "trace": trace,
        "scada_summary": scada_summary,
        "manual_hits": manual_result.data,
        "work_order_hits": work_orders_result.data,
        "ranked_causes": ranked_causes,
        "confidence": confidence,
        "answer": answer,
    }
