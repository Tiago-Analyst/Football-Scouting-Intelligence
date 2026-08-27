"""Database engine, session factory and declarative base.

Synchronous SQLAlchemy is deliberate: the analytical layer (pandas / numpy /
scikit-learn) is synchronous, and FastAPI already runs sync dependencies in a
worker thread. An async stack would add contagion for no measurable benefit at
this read-mostly workload.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings

# Explicit constraint naming. Without this, Alembic autogenerate cannot emit
# stable DROP statements for unnamed constraints on PostgreSQL.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ORM model in the application."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def build_engine(settings: Settings) -> Engine:
    """Create the SQLAlchemy engine.

    `pool_pre_ping` costs one cheap round-trip per checkout and removes the
    class of errors where a managed database silently drops idle connections.
    """
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        # SQLAlchemy's `echo` attaches a second handler of its own, which
        # duplicates every statement alongside our root handler. SQL logging is
        # instead enabled by raising the sqlalchemy.engine level in
        # configure_logging, so it flows through one pipeline and inherits the
        # request id and redaction processors.
        echo=False,
        future=True,
    )


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Process-wide lazily-created engine."""
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings())
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database_connection() -> tuple[bool, str | None]:
    """Ping the database for the health endpoint.

    Returns `(ok, error_message)`. The message is for server-side logging and
    is not returned to unauthenticated callers verbatim.
    """
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, None
    # A health check must report any failure mode, so catch broadly.
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def get_schema_revision() -> str | None:
    """Current Alembic revision applied to the database, if any.

    Returns None when the migration chain has never been applied, which lets
    the readiness endpoint distinguish "database reachable but unmigrated"
    from "database reachable and ready".
    """
    try:
        with get_engine().connect() as connection:
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            row = result.first()
            return str(row[0]) if row else None
    # An absent alembic_version table is an expected state, not an error.
    except Exception:
        return None


def dispose_engine() -> None:
    """Release pooled connections. Called on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
