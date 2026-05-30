import csv
import io
import logging
import re
import urllib.request
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
_SHEET_ID_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
logger = logging.getLogger(__name__)


class InvalidSheetURL(ValueError):
    """Raised when the provided URL is not a valid Google Sheets URL."""


class SheetFetchError(RuntimeError):
    """Raised when the Google Sheet cannot be fetched (private, network error, etc.)."""


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
            df = _read_csv_with_encoding_fallback(file_bytes, delimiter)
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


def load_google_sheet(sheet_url: str) -> pd.DataFrame:
    """Fetch a public Google Sheet as CSV and load it into session state.

    Args:
        sheet_url: A Google Sheets URL (e.g. https://docs.google.com/spreadsheets/d/SHEET_ID/edit).

    Returns:
        The cleaned DataFrame.

    Raises:
        InvalidSheetURL: If the URL doesn't match Google Sheets pattern.
        SheetFetchError: If the sheet cannot be fetched.
    """
    if not sheet_url or not sheet_url.strip():
        raise InvalidSheetURL("No URL provided.")

    match = _SHEET_ID_PATTERN.search(sheet_url.strip())
    if not match:
        raise InvalidSheetURL("Not a valid Google Sheets URL.")

    sheet_id = match.group(1)
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    try:
        req = urllib.request.Request(export_url, headers={"User-Agent": "DataTwin/1.0"})
        response = urllib.request.urlopen(req, timeout=20)
        csv_bytes = response.read()
    except Exception as exc:
        logger.exception("Failed to fetch Google Sheet: %s", sheet_id)
        raise SheetFetchError("Could not fetch the Google Sheet.") from exc

    if not csv_bytes or len(csv_bytes) < 10:
        raise SheetFetchError("The Google Sheet appears to be empty.")

    try:
        delimiter = _detect_csv_delimiter(csv_bytes)
        df = _read_csv_with_encoding_fallback(csv_bytes, delimiter)
    except Exception as exc:
        raise SheetFetchError("Could not parse the Google Sheet data.") from exc

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

    sensitive_keywords = ['email', 'phone', 'password', 'ssn', 'id', 'address', 'dob']
    sensitive_columns = [col for col in df.columns if any(kw in str(col).lower() for kw in sensitive_keywords)]
    
    sample_records = df.head(3).to_dict(orient="records")
    for record in sample_records:
        for col in sensitive_columns:
            if pd.notna(record.get(col)):
                record[col] = "••••••••"

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
        "sensitive_columns": sensitive_columns,
        "sample": sample_records,
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


def _read_csv_with_encoding_fallback(file_bytes: bytes, delimiter: str) -> pd.DataFrame:
    """Try reading CSV bytes with multiple encodings, returning the first that succeeds."""
    encodings = ("utf-8", "utf-8-sig", "latin-1", "cp1252")
    last_exc = None
    for encoding in encodings:
        try:
            return pd.read_csv(
                io.BytesIO(file_bytes),
                sep=delimiter,
                engine="python",
                encoding=encoding,
            )
        except (UnicodeDecodeError, Exception) as exc:
            last_exc = exc
            continue
    raise ValueError("Could not decode CSV with any supported encoding.") from last_exc


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
