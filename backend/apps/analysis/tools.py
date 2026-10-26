"""Deterministic data-analysis tools the model can call.

The model chooses *what* to compute; the server computes it with pandas. Arguments are untrusted model output
and are validated here; no model-written code is ever executed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from django.conf import settings

from apps.documents.extract import ExtractionError
from apps.documents.models import Document
from apps.providers.base import ToolSpec

from .calculator import CalcError, evaluate
from .datasets import DATASET_KINDS, load
from .models import AnalysisResult

FILTER_OPS = ["==", "!=", ">", ">=", "<", "<=", "contains", "in", "is_null", "not_null"]
AGG_FUNCS = ["count", "sum", "mean", "median", "min", "max", "nunique", "std"]
# No pie charts: they are poor for comparing values. Scatter is capped at 3 series (palette limit).
CHART_TYPES = ["bar", "line", "scatter"]
MAX_RETURN_ROWS = 50


class ToolError(Exception):
    """A user/model-facing reason a tool call could not be completed."""


@dataclass
class ToolContext:
    user: Any
    conversation: Any
    datasets: list[Document]


# ----------------------------------------------------------------------------- tool specifications

DATASET_ID = {"type": "integer", "description": "dataset_id from list_datasets"}
SHEET = {"type": "string", "description": "Sheet name (XLSX). Omit for CSV or to use the first sheet."}

SPECS = [
    ToolSpec(
        "list_datasets",
        "List the datasets (CSV/Excel files) attached to this conversation, with their sheets, row counts and "
        "columns. Call this first.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        "describe_dataset",
        "Profile one dataset sheet: column types, missing values, unique counts, numeric statistics (min, max, "
        "mean, median, std, sum), most common values, date ranges, and a few sample rows.",
        {"type": "object", "properties": {"dataset_id": DATASET_ID, "sheet": SHEET},
         "required": ["dataset_id"], "additionalProperties": False},
    ),
    ToolSpec(
        "query_dataset",
        "Filter, group, aggregate and sort a dataset sheet. Use this for every number you report. Returns up to "
        f"{MAX_RETURN_ROWS} rows plus the total number of matching rows, and a result_id usable with create_chart.",
        {
            "type": "object",
            "properties": {
                "dataset_id": DATASET_ID,
                "sheet": SHEET,
                "title": {"type": "string", "description": "Short human-readable title for this result."},
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "op": {"type": "string", "enum": FILTER_OPS},
                            "value": {"description": "Comparison value; a list for 'in'; omit for null checks."},
                        },
                        "required": ["column", "op"],
                    },
                },
                "group_by": {"type": "array", "items": {"type": "string"}},
                "aggregations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "func": {"type": "string", "enum": AGG_FUNCS},
                            "column": {"type": "string", "description": "Omit only for count of rows."},
                        },
                        "required": ["func"],
                    },
                },
                "select": {"type": "array", "items": {"type": "string"},
                           "description": "Columns to return when not aggregating."},
                "sort": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"column": {"type": "string"},
                                                               "descending": {"type": "boolean"}},
                              "required": ["column"]},
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_RETURN_ROWS},
            },
            "required": ["dataset_id"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        "create_chart",
        "Create a chart from a query_dataset result. x is the category/time column; y lists numeric columns.",
        {
            "type": "object",
            "properties": {
                "result_id": {"type": "integer"},
                "chart_type": {"type": "string", "enum": CHART_TYPES},
                "x": {"type": "string"},
                "y": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                "title": {"type": "string"},
            },
            "required": ["result_id", "chart_type", "x", "y"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        "calculate",
        "Evaluate an arithmetic expression exactly (e.g. percentage change). Supports + - * / ** %, parentheses, "
        "abs, round, sqrt, log, log10, exp, min, max, ceil, floor.",
        {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"],
         "additionalProperties": False},
    ),
]


# ----------------------------------------------------------------------------- helpers

def to_json(value: Any) -> Any:
    """Converts pandas/numpy values to JSON-safe Python values (NaN → None, timestamps → ISO strings)."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else round(value, 6)
    if isinstance(value, pd.Timestamp | datetime | date):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    return value


