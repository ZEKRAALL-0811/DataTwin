import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Tuple
from core.ai_engine import standardize_categories

logger = logging.getLogger(__name__)

def scan_data_issues(df: pd.DataFrame, meta: dict) -> dict:
    """Scans the DataFrame for common data quality issues.
    
    Args:
        df: The pandas DataFrame.
        meta: The metadata dict from data_loader.
        
    Returns:
        A dictionary of found issues.
    """
    issues = {
        "missing": [],           # List of dicts: {"column": str, "count": int}
        "duplicates": 0,         # Int: number of exact duplicate rows
        "inconsistent_cats": [], # List of columns that might have inconsistent categories
        "non_standard_dates": [] # List of columns with date-like data that might need standardizing
    }
    
    try:
        # 1. Missing Values
        missing_counts = df.isnull().sum()
        for col, count in missing_counts.items():
            if count > 0:
                issues["missing"].append({"column": col, "count": int(count)})
                
        # 2. Duplicate Rows
        issues["duplicates"] = int(df.duplicated().sum())
        
        # 3. Inconsistent Categories
        # Look at categorical columns with a moderate number of unique values
        cat_cols = meta.get("categorical_columns", [])
        for col in cat_cols:
            if col in df.columns:
                n_unique = df[col].nunique()
                if 2 < n_unique < 50:
                    # We flag it. The actual LLM standardization will decide if changes are needed.
                    issues["inconsistent_cats"].append(col)
                    
        # 4. Non-Standard Dates
        # Date columns identified by metadata or pandas inference
        date_cols = meta.get("datetime_columns", [])
        for col in date_cols:
            if col in df.columns:
                issues["non_standard_dates"].append(col)
                
    except Exception as exc:
        logger.warning("Error scanning data issues: %s", exc)
        
    return issues


def generate_path_to_100(df: pd.DataFrame, meta: dict, issues: dict) -> list:
    """Generates an action plan to improve the data health score."""
    path = []
    
    total_rows = len(df)
    total_cols = len(df.columns)
    total_cells = total_rows * total_cols
    
    if total_cells == 0:
        return []
        
    # 1. Missing values
    for missing_info in issues.get("missing", []):
        col = missing_info["column"]
        count = missing_info["count"]
        points = (count / total_cells * 100) / 3
        points = int(max(1, round(points)))
        if points > 0:
            path.append({
                "action": f"Fill {count:,} missing values in {col} column",
                "points_gained": points,
                "column": col,
                "type": "missing"
            })
            
    # 2. Duplicates
    duplicates = issues.get("duplicates", 0)
    if duplicates > 0:
        dup_pct = (duplicates / total_rows * 100)
        points = (dup_pct * 10) / 3
        points = int(max(1, round(points)))
        if points > 0:
            path.append({
                "action": f"Remove {duplicates:,} duplicate rows",
                "points_gained": points,
                "column": "All",
                "type": "duplicates"
            })
            
    # 3. Inconsistent Categories
    for col in issues.get("inconsistent_cats", []):
        points = int(max(1, round(15 / 3)))
        path.append({
            "action": f"Standardize formatting in {col} column",
            "points_gained": points,
            "column": col,
            "type": "inconsistent_cats"
        })
        
    # 4. Non-standard Dates
    for col in issues.get("non_standard_dates", []):
        points = 2
        path.append({
            "action": f"Standardize dates in {col} column",
            "points_gained": points,
            "column": col,
            "type": "non_standard_dates"
        })
        
    # Sort by points gained descending
    path.sort(key=lambda x: x["points_gained"], reverse=True)
    return path


def calculate_health_score(df: pd.DataFrame, meta: dict, issues: dict = None) -> dict:
    """Calculates data health sub-scores and overall score from 0-100.
    
    Args:
        df: The pandas DataFrame.
        meta: The metadata dict from data_loader.
        issues: (Optional) The issues dict returned by scan_data_issues.
                If None, scan_data_issues will be called.
                
    Returns:
        Dict with keys: 'overall', 'completeness', 'consistency', 'readiness'
    """
    if issues is None:
        issues = scan_data_issues(df, meta)
        
    total_rows = len(df)
    total_cols = len(df.columns)
    total_cells = total_rows * total_cols
    
    if total_cells == 0:
        return {"overall": 0, "completeness": 0, "consistency": 0, "readiness": 0}
        
    # 1. Completeness Score (100 - % missing)
    total_missing = sum(m["count"] for m in issues.get("missing", []))
    completeness = max(0, 100 - (total_missing / total_cells * 100))
    
    # 2. Consistency Score (100 - penalties)
    dup_pct = (issues.get("duplicates", 0) / total_rows * 100) if total_rows > 0 else 0
    inconsistent_cats_count = len(issues.get("inconsistent_cats", []))
    penalty = (dup_pct * 10) + (inconsistent_cats_count * 15)
    consistency = max(0, 100 - penalty)
    
    # 3. Readiness Score (% columns that are strictly typed, not unknown)
    num_cols = len(meta.get("numeric_columns", []))
    cat_cols = len(meta.get("categorical_columns", []))
    date_cols = len(meta.get("datetime_columns", []))
    typed_cols = num_cols + cat_cols + date_cols
    readiness = (typed_cols / total_cols * 100) if total_cols > 0 else 0
    
    # 4. Overall Score
    overall = (completeness + consistency + readiness) / 3
    
    res = {
        "overall": int(round(overall)),
        "completeness": int(round(completeness)),
        "consistency": int(round(consistency)),
        "readiness": int(round(readiness))
    }
    
    res["path_to_100"] = generate_path_to_100(df, meta, issues)
    return res


