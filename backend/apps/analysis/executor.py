"""Bridges provider tool calls to the deterministic analysis tools, producing UI artifacts and an audit log."""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

from apps.providers.base import ToolActivity

from .tools import ToolContext, ToolError, run_tool

logger = logging.getLogger(__name__)


def _summary(name: str, result: dict) -> str:
    if name == "list_datasets":
        return f"{len(result['datasets'])} dataset(s)"
    if name == "describe_dataset":
        return f"{result['title']} · {result['rows']:,} rows · {len(result['columns'])} columns"
    if name == "query_dataset":
        return f"{result['result_rows']:,} result row(s) from {result['rows_matching_filters']:,} matching"
    if name == "create_chart":
        return f"{result['chart_type']} chart · {result['points']} points"
    if name == "calculate":
        return f"{result['expression']} = {result['result']}"
    return ""


def _artifact(name: str, result: dict) -> dict | None:
    if name == "query_dataset":
        return {"type": "table", "result_id": result["result_id"], "title": result["title"],
                "columns": result["columns"], "rows": result["rows"], "total_rows": result["result_rows"]}
    if name == "create_chart":
        return {"type": "chart", **result}
    return None


class AnalysisExecutor:
    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self.calls: list[dict[str, Any]] = []
        self.artifacts: list[dict] = []

    async def __call__(self, call_id: str, name: str, args: dict) -> tuple[dict, ToolActivity]:
        try:
            result = await sync_to_async(run_tool)(self.ctx, name, args)
        except ToolError as e:
            logger.info("tool %s rejected: %s", name, e)
            self.calls.append({"id": call_id, "name": name, "args": args, "status": "error", "summary": str(e)})
            return {"error": str(e)}, ToolActivity(call_id, name, "error", args, str(e))
        summary = _summary(name, result)
        artifact = _artifact(name, result)
        if artifact:
            self.artifacts.append(artifact)
        self.calls.append({"id": call_id, "name": name, "args": args, "status": "done", "summary": summary})
        logger.info("tool %s ok: %s", name, summary)
        return result, ToolActivity(call_id, name, "done", args, summary, artifact)
