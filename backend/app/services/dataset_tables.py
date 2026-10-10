from pathlib import Path

from app.models.dataset import Dataset
from app.services.storage import get_storage


def get_table_profiles(ds: Dataset) -> list[dict]:
    """
    Returns one profile dict per table. Handles both shapes:
      new: profile = {"tables": [ {...}, {...} ]}
      old: profile = {"table": ..., "rows": ..., "columns": [...]}  (single-table, pre step 5)
    """
    profile = ds.profile or {}
    if profile.get("tables"):
        return profile["tables"]
    if profile.get("columns") and ds.table_name:
        legacy = dict(profile)
        legacy["parquetKey"] = ds.parquet_key
        return [legacy]
    return []


def get_table_paths(ds: Dataset, wanted: set[str] | None = None) -> dict[str, Path]:
    """
    Local Parquet file per table (fetched from S3 when needed). Tables whose file cannot be
    found are left out, so callers can tell the user the data is missing instead of crashing.
    """
    storage = get_storage()
    paths: dict[str, Path] = {}
    for prof in get_table_profiles(ds):
        name, key = prof.get("table"), prof.get("parquetKey")
        if not name or not key or (wanted is not None and name not in wanted):
            continue
        try:
            path = storage.get_local_path(key)
        except FileNotFoundError:
            continue
        if path.exists():
            paths[name] = path
    return paths
