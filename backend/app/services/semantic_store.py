from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.utils import utcnow
from app.models.dataset import SemanticLayer
from app.schemas.semantic import SemanticLayerSchema


def latest_layer(db: Session, dataset_id: str) -> SemanticLayer | None:
    stmt = (
        select(SemanticLayer)
        .where(SemanticLayer.dataset_id == dataset_id)
        .order_by(SemanticLayer.version.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def latest_approved_layer(db: Session, dataset_id: str) -> SemanticLayer | None:
    stmt = (
        select(SemanticLayer)
        .where(SemanticLayer.dataset_id == dataset_id, SemanticLayer.is_approved.is_(True))
        .order_by(SemanticLayer.version.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


def save_layer(
    db: Session, dataset_id: str, layer: SemanticLayerSchema, approved: bool = False
) -> SemanticLayer:
    last = latest_layer(db, dataset_id)
    row = SemanticLayer(
        dataset_id=dataset_id,
        version=(last.version + 1) if last else 1,
        layer=layer.model_dump(by_alias=True),
        is_approved=approved,
        approved_at=utcnow() if approved else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row