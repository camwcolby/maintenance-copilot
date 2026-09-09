from pathlib import Path
import os
import pandas as pd

REQUIRED_COLUMNS = {
    "work_order_id",
    "asset_id",
    "date",
    "problem",
    "cause",
    "corrective_action",
}


def configured_cmms_path():
    value = os.getenv("CMMS_CSV_PATH", "").strip()
    return Path(value) if value else None


def load_real_cmms_work_orders(asset_id: str):
    """Load a canonical CMMS export when CMMS_CSV_PATH is configured.

    This is the first production data seam: point CMMS_CSV_PATH to a normalized
    export and the copilot will use it before demo-generated maintenance history.
    """
    path = configured_cmms_path()
    if path is None or not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"CMMS CSV is missing required columns: {sorted(missing)}")

    result = df[df["asset_id"].astype(str) == str(asset_id)].copy()
    if not result.empty:
        result["source"] = "real-cmms-csv"
    return result
