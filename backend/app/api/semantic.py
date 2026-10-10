from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.utils import utcnow
from app.models.dataset import Dataset, VerifiedQuery
from app.schemas.dataset import DatasetOut
from app.schemas.insights import QualityIssue
from app.schemas.semantic import DefinitionCheck, SemanticLayerSchema
from app.schemas.verified import VerifiedQueryOut
from app.services.data_quality import check_quality
from app.services.dataset_tables import get_table_paths, get_table_profiles
from app.services.definitions import check_definitions, definition_problems
from app.services.semantic_generator import build_baseline_layer, enrich_layer
from app.services.semantic_store import latest_layer, save_layer
from app.services.verified_store import list_for_dataset

router = APIRouter(prefix="/api/datasets", tags=["semantic"])


def _reviewable_dataset(db: Session, dataset_id: str) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    if ds.status not in ("needs_review", "approved"):
        raise HTTPException(409, f"Dataset is {ds.status}; it has no semantic layer to review yet.")
    return ds


def _reject_bad_definitions(layer: SemanticLayerSchema, status: int = 422) -> None:
    """A broken metric or filter would be copied into every generated query, so it is never saved."""
    problems = definition_problems(layer)
    if problems:
        raise HTTPException(status, "Fix these definitions first: " + " ".join(problems))


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
    _reject_bad_definitions(body)
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


@router.post("/{dataset_id}/semantic/check", response_model=list[DefinitionCheck])
def check_semantic(dataset_id: str, body: SemanticLayerSchema, db: Session = Depends(get_db)):
    """Tries every metric and filter of the given (possibly unsaved) layer against the real data."""
    ds = _reviewable_dataset(db, dataset_id)
    return check_definitions(body, get_table_paths(ds, {t.name for t in body.tables}))


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
    _reject_bad_definitions(SemanticLayerSchema.model_validate(row.layer), status=409)
    row.is_approved = True
    row.approved_at = utcnow()
    ds.status = "approved"
    db.commit()
    return DatasetOut.from_model(ds)


# ---------- verified answers (built from thumbs-ups in chat) ----------


@router.get("/{dataset_id}/verified", response_model=list[VerifiedQueryOut])
def list_verified(dataset_id: str, db: Session = Depends(get_db)):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found")
    return [
        VerifiedQueryOut(
            id=row.id,
            dataset_id=row.dataset_id,
            question=row.question,
            sql=row.sql,
            standalone=row.standalone,
            conversation_id=conversation_id,
            created_at=row.created_at,
        )
        for row, conversation_id in list_for_dataset(db, dataset_id)
    ]


@router.delete("/{dataset_id}/verified/{verified_id}", status_code=204)
def delete_verified(dataset_id: str, verified_id: str, db: Session = Depends(get_db)):
    row = db.get(VerifiedQuery, verified_id)
    if row is None or row.dataset_id != dataset_id:
        raise HTTPException(404, "Verified answer not found")
    db.delete(row)
    db.commit()
