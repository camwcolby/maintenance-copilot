import json
import os
from typing import Any

try:
    from .agent import run_investigation, summarize_scada
    from .tools import (
        ToolResult,
        get_asset_context,
        get_scada_trend,
        search_asset_work_orders,
        search_manuals,
    )
except ImportError:
    from agent import run_investigation, summarize_scada
    from tools import (
        ToolResult,
        get_asset_context,
        get_scada_trend,
        search_asset_work_orders,
        search_manuals,
    )


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict(orient="records")
        except TypeError:
            return value.to_dict()
    if isinstance(value, ToolResult):
        return {
            "tool": value.tool,
            "label": value.label,
            "status": value.status,
            "data": _jsonable(value.data),
        }
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


def _tool_definitions():
    return [
        {
            "type": "function",
            "name": "get_asset_context",
            "description": "Get identity, service, manufacturer, model, ratings, process, and criticality for the selected asset.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "get_scada_trend",
            "description": "Get the recent operating trend for the selected asset, including motor current, flow, discharge pressure, temperature, and vibration when available.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "search_manuals",
            "description": "Search equipment/OEM troubleshooting guidance for the selected asset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Troubleshooting symptoms or failure mode to search for."}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "search_work_orders",
            "description": "Search prior maintenance work orders for similar symptoms, causes, and corrective actions on the selected asset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Symptoms or suspected failure mode to search for."}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    ]


def _execute_tool(name: str, args: dict, asset_id: str) -> ToolResult:
    if name == "get_asset_context":
        return get_asset_context(asset_id)
    if name == "get_scada_trend":
        return get_scada_trend(asset_id)
    if name == "search_manuals":
        return search_manuals(asset_id, args.get("query", "maintenance troubleshooting"), top_k=4)
    if name == "search_work_orders":
        return search_asset_work_orders(asset_id, args.get("query", "maintenance troubleshooting"), top_k=4)
    raise ValueError(f"Unknown maintenance tool: {name}")


def run_llm_investigation(asset_id: str, question: str, model: str | None = None, max_rounds: int = 6):
    """Let an OpenAI model choose maintenance evidence tools, then answer from the evidence.

    The deterministic investigation still runs in parallel as a safety rail and provides
    ranked failure modes and structured findings used by the UI.
    """
    if not llm_available():
        result = run_investigation(asset_id, question)
        result["provider"] = "Deterministic fallback"
        result["llm_used"] = False
        return result

    from openai import OpenAI

    model = model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    client = OpenAI()
    tools = _tool_definitions()
    trace: list[ToolResult] = []
    tool_cache: dict[str, Any] = {}

    instructions = """You are a maintenance troubleshooting copilot for water and wastewater facilities.
Use the available tools to investigate the selected asset before diagnosing it. Prefer evidence from actual
operating trends, equipment guidance, and prior work orders. Do not invent readings, work orders, OEM limits,
or maintenance history. Distinguish observed evidence from plausible causes. Include a concise likely-cause
assessment, confidence, evidence, and a safe troubleshooting sequence. Never instruct a user to bypass lockout/
tagout, guards, interlocks, permits, confined-space requirements, or OEM/site safety procedures. You are decision
support, not an autonomous controller, and you cannot issue equipment commands."""

    input_items: list[Any] = [
        {
            "role": "user",
            "content": f"Selected asset ID: {asset_id}\nMaintenance question: {question}\nInvestigate before answering.",
        }
    ]

    response = None
    for _ in range(max_rounds):
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=input_items,
            tools=tools,
        )
        function_calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
        if not function_calls:
            break

        input_items.extend([item.to_dict() for item in response.output])
        for call in function_calls:
            args = json.loads(call.arguments or "{}")
            tool_result = _execute_tool(call.name, args, asset_id)
            trace.append(tool_result)
            tool_cache[call.name] = tool_result.data
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(_jsonable(tool_result.data), default=str),
                }
            )

    deterministic = run_investigation(asset_id, question)
    answer = (response.output_text if response is not None else "").strip()
    if not answer:
        answer = deterministic["answer"]

    # If the model skipped an evidence channel, the deterministic result keeps the UI complete
    # without pretending the LLM inspected something it did not.
    result = deterministic
    result["answer"] = answer
    result["trace"] = trace or deterministic["trace"]
    result["provider"] = f"OpenAI {model}"
    result["llm_used"] = True
    result["llm_tool_names"] = [step.tool for step in trace]
    return result


def run_copilot(asset_id: str, question: str, prefer_llm: bool = True):
    if prefer_llm and llm_available():
        try:
            return run_llm_investigation(asset_id, question)
        except Exception as exc:
            result = run_investigation(asset_id, question)
            result["provider"] = "Deterministic fallback"
            result["llm_used"] = False
            result["llm_error"] = str(exc)
            return result

    result = run_investigation(asset_id, question)
    result["provider"] = "Deterministic engine"
    result["llm_used"] = False
    return result
