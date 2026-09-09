from app.data_service import load_assets, load_recent_scada, load_work_orders
from app.llm_agent import run_copilot


def test_demo_fleet_has_multiple_assets_and_scenarios():
    assets = load_assets()
    assert len(assets) >= 20
    assert len({a["scenario"] for a in assets}) >= 5


def test_generated_assets_have_operating_and_maintenance_data():
    asset_id = "INF-P-0103"
    scada = load_recent_scada(asset_id)
    work_orders = load_work_orders(asset_id)
    assert not scada.empty
    assert {"motor_amps", "flow_mgd", "bearing_temp_f", "vibration_ips"}.issubset(scada.columns)
    assert len(work_orders) >= 3


def test_copilot_runs_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = run_copilot("RAS-P-003", "The pump is rattling and amps are increasing.")
    assert result["llm_used"] is False
    assert result["answer"]
    assert result["ranked_causes"]