def _as_int(args: dict, key: str, required: bool = True) -> int | None:
    value = args.get(key)
    if value is None and not required:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ToolError(f"'{key}' must be an integer.")
    return value


def _as_list(args: dict, key: str) -> list:
    value = args.get(key) or []
    if not isinstance(value, list):
        raise ToolError(f"'{key}' must be a list.")
    return value


def _dataset(ctx: ToolContext, args: dict) -> tuple[Document, str, pd.DataFrame]:
    dataset_id = _as_int(args, "dataset_id")
    document = next((d for d in ctx.datasets if d.pk == dataset_id), None)
    if document is None:
        raise ToolError(f"No dataset with id {dataset_id} is attached to this conversation.")
    try:
        sheets = load(document)
    except ExtractionError as e:
        raise ToolError(str(e)) from e
    sheet = args.get("sheet")
    if sheet is None:
        sheet = next(iter(sheets))
    if sheet not in sheets:
        raise ToolError(f"Sheet '{sheet}' not found. Available sheets: {', '.join(sheets)}.")
    return document, sheet, sheets[sheet]


def _column(df: pd.DataFrame, name: Any) -> str:
    if not isinstance(name, str):
        raise ToolError("Column names must be strings.")
    if name in df.columns:
        return name
    folded = {c.lower(): c for c in df.columns}
    if name.lower() in folded:
        return folded[name.lower()]
    raise ToolError(f"Unknown column '{name}'. Columns: {', '.join(map(str, df.columns))}.")


def _coerce(series: pd.Series, value: Any) -> Any:
    try:
        if pd.api.types.is_datetime64_any_dtype(series):
            return pd.to_datetime(value)
        if pd.api.types.is_numeric_dtype(series) and not isinstance(value, bool):
            return float(value)
    except (TypeError, ValueError) as e:
        raise ToolError(f"Value {value!r} does not match the type of column '{series.name}'.") from e
    return value


def _apply_filter(df: pd.DataFrame, f: Any) -> pd.DataFrame:
    if not isinstance(f, dict):
        raise ToolError("Each filter must be an object with 'column' and 'op'.")
    column = _column(df, f.get("column"))
    op = f.get("op")
    if op not in FILTER_OPS:
        raise ToolError(f"Unsupported filter op '{op}'. Use one of: {', '.join(FILTER_OPS)}.")
    s = df[column]
    if op == "is_null":
        return df[s.isna()]
    if op == "not_null":
        return df[s.notna()]
    if "value" not in f:
        raise ToolError(f"Filter on '{column}' with op '{op}' needs a value.")
    value = f["value"]
    if op == "contains":
        return df[s.astype(str).str.contains(str(value), case=False, regex=False, na=False)]
    if op == "in":
        if not isinstance(value, list):
            raise ToolError("The 'in' operator needs a list value.")
        return df[s.isin([_coerce(s, v) for v in value])]
    value = _coerce(s, value)
    try:
        mask = {"==": s == value, "!=": s != value, ">": s > value, ">=": s >= value, "<": s < value,
                "<=": s <= value}[op]
    except TypeError as e:
        raise ToolError(f"Cannot compare column '{column}' with {value!r} using '{op}'.") from e
    return df[mask]


def _table(df: pd.DataFrame, limit: int) -> tuple[list[str], list[list]]:
    head = df.head(limit)
    return [str(c) for c in head.columns], [[to_json(v) for v in row] for row in head.itertuples(index=False)]


# ----------------------------------------------------------------------------- tools

