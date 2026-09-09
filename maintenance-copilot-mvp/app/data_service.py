from pathlib import Path
import json
import pandas as pd

BASE = Path(__file__).resolve().parents[1]

def load_assets():
    with open(BASE / "data/assets/assets.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_asset(asset_id):
    for asset in load_assets():
        if asset["asset_id"] == asset_id:
            return asset
    raise KeyError(asset_id)

def load_work_orders(asset_id):
    df = pd.read_csv(BASE / "data/work_orders/work_orders.csv")
    return df[df["asset_id"] == asset_id].copy()

def load_recent_scada(asset_id):
    mapping = {
        "RAS-P-003": BASE / "data/scada/ras_p003_recent.csv",
    }
    path = mapping.get(asset_id)
    if path is None or not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df

def load_manual(asset):
    path = BASE / asset["manual"]
    return path.read_text(encoding="utf-8")