def clean_data(df: pd.DataFrame, issues: dict, meta: dict) -> Tuple[pd.DataFrame, str, list]:
    """Applies auto-cleaning operations to a COPY of the DataFrame.
    
    Args:
        df: The original pandas DataFrame.
        issues: The issues dict returned by scan_data_issues.
        meta: The metadata dict from data_loader.
        
    Returns:
        A tuple of (cleaned_df, report_markdown_string, audit_trail_list).
    """
    df_clean = df.copy()
    report_items = []
    audit_trail = []
    import datetime
    
    def log_audit(operation: str, desc: str, rows: int, cols: list, vals: str):
        audit_trail.append({
            "timestamp": datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
            "operation": operation,
            "description": desc,
            "rows_affected": rows,
            "columns_affected": cols,
            "values_changed": vals
        })
    
    # 1. Remove Duplicate Rows
    if issues.get("duplicates", 0) > 0:
        try:
            initial_len = len(df_clean)
            df_clean.drop_duplicates(inplace=True)
            removed = initial_len - len(df_clean)
            if removed > 0:
                report_items.append(f"Removed **{removed}** exact duplicate rows.")
                log_audit("Duplicate Removal", f"{removed} duplicate rows removed", removed, ["All"], "Exact matches removed")
        except Exception as exc:
            logger.warning("Failed to remove duplicates: %s", exc)
            
    # 2. Fill Missing Values
    if issues.get("missing"):
        try:
            filled_count = 0
            cols_filled = 0
            num_cols = meta.get("numeric_columns", [])
            
            for missing_info in issues["missing"]:
                col = missing_info["column"]
                if col in df_clean.columns:
                    missing_mask = df_clean[col].isnull()
                    count = missing_mask.sum()
                    if count > 0:
                        if col in num_cols:
                            fill_val = df_clean[col].median()
                            fill_desc = f"median value {fill_val:.2f}" if isinstance(fill_val, float) else f"median value {fill_val}"
                        else:
                            mode_series = df_clean[col].mode()
                            fill_val = mode_series.iloc[0] if not mode_series.empty else "Unknown"
                            fill_desc = f"mode '{fill_val}'"
                            
                        df_clean.loc[missing_mask, col] = fill_val
                        filled_count += count
                        cols_filled += 1
                        
                        log_audit("Impute Missing", f"{count} null values filled in {col} → {fill_desc}", count, [col], f"NaN → {fill_val}")
                        
            if filled_count > 0:
                report_items.append(f"Filled **{filled_count}** missing values across **{cols_filled}** columns.")
        except Exception as exc:
            logger.warning("Failed to fill missing values: %s", exc)
            
    # 3. Standardize Categories (using LLM)
    if issues.get("inconsistent_cats"):
        try:
            standardized_count = 0
            for col in issues["inconsistent_cats"]:
                if col in df_clean.columns:
                    unique_vals = [str(v) for v in df_clean[col].dropna().unique()]
                    if 2 < len(unique_vals) < 50:
                        mapping = standardize_categories(col, unique_vals)
                        if mapping:
                            original_values = df_clean[col].copy()
                            str_series = df_clean[col].astype(str)
                            df_clean[col] = str_series.replace(mapping)
                            
                            changed = (original_values.astype(str) != df_clean[col].astype(str)).sum()
                            if changed > 0:
                                standardized_count += changed
                                # Format sample changes
                                changes_str = ", ".join([f'"{k}"→"{v}"' for k, v in list(mapping.items())[:3]])
                                if len(mapping) > 3: changes_str += "..."
                                log_audit("Standardize Categories", f"AI fixed {len(mapping)} category variants in {col}", changed, [col], changes_str)
                                
            if standardized_count > 0:
                report_items.append(f"Standardized **{standardized_count}** categorical inconsistencies.")
        except Exception as exc:
            logger.warning("Failed to standardize categories: %s", exc)
            
    # 4. Standardize Dates
    if issues.get("non_standard_dates"):
        try:
            dates_fixed = 0
            for col in issues["non_standard_dates"]:
                if col in df_clean.columns:
                    parsed = pd.to_datetime(df_clean[col], errors='coerce')
                    # count successful parses that changed format
                    # rough heuristic
                    changed = len(df_clean[col].dropna())
                    df_clean[col] = parsed.dt.strftime('%Y-%m-%d')
                    dates_fixed += 1
                    log_audit("Standardize Dates", f"Date formats standardized in {col} → YYYY-MM-DD", changed, [col], "mixed formats → YYYY-MM-DD")
                    
            if dates_fixed > 0:
                report_items.append(f"Standardized **{dates_fixed}** date columns to YYYY-MM-DD format.")
        except Exception as exc:
            logger.warning("Failed to standardize dates: %s", exc)

    if not report_items:
        report_md = "Data was already clean, no changes were needed!"
    else:
        report_md = "\n".join([f"- ✅ {item}" for item in report_items])
        
    return df_clean, report_md, audit_trail
