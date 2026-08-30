"""Drop the market history of players the site never shows.

    python -m pipelines.load.prune              # report only
    python -m pipelines.load.prune --apply      # and delete

The Transfermarkt dataset covers roughly 50,000 players. The performance
provider covers the ones who play in the 47 configured competitions, which is
about 8,500 of them. Valuation history and transfers are loaded for all 50,000,
and 80% of that is history for people no page can reach.

---------------------------------------------------------------------------
WHY THIS IS NOT A FILTER IN THE LOADER
---------------------------------------------------------------------------

The obvious version - load only the market data of players who have statistics
- cannot work, because at the moment Transfermarkt is loaded that association
does not exist yet. The performance provider has not been loaded, and even once
it has, its players are separate `dim_player` rows until identity resolution
merges them. A filter at load time would find nothing used and keep nothing.

So this runs **after** resolution, when "which players does the site show" is
finally a question the database can answer.

---------------------------------------------------------------------------
WHAT IS DELIBERATELY NOT PRUNED
---------------------------------------------------------------------------

The 45,000 players without statistics stay, and so do their bridge rows.

They are not dead weight: they are the pool identity resolution matches
against. Every future competition ingested brings players who need to find
their Transfermarkt identity in that set, and a smaller pool is a lower match
rate - quietly, because an unmatched player simply never appears.

Their **market history** is another matter. Nothing reads it: resolution
matches on name, date of birth, nationality and club, all of which live on
`dim_player`. Deleting it costs nothing and removes about two thirds of the
database.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PruneReport:
    """What would go, and what would stay."""

    valuations_total: int
    valuations_unused: int
    transfers_total: int
    transfers_unused: int
    players_with_stats: int
    players_total: int
    applied: bool = False

    @property
    def is_safe(self) -> bool:
        """Whether anything at all is in use.

        Nothing in use means one of two things, and both are reasons to stop:
        identity resolution has not run, so no player has both statistics and a
        market history; or the sources genuinely do not overlap. Pruning either
        way would delete every valuation in the database.
        """
        return self.valuations_total > 0 and self.valuations_unused < self.valuations_total


def survey(session) -> PruneReport:  # type: ignore[no-untyped-def]
    """Count what is used without changing anything."""
    from sqlalchemy import func, select

    from app.models import DimPlayer, FactMarketValue, FactPlayerSeasonStats, FactTransfer

    played = select(FactPlayerSeasonStats.player_id).distinct().scalar_subquery()

    def count(model, where=None):  # type: ignore[no-untyped-def]
        query = select(func.count()).select_from(model)
        if where is not None:
            query = query.where(where)
        return session.scalar(query) or 0

    return PruneReport(
        valuations_total=count(FactMarketValue),
        valuations_unused=count(FactMarketValue, FactMarketValue.player_id.not_in(played)),
        transfers_total=count(FactTransfer),
        transfers_unused=count(FactTransfer, FactTransfer.player_id.not_in(played)),
        players_with_stats=session.scalar(
            select(func.count(func.distinct(FactPlayerSeasonStats.player_id)))
        )
        or 0,
        players_total=count(DimPlayer),
    )


def prune(session) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """Delete the market history of players with no statistics.

    Returns the number of valuations and transfers removed. The players
    themselves are untouched - see the module docstring.
    """
    from sqlalchemy import delete, select

    from app.models import FactMarketValue, FactPlayerSeasonStats, FactTransfer

    played = select(FactPlayerSeasonStats.player_id).distinct().scalar_subquery()

    valuations = session.execute(
        delete(FactMarketValue).where(FactMarketValue.player_id.not_in(played))
    )
    transfers = session.execute(delete(FactTransfer).where(FactTransfer.player_id.not_in(played)))
    return valuations.rowcount, transfers.rowcount


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete. Without this, nothing is written and the survey is printed.",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.core.config import get_settings
    from app.core.database import get_session_factory
    from app.core.logging import configure_logging, get_logger

    configure_logging(get_settings())
    log = get_logger(__name__)

    session = get_session_factory()()
    try:
        report = survey(session)

        print(f"{report.players_with_stats:,} of {report.players_total:,} players have statistics.")
        print(
            f"\n  valuations   {report.valuations_total:>9,} loaded, "
            f"{report.valuations_unused:>9,} for players with none"
        )
        print(
            f"  transfers    {report.transfers_total:>9,} loaded, "
            f"{report.transfers_unused:>9,} for players with none"
        )

        if not report.is_safe:
            print(
                "\nRefusing: no player has both statistics and a market history. "
                "Either identity resolution has not run yet, or the sources do not "
                "overlap - and pruning now would delete every valuation there is.",
                file=sys.stderr,
            )
            return 2

        if not args.apply:
            print(
                f"\nNothing was deleted. --apply would remove "
                f"{report.valuations_unused + report.transfers_unused:,} rows."
            )
            print(
                "\nThe players themselves stay: they are the pool identity "
                "resolution matches future ingests against."
            )
            return 0

        valuations, transfers = prune(session)
        session.commit()

        print(f"\n  deleted      {valuations:,} valuations, {transfers:,} transfers")
        print("  kept         every player, and every history the site can reach")
        log.info("market_history_pruned", valuations=valuations, transfers=transfers)

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
