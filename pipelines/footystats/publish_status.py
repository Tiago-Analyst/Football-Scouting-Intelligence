"""Project a generation's state into the database, for the site to read.

The generation itself lives on disk beside its snapshots. The API cannot see
that disk - the fetch runs in CI, the API runs elsewhere - so without this,
`/data-quality` would show full refresh progress in development and nothing at
all in production.

Deliberately best-effort. A refresh that cannot reach the database has not
failed: the fetch is the expensive part and it succeeded, the snapshots are on
disk, and the next run continues. Losing the progress *display* is not worth
losing the progress.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pipelines.footystats.generations import Generation


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def record(generation: Generation, *, source: str = "footystats") -> bool:
    """Upsert this generation's state. Returns whether it was written.

    One row per generation, updated as it progresses, so how long a refresh
    took stays answerable afterwards.
    """
    try:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

        from sqlalchemy.dialects.postgresql import insert

        from app.core.database import get_session_factory
        from app.models import FactRefreshGeneration
    except Exception:
        return False

    meta = generation.metadata
    now = datetime.now(UTC)
    values = {
        "generation_id": meta.generation_id,
        "source": source,
        "status": meta.status,
        "created_at": _parse(meta.created_at) or now,
        "updated_at": _parse(meta.last_updated_at) or now,
        "published_at": _parse(meta.published_at),
        "total_expected_players": meta.total_expected_players,
        "completed_players": meta.completed_players,
        "failed_players": len(meta.failed_players),
        "competitions_expected": len(meta.competitions_expected),
        "competitions_complete": len(meta.competitions_complete),
        "complete": bool(meta.complete),
    }

    try:
        with get_session_factory()() as session:
            statement = insert(FactRefreshGeneration).values(**values)
            statement = statement.on_conflict_do_update(
                constraint="uq_refresh_generation",
                set_={k: v for k, v in values.items() if k not in {"generation_id", "source"}},
            )
            session.execute(statement)
            session.commit()
        return True
    except Exception:
        return False
