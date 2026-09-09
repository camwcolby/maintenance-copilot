from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

try:
    from .adapters.cmms_csv import load_real_cmms_work_orders
except ImportError:
    from adapters.cmms_csv import load_real_cmms_work_orders

BASE = Path(__file__).resolve().parents[1]
CAVITATION_DEMO_ASSETS = {"SMP-P-0105", "INF-P-0303"}


def load_assets():
    with open(BASE / "data/assets/assets.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_asset(asset_id):
    for asset in load_assets():
        if asset["asset_id"] == asset_id:
            return asset
    raise KeyError(asset_id)


def load_condition_assessment(asset_id):
    path = BASE / "data/condition/condition_assessments.csv"
    df = pd.read_csv(path, parse_dates=["assessment_date"])
    rows = df[df["asset_id"] == asset_id].sort_values("assessment_date")
    if rows.empty:
        return {}
    row = rows.iloc[-1].to_dict()
    row["assessment_date"] = row["assessment_date"].date().isoformat()
    return row


def load_pump_curve(asset_id):
    asset = load_asset(asset_id)
    with open(BASE / "data/pump_curves/pump_curves.json", "r", encoding="utf-8") as f:
        curves = json.load(f)
    return curves[asset["model"]]


def _interp_curve(curve, flow_mgd, field):
    flows = np.array([point["flow_mgd"] for point in curve], dtype=float)
    values = np.array([point[field] for point in curve], dtype=float)
    return float(np.interp(float(flow_mgd), flows, values))


def _rng(asset_id):
    seed = int(hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:8], 16)
    return np.random.default_rng(seed)


def _synthetic_work_orders(asset):
    scenario = asset.get("scenario", "normal")
    if asset["asset_id"] in CAVITATION_DEMO_ASSETS:
        scenario = "cavitation"
    templates = {
        "bearing": [
            ("Abnormal vibration and rising motor current", "Bearing degradation", "Replaced bearing; checked lubrication and alignment"),
            ("Bearing housing running hot", "Inadequate lubrication", "Corrected lubrication; inspected bearing condition"),
            ("Rattling noise during operation", "Mechanical looseness at bearing housing", "Re-torqued hardware and verified alignment"),
        ],
        "obstruction": [
            ("Motor current elevated and flow reduced", "Partial rag obstruction at suction", "Isolated pump; cleared obstruction; inspected impeller"),
            ("Intermittent loss of capacity", "Debris at impeller eye", "Removed debris and inspected wear surfaces"),
            ("Pump sounds loaded with low discharge flow", "Suction restriction", "Cleared suction path and verified wet-well condition"),
        ],
        "coupling": [
            ("High vibration after startup", "Coupling misalignment", "Realigned motor and pump; verified soft foot"),
            ("Rattling near coupling guard", "Loose coupling hardware", "Re-torqued coupling hardware and checked alignment"),
            ("Vibration increased after motor work", "Alignment drift", "Laser aligned motor and pump"),
        ],
        "discharge": [
            ("Motor load high with elevated discharge pressure", "Downstream valve partially closed", "Corrected valve position and verified pressure"),
            ("Reduced flow with high head", "Discharge restriction", "Inspected downstream piping and cleared restriction"),
            ("Pump overloaded at normal wet-well level", "Increased system head", "Verified valve lineup and downstream hydraulic condition"),
        ],
        "seal": [
            ("Leakage observed at pump seal", "Mechanical seal wear", "Replaced mechanical seal and inspected shaft sleeve"),
            ("Seal area running hot", "Seal flush restriction", "Restored seal flush and inspected seal faces"),
            ("Intermittent leakage after startup", "Seal face damage", "Replaced seal and verified alignment"),
        ],
        "cavitation": [
            ("Gravel-like noise and unstable flow", "Insufficient suction head", "Restored wet-well level and verified suction pressure"),
            ("Impeller eye showed pitting", "Cavitation erosion", "Inspected suction losses and established minimum submergence"),
            ("Vibration increased as wet well level fell", "Low NPSH margin", "Checked suction restriction and operating point"),
        ],
        "normal": [
            ("Routine preventive inspection", "No defect found", "Lubricated and returned to service"),
            ("Minor vibration check", "Within expected range", "No corrective work required"),
            ("Annual pump inspection", "Normal wear", "Documented condition and continued service"),
        ],
    }
    rows = []
    for i, (problem, cause, action) in enumerate(templates.get(scenario, templates["normal"]), 1):
        rows.append(
            {
                "work_order_id": f"SIM-{asset['asset_id']}-{i:02d}",
                "asset_id": asset["asset_id"],
                "date": f"2026-{max(1, 7-i):02d}-{10+i:02d}",
                "problem": problem,
                "cause": cause,
                "corrective_action": action,
                "downtime_hours": round(0.8 + i * 0.7, 1),
                "source": "synthetic-demo",
            }
        )
    return pd.DataFrame(rows)


