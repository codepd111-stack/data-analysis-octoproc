from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import utcnow
from app.models.dataset import Dataset
from app.schemas.dataset import DatasetOut
from app.schemas.insights import QualityIssue
from app.schemas.semantic import SemanticLayerSchema
from app.services.data_quality import check_quality
from app.services.dataset_tables import get_table_profiles
from app.services.semantic_generator import build_baseline_layer, enrich_layer
from app.services.semantic_store import latest_layer, save_layer

router = APIRouter(prefix="/api/datasets", tags=["semantic"])


def _reviewable_dataset(db: Session, dataset_id: str) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    if ds.status not in ("needs_review", "approved"):
        raise HTTPException(409, f"Dataset is {ds.status}; it has no semantic layer to review yet.")
    return ds


@router.get("/{dataset_id}/semantic", response_model=SemanticLayerSchema)
def get_semantic(dataset_id: str, db: Session = Depends(get_db)):
    _reviewable_dataset(db, dataset_id)
    row = latest_layer(db, dataset_id)
    if row is None:
        raise HTTPException(404, "No semantic layer found")
    return SemanticLayerSchema.model_validate(row.layer)


@router.put("/{dataset_id}/semantic", response_model=SemanticLayerSchema)
def save_semantic(dataset_id: str, body: SemanticLayerSchema, db: Session = Depends(get_db)):
    """Saves the edits as a new version (not yet approved). History of edits is kept."""
    _reviewable_dataset(db, dataset_id)
    body.dataset_id = dataset_id
    row = save_layer(db, dataset_id, body, approved=False)
    return SemanticLayerSchema.model_validate(row.layer)


@router.post("/{dataset_id}/semantic/regenerate", response_model=SemanticLayerSchema)
def regenerate_semantic(dataset_id: str, db: Session = Depends(get_db)):
    """Rebuilds the draft from the stored profile and asks the AI again. Saved as a new, unapproved version."""
    ds = _reviewable_dataset(db, dataset_id)
    tables = get_table_profiles(ds)
    if not tables:
        raise HTTPException(409, "No profile is stored for this dataset. Please upload it again.")
    layer = build_baseline_layer(ds.id, ds.name, tables)
    layer = enrich_layer(layer, tables)
    row = save_layer(db, ds.id, layer, approved=False)
    return SemanticLayerSchema.model_validate(row.layer)


@router.get("/{dataset_id}/quality", response_model=list[QualityIssue])
def get_quality(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    return [QualityIssue(**issue) for issue in check_quality(ds)]


@router.post("/{dataset_id}/approve", response_model=DatasetOut)
def approve_semantic(dataset_id: str, db: Session = Depends(get_db)):
    ds = _reviewable_dataset(db, dataset_id)
    row = latest_layer(db, dataset_id)
    if row is None:
        raise HTTPException(404, "No semantic layer found")
    row.is_approved = True
    row.approved_at = utcnow()
    ds.status = "approved"
    db.commit()
    return DatasetOut.from_model(ds)