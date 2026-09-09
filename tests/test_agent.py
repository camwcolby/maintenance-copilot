from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from agent import run_investigation


def test_investigation_uses_expected_tools_and_ranks_bearing_issue():
    result = run_investigation(
        "RAS-P-003",
        "The pump is rattling and motor amps keep increasing. What should I check?",
    )

    tool_names = [step.tool for step in result["trace"]]
    assert tool_names == [
        "get_asset_context",
        "get_scada_trend",
        "search_manuals",
        "search_asset_work_orders",
    ]

    assert result["confidence"] == "HIGH"
    assert result["ranked_causes"]
    assert result["ranked_causes"][0]["cause"] == "Bearing degradation or lubrication issue"
    assert result["manual_hits"]
    assert result["work_order_hits"]


def test_investigation_returns_grounded_answer():
    result = run_investigation(
        "RAS-P-003",
        "The pump has high vibration and high amperage.",
    )

    answer = result["answer"]
    assert "Recommended troubleshooting sequence" in answer
    assert "work order" not in answer.lower() or result["work_order_hits"]
    assert "lockout/tagout" in answer.lower()
