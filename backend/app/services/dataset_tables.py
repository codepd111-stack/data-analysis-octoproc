from app.models.dataset import Dataset


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