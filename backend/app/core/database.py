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

from app.core.config import Settings, get_settings, is_pooled

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


def direct_url(url: str) -> str:
    """The same database reached without the pooler, where that is derivable.

    Neon names the two endpoints for one database `ep-x-pooler.<region>` and
    `ep-x.<region>`, so the direct host is the pooled one with `-pooler`
    removed. That is a convention, not a guarantee, and no other provider
    shares it: Supabase's direct host is a different name entirely.

    So this returns the URL unchanged when it cannot do better, and the caller
    decides. A caller that needs an unpooled connection must check rather than
    assume it got one.
    """
    if not is_pooled(url):
        return url
    # Split from the right: a password may contain anything, including the
    # text this replaces.
    head, at, tail = url.rpartition("@")
    if not at:
        return url.replace("-pooler.", ".", 1)
    return head + at + tail.replace("-pooler.", ".", 1)


def search_path_args(settings: Settings) -> dict[str, str]:
    """The libpq arguments that put the analytical schema on the search path.

    Empty through a pooler, which refuses them - see `build_engine`. Its own
    function so the decision can be asserted on directly: the whole outage was
    one argument reaching a server that will not take it, and
    `create_connect_args` does not report what `create_engine` was handed.
    """
    if is_pooled(settings.sqlalchemy_url):
        return {}
    # Applied per connection rather than per session: a pooled connection
    # handed to a new session must already be pointing at the right place.
    return {"options": f"-csearch_path={settings.analytics_schema},public"}


def build_engine(settings: Settings) -> Engine:
    """Create the SQLAlchemy engine.

    `pool_pre_ping` costs one cheap round-trip per checkout and removes the
    class of errors where a managed database silently drops idle connections.

    WHY THE SEARCH PATH IS SET HERE

    The analytical tables live in a schema of their own - `analytics` when
    serving, `analytics_staging` when a refresh is loading - and the models
    name no schema at all. That is deliberate: one set of models, resolved by
    the connection, so a pipeline step targets staging by being started with a
    different setting rather than by every query growing a qualifier.

    `public` stays on the path behind it, because the operational tables
    (accounts, sessions, shortlists, and the quality and refresh history) are
    never swapped and must resolve wherever the analytical ones point.

    WHY IT IS NOT SET THROUGH A POOLER
    ----------------------------------

    This took production down for the length of one deploy. The search path
    was sent as the libpq startup parameter `options`, which is exactly right
    for a direct connection and impossible through PgBouncer: in transaction
    pooling mode it refuses every startup parameter outside its small
    allowlist, and `options` is not on it. The connection is rejected at once
    - a fast 503 rather than a timeout, which is what gave it away - and
    `render.yaml` tells the operator to use Neon's pooled endpoint.

    So the parameter is sent only on a direct connection. Through a pooler
    the search path has to come from the server side instead, where it
    survives a pooled connection being handed round:

        ALTER ROLE fri_app IN DATABASE <db> SET search_path = analytics, public;

    Until the analytical tables move out of `public` (migration 0009) the
    default path already resolves them, so a pooled deployment needs that
    statement only when the migration is applied. `docs/deployment.md` says
    so beside the migration step.
    """
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args=search_path_args(settings),
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
