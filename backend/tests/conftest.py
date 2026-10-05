"""
Shared fixtures. Settings are read the moment `app` is imported, so the environment is prepared
first: a throwaway SQLite file (one in-memory DB per connection would not survive the thread pool
that FastAPI runs sync endpoints in), local storage in a temp folder, sign-in off, no AI key.
Environment variables take precedence over backend/.env, so a developer's real settings are
never touched.
"""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="octoproc-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["S3_CACHE_DIR"] = ""
os.environ["ACCESS_CODE"] = ""
os.environ["AUTH_SECRET"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["TRUST_PROXY_HEADERS"] = "false"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    # The `with` runs the lifespan (auth validation, interrupted-job sweep) like a real start
    with TestClient(app) as c:
        yield c
