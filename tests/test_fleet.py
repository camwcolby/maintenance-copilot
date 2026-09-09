from app.data_service import calculate_pump_hydraulics, load_assets, load_condition_assessment, load_recent_scada, load_work_orders
from app.llm_agent import _classify_llm_error, run_copilot


def test_demo_fleet_has_multiple_assets_and_scenarios():
    assets = load_assets()
    assert len(assets) >= 20
    assert len({a["scenario"] for a in assets}) >= 5


def test_generated_assets_have_operating_and_maintenance_data():
    asset_id = "INF-P-0103"
    scada = load_recent_scada(asset_id)
    work_orders = load_work_orders(asset_id)
    assert not scada.empty
    assert {"motor_amps", "flow_mgd", "bearing_temp_f", "vibration_ips", "suction_pressure_psi", "speed_pct"}.issubset(scada.columns)
    assert len(work_orders) >= 3


def test_condition_assessment_is_available_for_demo_asset():
    assessment = load_condition_assessment("RAS-P-0301")
    assert assessment["condition_score"] > 0
    assert assessment["visual_findings"]
    assert assessment["source"] == "dummy-condition-assessment"


def test_cavitation_demo_has_low_npsh_margin_and_evidence():
    hydraulics = calculate_pump_hydraulics("INF-P-0303")
    assert hydraulics["cavitation_risk"] in {"High", "Elevated"}
    assert hydraulics["npsh_margin_ft"] < 3.0
    assert hydraulics["cavitation_evidence"]


def test_curve_question_returns_hydraulic_answer_without_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = run_copilot("RAS-P-0301", "Is this pump operating on its pump curve?")
    assert result["llm_used"] is False
    assert "Pump curve check" in result["answer"]
    assert "pump_hydraulics" in result
    assert "condition_assessment" in result


def test_copilot_runs_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = run_copilot("RAS-P-003", "The pump is rattling and amps are increasing.")
    assert result["llm_used"] is False
    assert result["answer"]
    assert result["ranked_causes"]


def test_openai_error_classifier_identifies_quota():
    class FakeRateLimitError(Exception):
        status_code = 429

    category, detail = _classify_llm_error(FakeRateLimitError("insufficient_quota"))
    assert category == "quota/rate limit"
    assert "billing" in detail.lower()


def test_openai_error_classifier_identifies_authentication():
    class FakeAuthenticationError(Exception):
        status_code = 401

    category, detail = _classify_llm_error(FakeAuthenticationError("invalid api key"))
    assert category == "authentication"
    assert "OPENAI_API_KEY" in detail
