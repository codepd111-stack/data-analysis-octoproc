import io
import logging
import re
import warnings
from datetime import timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.utils import utcnow
from app.models.dataset import Dataset
from app.services.profiling import profile_dataframe
from app.services.semantic_generator import build_baseline_layer, enrich_layer
from app.services.semantic_store import save_layer
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet"}
DATE_HINTS = ("date", "time", "_at", "timestamp", "dob")
MAX_TABLES = 20

INTERRUPTED_ERROR = (
    "Processing was interrupted by a server restart before it finished. Use Retry to run it again."
)
# A healthy pipeline bumps updated_at at every stage; nothing legitimately stays silent this long
STALE_AFTER = timedelta(minutes=15)


def load_tables(path: Path) -> list[tuple[str, pd.DataFrame]]:
    """One (label, dataframe) per CSV/Parquet file, or per sheet for Excel. Empty sheets are skipped."""
    suffix = path.suffix.lower()
    stem = path.stem

    if suffix == ".csv":
        try:
            df = pd.read_csv(path)
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="latin-1")
        return [(stem, df)]

    if suffix in {".xlsx", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None)
        usable = {n: d for n, d in sheets.items() if not d.empty and len(d.columns) > 0}
        if len(usable) == 1:
            return [(stem, next(iter(usable.values())))]
        return [(f"{stem}_{name}", df) for name, df in usable.items()]

    if suffix == ".parquet":
        return [(stem, pd.read_parquet(path))]

    raise ValueError(f"Unsupported file type: {suffix}")


def clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """snake_case, unique column names, so generated SQL is always valid."""
    seen: dict[str, int] = {}
    names = []
    for i, col in enumerate(df.columns):
        base = re.sub(r"\W+", "_", str(col).strip()).strip("_").lower() or f"col_{i}"
        if base[0].isdigit():
            base = f"c_{base}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        names.append(base if count == 0 else f"{base}_{count + 1}")
    df = df.copy()
    df.columns = names
    return df


def coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        s = df[col]
        if (
            pd.api.types.is_numeric_dtype(s)
            or pd.api.types.is_datetime64_any_dtype(s)
            or pd.api.types.is_bool_dtype(s)
        ):
            continue
        if not any(hint in col for hint in DATE_HINTS):
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(s, errors="coerce")
        non_null = s.notna().sum()
        if non_null and parsed.notna().sum() / non_null >= 0.9:
            df[col] = parsed
    return df


def stringify_objects(df: pd.DataFrame) -> pd.DataFrame:
    """Mixed-type object columns break Parquet; make them clean strings."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]):
            df[col] = df[col].map(lambda v: None if pd.isna(v) else str(v))
    return df


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return stringify_objects(coerce_dates(clean_columns(df)))


def make_table_name(label: str) -> str:
    name = re.sub(r"\W+", "_", label).strip("_").lower() or "data"
    return f"t_{name}" if name[0].isdigit() else name


def unique_table_name(label: str, used: set[str]) -> str:
    base = make_table_name(label)[:100]
    name, n = base, 2
    while name in used:
        name = f"{base}_{n}"
        n += 1
    used.add(name)
    return name


def _update(db, ds: Dataset, **fields) -> None:
    for key, value in fields.items():
        setattr(ds, key, value)
    db.commit()


def fail_interrupted_datasets(db: Session, older_than: timedelta | None = None) -> int:
    """
    Mark 'processing' datasets as failed so the user can retry them. The pipeline runs inside the
    API process, so a restart kills it mid-way and nothing else would ever update the row.
    At startup every processing row is dead (older_than=None); while running, only rows that
    have not progressed for `older_than` are considered stuck.
    """
    stmt = select(Dataset).where(Dataset.status == "processing")
    if older_than is not None:
        stmt = stmt.where(Dataset.updated_at < utcnow() - older_than)
    stuck = db.scalars(stmt).all()
    for ds in stuck:
        ds.status, ds.stage, ds.error = "failed", None, INTERRUPTED_ERROR
    if stuck:
        db.commit()
    return len(stuck)


def run_pipeline(dataset_id: str) -> None:
    """Background job: raw files -> cleaned parquet tables + profile + AI-drafted semantic layer."""
    db = SessionLocal()
    try:
        ds = db.get(Dataset, dataset_id)
        if ds is None:
            return
        try:
            storage = get_storage()
            raw_keys = [
                k
                for k in storage.list_keys(f"raw/{ds.id}")
                if Path(k).suffix.lower() in ALLOWED_EXTENSIONS
            ]
            if not raw_keys:
                raise ValueError("No source files were found for this dataset.")

            _update(db, ds, stage="Reading files", progress=10)
            used_names: set[str] = set()
            profiles: list[dict] = []

            for index, key in enumerate(raw_keys, start=1):
                for label, df in load_tables(storage.get_local_path(key)):
                    if df.empty or len(df.columns) == 0:
                        continue
                    if len(profiles) >= MAX_TABLES:
                        raise ValueError(f"Too many tables (the limit is {MAX_TABLES}).")

                    df = prepare_dataframe(df)
                    table_name = unique_table_name(label, used_names)
                    profile = profile_dataframe(df, table_name)

                    buffer = io.BytesIO()
                    df.to_parquet(buffer, index=False)
                    parquet_key = f"parquet/{ds.id}/{table_name}.parquet"
                    storage.put_bytes(parquet_key, buffer.getvalue())

                    profile["parquetKey"] = parquet_key
                    profiles.append(profile)

                _update(
                    db,
                    ds,
                    stage=f"Profiled {Path(key).name}",
                    progress=10 + int(60 * index / len(raw_keys)),
                )

            if not profiles:
                raise ValueError("The file contains no data.")

            first = profiles[0]
            _update(
                db,
                ds,
                stage="Building semantic layer",
                progress=80,
                row_count=sum(p["rows"] for p in profiles),
                column_count=sum(len(p["columns"]) for p in profiles),
                # table_name / parquet_key keep pointing at the first table for older code paths
                table_name=first["table"],
                parquet_key=first["parquetKey"],
                profile={"tables": profiles},
            )

            layer = build_baseline_layer(ds.id, ds.name, profiles)

            _update(db, ds, stage="Asking the AI to describe your data", progress=88)
            layer = enrich_layer(layer, profiles)
            save_layer(db, ds.id, layer)

            _update(db, ds, status="needs_review", progress=100, stage=None, error=None)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline failed for dataset %s", dataset_id)
            db.rollback()
            failed = db.get(Dataset, dataset_id)
            if failed:
                _update(db, failed, status="failed", stage=None, error=str(exc)[:500])
    finally:
        db.close()