def load_work_orders(asset_id):
    real = load_real_cmms_work_orders(asset_id)
    if not real.empty:
        return real

    df = pd.read_csv(BASE / "data/work_orders/work_orders.csv")
    existing = df[df["asset_id"] == asset_id].copy()
    if not existing.empty:
        existing["source"] = "static-demo"
        return existing
    return _synthetic_work_orders(load_asset(asset_id))


def _synthetic_scada(asset):
    rng = _rng(asset["asset_id"])
    n = 24
    times = pd.date_range("2026-09-09 11:00", periods=n, freq="5min")
    rated_amps = float(asset.get("rated_amps", 40))
    rated_flow = float(asset.get("rated_flow_mgd", 1.0))
    x = np.linspace(0, 1, n)
    scenario = asset.get("scenario", "normal")
    if asset["asset_id"] in CAVITATION_DEMO_ASSETS:
        scenario = "cavitation"

    amps = rated_amps * (0.88 + rng.normal(0, 0.008, n))
    flow = rated_flow * (0.94 + rng.normal(0, 0.006, n))
    temp = 138 + rng.normal(0, 1.0, n)
    vibration = 0.14 + rng.normal(0, 0.008, n)
    suction_pressure = -1.2 + rng.normal(0, 0.08, n)
    speed_pct = 100 + rng.normal(0, 0.15, n)

    if scenario == "bearing":
        amps += rated_amps * 0.30 * x
        temp += 42 * x
        vibration += 0.34 * x
        flow -= rated_flow * 0.04 * x
    elif scenario == "obstruction":
        amps += rated_amps * 0.22 * x
        flow -= rated_flow * 0.22 * x
        vibration += 0.12 * x
        suction_pressure -= 1.8 * x
    elif scenario == "coupling":
        amps += rated_amps * 0.10 * x
        vibration += 0.40 * x
        temp += 15 * x
    elif scenario == "discharge":
        amps += rated_amps * 0.24 * x
        flow -= rated_flow * 0.16 * x
    elif scenario == "seal":
        temp += 18 * x
        vibration += 0.08 * x
    elif scenario == "cavitation":
        flow -= rated_flow * 0.18 * x
        suction_pressure -= 6.0 * x
        vibration += 0.42 * x
        amps += rated_amps * 0.08 * x + rng.normal(0, rated_amps * 0.02, n)

    curve_def = load_pump_curve(asset["asset_id"])
    curve = curve_def["curve"]
    head = []
    for q, speed in zip(flow, speed_pct):
        speed_frac = max(float(speed) / 100.0, 0.1)
        base_flow = float(q) / speed_frac
        expected = _interp_curve(curve, base_flow, "head_ft") * speed_frac**2
        head.append(expected)
    head = np.array(head) + rng.normal(0, 1.2, n)
    if scenario == "obstruction":
        head -= 0.10 * head * x
    elif scenario == "cavitation":
        head -= 0.22 * head * x

    discharge_pressure = suction_pressure + head / 2.31
    wet_well_level = 12.5 + rng.normal(0, 0.15, n)
    if scenario == "cavitation":
        wet_well_level -= 5.0 * x

    return pd.DataFrame(
        {
            "timestamp": times,
            "motor_amps": np.round(amps, 2),
            "flow_mgd": np.round(flow, 3),
            "suction_pressure_psi": np.round(suction_pressure, 2),
            "discharge_pressure_psi": np.round(discharge_pressure, 2),
            "speed_pct": np.round(speed_pct, 2),
            "wet_well_level_ft": np.round(wet_well_level, 2),
            "bearing_temp_f": np.round(temp, 1),
            "vibration_ips": np.round(np.maximum(vibration, 0.03), 3),
        }
    )


