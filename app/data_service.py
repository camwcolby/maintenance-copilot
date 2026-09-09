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


def load_assets():
    with open(BASE / "data/assets/assets.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_asset(asset_id):
    for asset in load_assets():
        if asset["asset_id"] == asset_id:
            return asset
    raise KeyError(asset_id)


def _rng(asset_id):
    seed = int(hashlib.sha256(asset_id.encode("utf-8")).hexdigest()[:8], 16)
    return np.random.default_rng(seed)


def _synthetic_work_orders(asset):
    scenario = asset.get("scenario", "normal")
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

    amps = rated_amps * (0.88 + rng.normal(0, 0.008, n))
    flow = rated_flow * (0.94 + rng.normal(0, 0.006, n))
    pressure = 18 + rng.normal(0, 0.15, n)
    temp = 138 + rng.normal(0, 1.0, n)
    vibration = 0.14 + rng.normal(0, 0.008, n)

    if scenario == "bearing":
        amps += rated_amps * 0.30 * x
        temp += 42 * x
        vibration += 0.34 * x
        flow -= rated_flow * 0.04 * x
    elif scenario == "obstruction":
        amps += rated_amps * 0.22 * x
        flow -= rated_flow * 0.22 * x
        vibration += 0.12 * x
    elif scenario == "coupling":
        amps += rated_amps * 0.10 * x
        vibration += 0.40 * x
        temp += 15 * x
    elif scenario == "discharge":
        amps += rated_amps * 0.24 * x
        pressure += 10 * x
        flow -= rated_flow * 0.16 * x
    elif scenario == "seal":
        temp += 18 * x
        vibration += 0.08 * x

    return pd.DataFrame(
        {
            "timestamp": times,
            "motor_amps": np.round(amps, 2),
            "flow_mgd": np.round(flow, 3),
            "discharge_pressure_psi": np.round(pressure, 2),
            "bearing_temp_f": np.round(temp, 1),
            "vibration_ips": np.round(np.maximum(vibration, 0.03), 3),
        }
    )


def load_recent_scada(asset_id):
    if asset_id == "RAS-P-003":
        path = BASE / "data/scada/ras_p003_recent.csv"
        if path.exists():
            return pd.read_csv(path, parse_dates=["timestamp"])
    return _synthetic_scada(load_asset(asset_id))


def load_manual(asset):
    path = BASE / asset["manual"]
    return path.read_text(encoding="utf-8")
