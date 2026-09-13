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
        "checkpoint_revision": int(meta.checkpoint_revision),
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


def expected_state(generation_id: str, *, source: str = "footystats") -> tuple[str, int] | None:
    """What the database says this generation's status and revision are.

    The authoritative answer for a runner deciding whether the cache it
    restored is the one it should be resuming. `None` when the database is
    unreachable or holds no such generation - which a caller must treat as
    "cannot verify", never as "verified".
    """
    try:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

        from sqlalchemy import select

        from app.core.database import get_session_factory
        from app.models import FactRefreshGeneration

        with get_session_factory()() as session:
            row = session.execute(
                select(
                    FactRefreshGeneration.status, FactRefreshGeneration.checkpoint_revision
                ).where(
                    FactRefreshGeneration.source == source,
                    FactRefreshGeneration.generation_id == generation_id,
                )
            ).first()
    except Exception:
        return None
    return (str(row[0]), int(row[1])) if row else None


def _transition(
    generation_id: str,
    *,
    source: str,
    from_statuses: tuple[str, ...],
    to_status: str,
) -> bool:
    """Move one generation's database status, guarded on where it is now.

    Guarded rather than set: `--mark-validated` run twice, or run after a
    promotion already happened, must not drag a PUBLISHED generation back to
    VALIDATED. Returns whether a row changed.
    """
    try:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

        from sqlalchemy import update

        from app.core.database import get_session_factory
        from app.models import FactRefreshGeneration

        with get_session_factory()() as session:
            result = session.execute(
                update(FactRefreshGeneration)
                .where(
                    FactRefreshGeneration.source == source,
                    FactRefreshGeneration.generation_id == generation_id,
                    FactRefreshGeneration.status.in_(from_statuses),
                )
                .values(status=to_status, updated_at=datetime.now(UTC))
            )
            session.commit()
            return bool(result.rowcount)
    except Exception:
        return False


def reconcile_revision(
    generation_id: str, local_revision: int, *, source: str = "footystats"
) -> bool:
    """Advance the database's checkpoint revision to a newer local one.

    The case: the last run wrote checkpoint 5, saved its cache, and could not
    reach the database, which still says 4. The restore brought back 5, the
    verifier found it newer and intact, and the database should now say 5 -
    otherwise the next run's exact key asks for 4 again.

    Strictly forward. `WHERE checkpoint_revision < :local` means a stale
    caller can never move it back, and a concurrent one can never move it
    past what is on disk. Returns whether a row changed.
    """
    try:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

        from sqlalchemy import update

        from app.core.database import get_session_factory
        from app.models import FactRefreshGeneration

        with get_session_factory()() as session:
            result = session.execute(
                update(FactRefreshGeneration)
                .where(
                    FactRefreshGeneration.source == source,
                    FactRefreshGeneration.generation_id == generation_id,
                    FactRefreshGeneration.checkpoint_revision < local_revision,
                )
                .values(checkpoint_revision=local_revision, updated_at=datetime.now(UTC))
            )
            session.commit()
            return bool(result.rowcount)
    except Exception:
        return False


def mark_validated(generation_id: str, *, source: str = "footystats") -> bool:
    """COMPLETE -> VALIDATED, after every candidate check has passed.

    The database and the disk both move: the disk so a local run agrees with
    what the site shows, the database because it is what the gate reads.
    """
    from pipelines.footystats.generations import GenerationStatus, GenerationStore

    generation = GenerationStore().get(generation_id)
    if generation is not None and generation.status is GenerationStatus.COMPLETE:
        generation.set_status(GenerationStatus.VALIDATED)
    return _transition(
        generation_id, source=source, from_statuses=("COMPLETE",), to_status="VALIDATED"
    )


def mark_failed(generation_id: str, *, reason: str, source: str = "footystats") -> bool:
    """Any live status -> FAILED. For `generations --abandon`; nothing else.

    The reason is printed rather than stored: the database row carries no
    reason column, and the disk metadata - when there is one - does.
    """
    print(f"generation {generation_id}: {reason}")
    return _transition(
        generation_id,
        source=source,
        from_statuses=("IN_PROGRESS", "COMPLETE", "VALIDATED"),
        to_status="FAILED",
    )


def main(argv: list[str] | None = None) -> int:
    """`python -m pipelines.footystats.publish_status --mark-validated <id>`."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "--mark-validated",
        metavar="GENERATION_ID",
        help="Record that every candidate check passed for this generation.",
    )
    args = parser.parse_args(argv)

    if not args.mark_validated:
        parser.print_help()
        return 2

    if mark_validated(args.mark_validated):
        print(f"generation {args.mark_validated} is VALIDATED")
        return 0
    state = expected_state(args.mark_validated)
    if state is None:
        print(
            f"::error::could not mark generation {args.mark_validated} VALIDATED: the "
            f"database is unreachable or holds no such generation"
        )
        return 1
    status, _ = state
    if status in {"VALIDATED", "PUBLISHED"}:
        # Already past this point. Not an error: a retried run reaches here
        # legitimately, and failing it would stop the publication it exists for.
        print(f"generation {args.mark_validated} is already {status}; nothing to do")
        return 0
    print(
        f"::error::generation {args.mark_validated} is {status}, not COMPLETE; refusing to "
        f"mark it VALIDATED"
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
