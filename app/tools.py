from dataclasses import dataclass
from typing import Any

try:
    from .data_service import (
        calculate_pump_hydraulics,
        load_asset,
        load_condition_assessment,
        load_manual,
        load_recent_scada,
        load_work_orders,
    )
    from .retrieval import search_text, search_work_orders
except ImportError:
    from data_service import (
        calculate_pump_hydraulics,
        load_asset,
        load_condition_assessment,
        load_manual,
        load_recent_scada,
        load_work_orders,
    )
    from retrieval import search_text, search_work_orders


@dataclass
class ToolResult:
    tool: str
    label: str
    status: str
    data: Any


def get_asset_context(asset_id: str) -> ToolResult:
    asset = load_asset(asset_id)
    return ToolResult(
        tool="get_asset_context",
        label="Reviewed asset context",
        status="complete",
        data=asset,
    )


def get_scada_trend(asset_id: str) -> ToolResult:
    scada = load_recent_scada(asset_id)
    return ToolResult(
        tool="get_scada_trend",
        label="Analyzed recent operating trend",
        status="complete" if not scada.empty else "no_data",
        data=scada,
    )


def get_condition_assessment(asset_id: str) -> ToolResult:
    assessment = load_condition_assessment(asset_id)
    return ToolResult(
        tool="get_condition_assessment",
        label="Reviewed latest condition assessment",
        status="complete" if assessment else "no_data",
        data=assessment,
    )


def get_pump_hydraulics(asset_id: str) -> ToolResult:
    hydraulics = calculate_pump_hydraulics(asset_id)
    return ToolResult(
        tool="get_pump_hydraulics",
        label="Checked pump curve and suction hydraulics",
        status="complete" if hydraulics else "no_data",
        data=hydraulics,
    )


def search_manuals(asset_id: str, query: str, top_k: int = 3) -> ToolResult:
    asset = load_asset(asset_id)
    manual = load_manual(asset)
    hits = search_text(query, manual, top_k=top_k)
    return ToolResult(
        tool="search_manuals",
        label="Searched equipment troubleshooting guidance",
        status="complete" if hits else "no_match",
        data=hits,
    )


def search_asset_work_orders(asset_id: str, query: str, top_k: int = 3) -> ToolResult:
    work_orders = load_work_orders(asset_id)
    hits = search_work_orders(query, work_orders, top_k=top_k)
    return ToolResult(
        tool="search_asset_work_orders",
        label="Searched similar maintenance history",
        status="complete" if hits else "no_match",
        data=hits,
    )
