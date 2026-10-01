import re

import pandas as pd

NUMERIC_STRIP = re.compile(r"[,\s%$€£₹]")
# Columns named like these hold codes, not quantities, so they are never flagged as "numbers as text"
NON_NUMERIC_NAME_TOKENS = {
    "id", "code", "key", "zip", "pin", "pincode", "postal", "phone", "mobile", "number", "no", "sku",
}


def dtype_label(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_integer_dtype(s):
        return "int64"
    if pd.api.types.is_float_dtype(s):
        return "float64"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    return "string"


def _samples(non_null: pd.Series, n: int = 5) -> list[str]:
    # Only a handful of distinct values per column ever leave the profile
    return [str(v)[:40] for v in non_null.drop_duplicates().head(n).tolist()]


def _looks_numeric(name: str, non_null: pd.Series) -> bool:
    """True for text columns such as '₹1,299.00' or '12%' that would be numbers without the symbols."""
    if set(name.lower().split("_")) & NON_NUMERIC_NAME_TOKENS or non_null.empty:
        return False
    sample = non_null.head(200).astype(str).str.replace(NUMERIC_STRIP, "", regex=True)
    parsed = pd.to_numeric(sample, errors="coerce")
    return bool(len(sample)) and float(parsed.notna().mean()) >= 0.95


def profile_dataframe(df: pd.DataFrame, table_name: str) -> dict:
    total = len(df)
    try:
        duplicates = int(df.duplicated().sum())
    except Exception:  # noqa: BLE001
        duplicates = 0

    columns = []
    for name in df.columns:
        series = df[name]
        non_null = series.dropna()
        dtype = dtype_label(series)

        col: dict = {
            "name": name,
            "dtype": dtype,
            "nullPct": round(100 * (total - len(non_null)) / total, 2) if total else 0.0,
            "distinct": int(non_null.nunique()),
            "samples": _samples(non_null),
        }
        if not non_null.empty:
            if dtype in ("int64", "float64"):
                col["min"] = float(non_null.min())
                col["max"] = float(non_null.max())
                col["mean"] = float(non_null.mean())
            elif dtype == "datetime":
                col["min"] = non_null.min().isoformat()
                col["max"] = non_null.max().isoformat()
            elif dtype == "string" and _looks_numeric(str(name), non_null):
                col["numericLike"] = True
        columns.append(col)

    return {"table": table_name, "rows": total, "duplicateRows": duplicates, "columns": columns}