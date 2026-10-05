import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (registers tables with SQLAlchemy)
from app.api import auth, chat, datasets, health, history, insights, semantic
from app.core.auth import require_auth, validate_auth_config
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.ingestion import fail_interrupted_datasets

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def _recover_interrupted_jobs() -> None:
    """Ingestion runs in-process, so a restart mid-pipeline leaves datasets stuck in 'processing'."""
    db = SessionLocal()
    try:
        count = fail_interrupted_datasets(db)
        if count:
            logger.warning("Marked %d dataset(s) interrupted by the last restart as failed.", count)
    except Exception:  # noqa: BLE001  (a maintenance sweep must never block startup)
        logger.exception("Could not check for interrupted dataset jobs")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_auth_config()
    if settings.storage_backend.lower() == "local":
        logger.warning(
            "STORAGE_BACKEND=local: uploads live on this machine's disk and are lost on redeploy. "
            "Use STORAGE_BACKEND=s3 in production."
        )
    logger.info("CORS origins: %s", settings.cors_origin_list)
    _recover_interrupted_jobs()
    yield


app = FastAPI(title="OCTOPROC Data Analysis Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Open: the wake-up check and the login itself
app.include_router(health.router)
app.include_router(auth.router)

# Everything else requires a valid sign-in token (when ACCESS_CODE is set)
protected = [Depends(require_auth)]
for router in (
    datasets.router,
    semantic.router,
    chat.router,
    history.router,
    insights.router,
):
    app.include_router(router, dependencies=protected)