def list_datasets(ctx: ToolContext, args: dict) -> dict:
    out = []
    for document in ctx.datasets:
        try:
            sheets = load(document)
        except ExtractionError as e:
            out.append({"dataset_id": document.pk, "title": document.title, "error": str(e)})
            continue
        out.append({
            "dataset_id": document.pk,
            "title": document.title,
            "sheets": [
                {
                    "sheet": name,
                    "rows": len(df),
                    "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
                }
                for name, df in sheets.items()
            ],
        })
    return {"datasets": out}


def describe_dataset(ctx: ToolContext, args: dict) -> dict:
    document, sheet, df = _dataset(ctx, args)
    columns = []
    for c in df.columns:
        s = df[c]
        info: dict[str, Any] = {"name": c, "dtype": str(s.dtype), "missing": int(s.isna().sum()),
                                "unique": int(s.nunique(dropna=True))}
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            info.update({k: to_json(v) for k, v in {"min": s.min(), "max": s.max(), "mean": s.mean(),
                                                     "median": s.median(), "std": s.std(), "sum": s.sum()}.items()})
        elif pd.api.types.is_datetime64_any_dtype(s):
            info.update({"min": to_json(s.min()), "max": to_json(s.max())})
        else:
            top = s.astype(str)[s.notna()].value_counts().head(5)
            info["top_values"] = [{"value": k, "count": int(v)} for k, v in top.items()]
        columns.append(info)
    cols, sample = _table(df, 5)
    return {"dataset_id": document.pk, "title": document.title, "sheet": sheet, "rows": len(df), "columns": columns,
            "sample_columns": cols, "sample_rows": sample}


def query_dataset(ctx: ToolContext, args: dict) -> dict:
    document, sheet, df = _dataset(ctx, args)
    query: dict[str, Any] = {"dataset_id": document.pk, "sheet": sheet}
    for f in _as_list(args, "filters"):
        df = _apply_filter(df, f)
    query["filters"] = _as_list(args, "filters")
    matched = len(df)

    group_by = [_column(df, c) for c in _as_list(args, "group_by")]
    aggregations = _as_list(args, "aggregations")
    if group_by and not aggregations:
        aggregations = [{"func": "count"}]
    if aggregations:
        named: dict[str, tuple[str, str]] = {}
        for agg in aggregations:
            if not isinstance(agg, dict) or agg.get("func") not in AGG_FUNCS:
                raise ToolError(f"Each aggregation needs 'func' from: {', '.join(AGG_FUNCS)}.")
            func, column = agg["func"], agg.get("column")
            if column is None:
                if func != "count":
                    raise ToolError(f"Aggregation '{func}' needs a column.")
                named["count"] = (df.columns[0], "size")
                continue
            column = _column(df, column)
            if func in ("sum", "mean", "median", "std") and not pd.api.types.is_numeric_dtype(df[column]):
                raise ToolError(f"Cannot compute {func} of non-numeric column '{column}'.")
            named[f"{func}({column})"] = (column, func)
        if group_by:
            result = df.groupby(group_by, dropna=False).agg(**named).reset_index()
        else:
            result = pd.DataFrame([{name: (len(df) if how == "size" else getattr(df[col], how)())
                                    for name, (col, how) in named.items()}])
        query.update(group_by=group_by, aggregations=aggregations)
    else:
        select = [_column(df, c) for c in _as_list(args, "select")]
        result = df[select] if select else df
        query["select"] = select

    sort = _as_list(args, "sort")
    if sort:
        keys, ascending = [], []
        for item in sort:
            if not isinstance(item, dict):
                raise ToolError("Each sort item must be an object with 'column'.")
            name = item.get("column")
            # Accept the source column name for an aggregate (e.g. "revenue" → "sum(revenue)") when unambiguous.
            suffix = f"({name.lower()})" if isinstance(name, str) else None
            matches = [c for c in result.columns if suffix and str(c).lower().endswith(suffix)]
            keys.append(matches[0] if name not in result.columns and len(matches) == 1 else _column(result, name))
            ascending.append(not bool(item.get("descending")))
        result = result.sort_values(keys, ascending=ascending, kind="stable")
        query["sort"] = sort

    limit = _as_int(args, "limit", required=False) or 20
    limit = max(1, min(limit, MAX_RETURN_ROWS))
    title = str(args.get("title") or f"Query on {document.title}")[:200]
    columns, all_rows = _table(result, settings.ANALYSIS_RESULT_MAX_ROWS)
    stored = AnalysisResult.objects.create(
        user=ctx.user, conversation=ctx.conversation, document=document, title=title, query=query,
        columns=columns, rows=all_rows, total_rows=len(result),
    )
    return {
        "result_id": stored.pk,
        "title": title,
        "rows_matching_filters": matched,
        "result_rows": len(result),
        "returned_rows": min(limit, len(result)),
        "columns": columns,
        "rows": all_rows[:limit],
    }


