from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (registers tables with SQLAlchemy)
from app.api import auth, chat, datasets, health, history, insights, semantic
from app.core.auth import require_auth, validate_auth_config
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_auth_config()
    yield


app = FastAPI(title="OCTOPROC Data Analysis Agent API", lifespan=lifespan)

print(">>> CORS ORIGINS:", settings.cors_origin_list)

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