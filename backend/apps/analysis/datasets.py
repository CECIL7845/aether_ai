"""Loads CSV/XLSX documents into pandas DataFrames for deterministic analysis."""

from __future__ import annotations

import io
import warnings
from collections import OrderedDict
from threading import Lock

import pandas as pd
from django.conf import settings

from apps.documents.extract import ExtractionError, _check_zip, _decode
from apps.documents.models import Document

DATASET_KINDS = (Document.Kind.CSV, Document.Kind.XLSX)

_cache: OrderedDict[tuple[int, str], dict[str, pd.DataFrame]] = OrderedDict()
_lock = Lock()
CACHE_SIZE = 16


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    seen: dict[str, int] = {}
    names = []
    for i, col in enumerate(df.columns):
        name = " ".join(str(col).split()) or f"column_{i + 1}"
        if name.lower().startswith("unnamed:"):
            name = f"column_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        names.append(name)
    df.columns = names
    return df


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        # pandas 3 stores text as the "str" dtype; older data may still be "object".
        if pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
            sample = df[col].dropna().astype(str).head(50)
            if len(sample) >= 3 and sample.str.contains(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}").mean() > 0.9:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    parsed = pd.to_datetime(df[col], errors="coerce", format="mixed")
                if parsed.notna().mean() >= 0.9:
                    df[col] = parsed
    return df


def load(document: Document) -> dict[str, pd.DataFrame]:
    """Sheet name → DataFrame. CSV files have a single sheet named after the file."""
    key = (document.pk, document.sha256)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    with document.file.open("rb") as f:
        data = f.read()
    limit = settings.MAX_SPREADSHEET_ROWS
    try:
        if document.kind == Document.Kind.CSV:
            frames = {"data": pd.read_csv(io.StringIO(_decode(data)), sep=None, engine="python", nrows=limit + 1)}
        else:
            _check_zip(data)
            frames = pd.read_excel(io.BytesIO(data), sheet_name=None, engine="openpyxl", nrows=limit + 1)
    except ExtractionError:
        raise
    except Exception as e:  # pandas raises many parser-specific errors
        raise ExtractionError("This spreadsheet could not be read as a table.") from e
    cleaned = {}
    for name, df in frames.items():
        if len(df) > limit:
            raise ExtractionError(f"Sheet '{name}' has more than {limit:,} rows.")
        cleaned[str(name)] = _parse_dates(_clean_columns(df.dropna(how="all").reset_index(drop=True)))
    with _lock:
        _cache[key] = cleaned
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return cleaned
