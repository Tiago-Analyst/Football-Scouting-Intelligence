"""Alembic migration environment.

The database URL comes from application settings rather than alembic.ini, so
credentials stay in `.env` and there is a single source of truth for how the
application and its migrations reach PostgreSQL.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Importing the models package registers every table on Base.metadata, which
# is what `alembic revision --autogenerate` compares against the database.
import app.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live connection."""
    # WHY THE SEARCH PATH IS PINNED TO `public`
    #
    # The application connects with `analytics` first, so its models resolve to
    # the schema being served. A migration inheriting that would create every
    # new table there - including operational ones like accounts and
    # shortlists, which must never be swapped away by a promotion.
    #
    # Set on the engine rather than with a statement on the connection. Issuing
    # `SET search_path` through `exec_driver_sql` begins an implicit
    # transaction, which alembic's own `begin_transaction()` then cannot
    # manage: the migration runs, reports success, and is rolled back when the
    # connection closes. That failure is silent in both directions - the schema
    # is unchanged and the version table is unchanged, so a re-run does the
    # same nothing.
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"options": "-csearch_path=public"},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # Otherwise autogenerate proposes dropping every analytical table,
            # because the models name no schema and it cannot see them in
            # `public`. Analytical changes are written by hand against both
            # schemas; see `docs/data_publication_lifecycle.md`.
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
