from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.utils import new_id
from app.models.dataset import Dataset
from app.schemas.dataset import DatasetOut
from app.services.ingestion import ALLOWED_EXTENSIONS, run_pipeline
from app.services.storage import get_storage

from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _group_name(names: list[str]) -> str:
    stems = [Path(n).stem for n in names]
    if len(stems) == 1:
        return stems[0]
    if len(stems) == 2:
        return f"{stems[0]} + {stems[1]}"
    return f"{stems[0]} + {len(stems) - 1} more"


@router.get("", response_model=list[DatasetOut])
def list_datasets(db: Session = Depends(get_db)):
    stmt = select(Dataset).order_by(Dataset.created_at.desc())
    return [DatasetOut.from_model(d) for d in db.scalars(stmt).all()]


@router.post("/upload", response_model=list[DatasetOut], status_code=201)
async def upload_datasets(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    combine: bool = Form(False),
    db: Session = Depends(get_db),
):
    """
    Each file becomes its own dataset, unless combine=true and several files are sent:
    then they all become tables of ONE dataset (so relationships between them can be detected).
    Excel files with several sheets always become several tables of one dataset.
    """
    for f in files:
        if Path(f.filename or "").suffix.lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                400, f"Unsupported file type: {f.filename}. Use CSV, Excel or Parquet."
            )

    limit = settings.max_upload_mb * 1024 * 1024
    items: list[tuple[str, bytes]] = []
    for f in files:
        data = await f.read()
        if len(data) > limit:
            raise HTTPException(413, f"{f.filename} is larger than {settings.max_upload_mb} MB.")
        items.append((Path(f.filename or "upload").name, data))

    groups = [items] if (combine and len(items) > 1) else [[item] for item in items]

    storage = get_storage()
    created: list[Dataset] = []

    for group in groups:
        dataset_id = new_id()
        used: set[str] = set()
        first_key: str | None = None
        total = 0

        for name, data in group:
            unique, counter = name, 2
            while unique in used:
                unique = f"{Path(name).stem}_{counter}{Path(name).suffix}"
                counter += 1
            used.add(unique)

            key = f"raw/{dataset_id}/{unique}"
            await run_in_threadpool(storage.put_bytes, key, data)
            first_key = first_key or key
            total += len(data)

        names = [n for n, _ in group]
        ds = Dataset(
            id=dataset_id,
            name=_group_name(names)[:255],
            file_name=", ".join(names)[:255],
            raw_key=first_key or "",
            size_bytes=total,
            status="processing",
            progress=5,
            stage="Queued",
        )
        db.add(ds)
        created.append(ds)

    db.commit()
    for ds in created:
        db.refresh(ds)
        background.add_task(run_pipeline, ds.id)
    return [DatasetOut.from_model(d) for d in created]


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    return DatasetOut.from_model(ds)


@router.post("/{dataset_id}/retry", response_model=DatasetOut)
def retry_dataset(dataset_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    if ds.status != "failed":
        raise HTTPException(409, "Only failed datasets can be retried.")
    ds.status, ds.progress, ds.stage, ds.error = "processing", 5, "Queued", None
    db.commit()
    background.add_task(run_pipeline, ds.id)
    return DatasetOut.from_model(ds)