def load_recent_scada(asset_id):
    if asset_id == "RAS-P-003":
        path = BASE / "data/scada/ras_p003_recent.csv"
        if path.exists():
            df = pd.read_csv(path, parse_dates=["timestamp"])
            if "suction_pressure_psi" not in df.columns:
                df["suction_pressure_psi"] = -1.2
            if "speed_pct" not in df.columns:
                df["speed_pct"] = 100.0
            if "wet_well_level_ft" not in df.columns:
                df["wet_well_level_ft"] = 12.0
            return df
    return _synthetic_scada(load_asset(asset_id))


def calculate_pump_hydraulics(asset_id):
    scada = load_recent_scada(asset_id)
    latest = scada.iloc[-1]
    curve_def = load_pump_curve(asset_id)
    curve = curve_def["curve"]

    flow = float(latest["flow_mgd"])
    suction_psi = float(latest.get("suction_pressure_psi", -1.2))
    discharge_psi = float(latest["discharge_pressure_psi"])
    speed_pct = float(latest.get("speed_pct", 100.0))
    speed_frac = max(speed_pct / 100.0, 0.1)

    equivalent_flow = flow / speed_frac
    expected_head = _interp_curve(curve, equivalent_flow, "head_ft") * speed_frac**2
    actual_head = (discharge_psi - suction_psi) * 2.31
    npshr = _interp_curve(curve, equivalent_flow, "npshr_ft") * speed_frac**2
    efficiency = _interp_curve(curve, equivalent_flow, "efficiency_pct")
    npsha = 33.9 + suction_psi * 2.31 - 0.8
    npsh_margin = npsha - npshr
    deviation_pct = 100.0 * (actual_head - expected_head) / max(expected_head, 1.0)

    bep_flow_at_speed = float(curve_def["bep_flow_mgd"]) * speed_frac
    bep_pct = 100.0 * flow / max(bep_flow_at_speed, 0.01)
    por_low, por_high = curve_def["preferred_operating_region_pct_bep"]
    in_por = por_low <= bep_pct <= por_high
    on_curve = abs(deviation_pct) <= 10.0
    cavitation_risk = "High" if npsh_margin < 1.0 else "Elevated" if npsh_margin < 3.0 else "Low"

    reasons = []
    if npsh_margin < 3.0:
        reasons.append("available NPSH margin is small")
    if suction_psi < -4.0:
        reasons.append("suction pressure is strongly negative")
    if float(latest.get("wet_well_level_ft", 99)) < 8.0:
        reasons.append("wet-well level is low")
    if float(latest.get("vibration_ips", 0)) > 0.35:
        reasons.append("vibration is elevated")
    if deviation_pct < -10:
        reasons.append("measured head is below the expected pump curve")

    return {
        "flow_mgd": round(flow, 3),
        "speed_pct": round(speed_pct, 1),
        "suction_pressure_psi": round(suction_psi, 2),
        "discharge_pressure_psi": round(discharge_psi, 2),
        "actual_tdh_ft": round(actual_head, 1),
        "expected_curve_head_ft": round(expected_head, 1),
        "curve_deviation_pct": round(deviation_pct, 1),
        "on_pump_curve": bool(on_curve),
        "estimated_efficiency_pct": round(efficiency, 1),
        "bep_flow_pct": round(bep_pct, 1),
        "in_preferred_operating_region": bool(in_por),
        "npsha_ft": round(npsha, 1),
        "npshr_ft": round(npshr, 1),
        "npsh_margin_ft": round(npsh_margin, 1),
        "cavitation_risk": cavitation_risk,
        "cavitation_evidence": reasons,
        "curve_source": f"dummy OEM curve for {load_asset(asset_id)['model']}",
    }


def load_manual(asset):
    path = BASE / asset["manual"]
    return path.read_text(encoding="utf-8")