def create_chart(ctx: ToolContext, args: dict) -> dict:
    result_id = _as_int(args, "result_id")
    stored = AnalysisResult.objects.filter(pk=result_id, user=ctx.user, conversation=ctx.conversation).first()
    if stored is None:
        raise ToolError(f"No result with id {result_id} in this conversation. Run query_dataset first.")
    chart_type = args.get("chart_type")
    if chart_type not in CHART_TYPES:
        raise ToolError(f"chart_type must be one of: {', '.join(CHART_TYPES)}.")
    if args.get("x") not in stored.columns:
        raise ToolError(f"Unknown x column. Result columns: {', '.join(stored.columns)}.")
    y = _as_list(args, "y")
    if not y or len(y) > 4 or any(c not in stored.columns for c in y):
        raise ToolError(f"y must list 1–4 result columns from: {', '.join(stored.columns)}.")
    if chart_type == "scatter" and len(y) > 3:
        raise ToolError("A scatter chart takes at most 3 y columns.")
    xi = stored.columns.index(args["x"])
    yi = [stored.columns.index(c) for c in y]
    rows = stored.rows[: settings.ANALYSIS_CHART_MAX_POINTS]
    for i in yi:
        if any(r[i] is not None and not isinstance(r[i], int | float) for r in rows):
            raise ToolError(f"Column '{stored.columns[i]}' is not numeric and cannot be plotted on the y axis.")
    data = [{"x": r[xi], **{stored.columns[i]: r[i] for i in yi}} for r in rows]
    title = str(args.get("title") or stored.title)[:200]
    return {"chart_type": chart_type, "title": title, "x": args["x"], "y": y, "points": len(data),
            "truncated": stored.total_rows > len(rows), "data": data}


def calculate(ctx: ToolContext, args: dict) -> dict:
    expression = args.get("expression")
    if not isinstance(expression, str):
        raise ToolError("'expression' must be a string.")
    try:
        value = evaluate(expression)
    except CalcError as e:
        raise ToolError(str(e)) from e
    return {"expression": expression, "result": to_json(value)}


REGISTRY = {
    "list_datasets": list_datasets,
    "describe_dataset": describe_dataset,
    "query_dataset": query_dataset,
    "create_chart": create_chart,
    "calculate": calculate,
}


def datasets_for(conversation, user) -> list[Document]:
    return list(
        conversation.documents.filter(user=user, kind__in=DATASET_KINDS, status=Document.Status.READY).order_by("pk")
    )


def run_tool(ctx: ToolContext, name: str, args: dict) -> dict:
    func = REGISTRY.get(name)
    if func is None:
        raise ToolError(f"Unknown tool '{name}'.")
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be an object.")
    return func(ctx, args)


INSTRUCTIONS = """
Datasets (CSV/Excel) are attached to this conversation and can be analysed with tools.
- Use the tools for every number, count, total, average, ranking or comparison about the data. Never estimate or \
compute figures yourself, and report numbers exactly as the tools return them.
- Start with list_datasets, then describe_dataset or query_dataset. Say which filters or groupings you used.
- Use create_chart when a chart would make a comparison or trend clearer.
- If a tool returns an error, fix the arguments (for example a column name) or explain the limitation."""
