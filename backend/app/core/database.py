import socket

from sqlalchemy import JSON, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

is_postgres = settings.database_url.startswith("postgresql")

connect_args: dict = {}
if is_postgres:
    # Neon's pooled connection runs behind PgBouncer; disable psycopg's auto-prepared statements
    connect_args["prepare_threshold"] = None
    # Fail with a clear error instead of hanging. 30s leaves room for Neon's cold start.
    connect_args["connect_timeout"] = 30
elif settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

# pool_pre_ping: Neon scales to zero, so connections can go stale
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)

if is_postgres:

    @event.listens_for(engine, "do_connect")
    def _prefer_ipv4(dialect, conn_rec, cargs, cparams):
        """
        Some networks advertise IPv6 but don't route it, which makes every new connection
        wait for timeouts on dead IPv6 addresses. Resolve an IPv4 address ourselves and pass it
        as hostaddr. The hostname is still used for TLS/SNI, which Neon needs for routing.
        """
        host = cparams.get("host")
        if not host or "hostaddr" in cparams:
            return
        try:
            infos = socket.getaddrinfo(
                host, cparams.get("port") or 5432, family=socket.AF_INET, type=socket.SOCK_STREAM
            )
        except OSError:
            return  # fall back to normal resolution
        if infos:
            cparams["hostaddr"] = infos[0][4][0]


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# JSONB on Postgres, plain JSON elsewhere
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()