import csv
import io
import logging
import warnings
from pathlib import Path

import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_numeric_dtype,
)

try:
    import streamlit as st
    from streamlit.runtime.scriptrunner import get_script_run_ctx
except ImportError:  # Allows this module to be tested before dependencies are installed.
    st = None
    get_script_run_ctx = None


SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
DATETIME_PARSE_THRESHOLD = 0.8
logger = logging.getLogger(__name__)


def load_file(uploaded_file) -> pd.DataFrame:
    """Read an uploaded CSV or Excel file, clean it, and store it in session state."""
    if uploaded_file is None:
        raise ValueError("No file was uploaded.")

    file_name = getattr(uploaded_file, "name", "")
    extension = Path(file_name).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Unsupported file format. Please upload CSV or Excel.")

    file_bytes = _read_uploaded_file(uploaded_file)

    try:
        if extension == ".csv":
            delimiter = _detect_csv_delimiter(file_bytes)
            df = pd.read_csv(io.BytesIO(file_bytes), sep=delimiter, engine="python")
        else:
            df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ValueError("Could not read the uploaded file.") from exc

    df = clean_dataframe(df)
    metadata = get_metadata(df)

    if _is_streamlit_runtime():
        st.session_state["df"] = df
        st.session_state["df_meta"] = metadata

    return df


def get_metadata(df: pd.DataFrame) -> dict:
    """Return shape, column, type, missing-value, and sample metadata for a DataFrame."""
    datetime_columns = detect_datetime_columns(df)
    numeric_columns = [
        col for col in df.columns if is_numeric_dtype(df[col]) and not is_bool_dtype(df[col])
    ]
    categorical_columns = [
        col
        for col in df.columns
        if col not in datetime_columns
        and col not in numeric_columns
        and not is_bool_dtype(df[col])
    ]

    missing_counts = df.isna().sum()
    row_count = len(df)

    return {
        "rows": int(row_count),
        "columns": int(len(df.columns)),
        "shape": tuple(df.shape),
        "column_names": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "column_types": {col: _get_column_type(df[col], datetime_columns) for col in df.columns},
        "missing_values": {col: int(count) for col, count in missing_counts.items()},
        "missing_percentages": {
            col: float(round((count / row_count) * 100, 2)) if row_count else 0.0
            for col, count in missing_counts.items()
        },
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "datetime_columns": datetime_columns,
        "sample": df.head(3).to_dict(orient="records"),
    }


def detect_datetime_columns(df: pd.DataFrame) -> list:
    """Detect columns that are already datetime-like or mostly parseable as datetimes."""
    datetime_columns = []

    for column in df.columns:
        series = df[column]

        if is_datetime64_any_dtype(series):
            datetime_columns.append(column)
            continue

        if is_numeric_dtype(series) or is_bool_dtype(series):
            continue

        non_null = series.dropna()
        if non_null.empty:
            continue

        parsed = _parse_datetime(non_null)
        parse_rate = parsed.notna().mean()
        if parse_rate >= DATETIME_PARSE_THRESHOLD:
            datetime_columns.append(column)

    return datetime_columns


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names, remove empty rows/columns, trim strings, and parse dates."""
    cleaned = df.copy()
    cleaned.columns = _dedupe_columns([str(column).strip() for column in cleaned.columns])
    cleaned = cleaned.dropna(axis=0, how="all").dropna(axis=1, how="all")
    cleaned = cleaned.replace(r"^\s*$", pd.NA, regex=True)

    for column in cleaned.columns:
        if cleaned[column].dtype == "object":
            cleaned[column] = cleaned[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )

    datetime_columns = detect_datetime_columns(cleaned)
    for column in datetime_columns:
        cleaned[column] = _parse_datetime(cleaned[column])

    return cleaned


def _read_uploaded_file(uploaded_file) -> bytes:
    if hasattr(uploaded_file, "getvalue"):
        return uploaded_file.getvalue()

    current_position = None
    if hasattr(uploaded_file, "tell") and hasattr(uploaded_file, "seek"):
        current_position = uploaded_file.tell()
        uploaded_file.seek(0)

    file_bytes = uploaded_file.read()

    if current_position is not None:
        uploaded_file.seek(current_position)

    if isinstance(file_bytes, str):
        return file_bytes.encode("utf-8")

    return file_bytes


def _detect_csv_delimiter(file_bytes: bytes) -> str:
    sample = _decode_bytes(file_bytes[:8192])

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
        return dialect.delimiter
    except csv.Error:
        return ","


def _decode_bytes(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "utf-8",
        file_bytes,
        0,
        len(file_bytes),
        "Could not decode file with supported encodings.",
    )


def _parse_datetime(series: pd.Series) -> pd.Series:
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("ignore", UserWarning)
        parsed = pd.to_datetime(series, errors="coerce", format=None)

    for warning in caught_warnings:
        logger.debug(
            "Suppressed datetime parsing warning for column %s: %s",
            getattr(series, "name", "<unknown>"),
            warning.message,
        )

    return parsed


def _is_streamlit_runtime() -> bool:
    return (
        st is not None
        and get_script_run_ctx is not None
        and get_script_run_ctx(suppress_warning=True) is not None
    )


def _dedupe_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    deduped = []

    for index, column in enumerate(columns):
        base_name = column or f"column_{index + 1}"
        count = seen.get(base_name, 0)
        deduped.append(base_name if count == 0 else f"{base_name}_{count + 1}")
        seen[base_name] = count + 1

    return deduped


def _get_column_type(series: pd.Series, datetime_columns: list[str]) -> str:
    if series.name in datetime_columns or is_datetime64_any_dtype(series):
        return "datetime"
    if is_bool_dtype(series):
        return "boolean"
    if is_numeric_dtype(series):
        return "numeric"
    return "categorical"
