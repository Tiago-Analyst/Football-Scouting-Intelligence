"""Valuation history and transfers, read from the database.

These two endpoints were the last thing still served by asking a *provider*
rather than reading what the pipeline loaded. That was deliberate once - the
history is per player and does not belong in the analytical view - but it left
two sources of truth, and the consequences were quiet:

- in demo mode the provider is the mock one, which knows only invented player
  ids, so a real player's history came back empty rather than wrong. Empty is
  the better failure and still the wrong answer: 4,768 of the loaded players
  have valuation history sitting in `fact_market_value`;
- in production the provider reads the Transfermarkt CSV snapshot directly, so
  the page could disagree with the database it was loaded from, and a load that
  had not been run yet would still appear to work.

Reading from the database makes these endpoints agree with every other figure
on the page, and makes the loaded data the only thing the site serves.

The provider stays where it belongs: it is how the pipeline *ingests*.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BridgePlayerSource, FactMarketValue, FactTransfer


@dataclass(frozen=True)
class ValuationPoint:
    valued_on: date
    market_value_eur: int


@dataclass(frozen=True)
class TransferRecord:
    transfer_date: date | None
    season: str | None
    from_club: str | None
    to_club: str | None
    fee_eur: int | None
    transfer_type: str


def _database_id(session: Session, player_key: str) -> int | None:
    """Resolve a provider's player id to the row it was merged into.

    A merged player carries a bridge row per source and they all point at the
    same row, so any of them answers this. Looked up per request rather than
    carried on the view: it is one indexed read, and putting the database's own
    id into the view is how it starts being used as a key.
    """
    return session.scalar(
        select(BridgePlayerSource.player_id).where(
            BridgePlayerSource.source_player_id == player_key
        )
    )


def market_value_history(session: Session, player_key: str) -> list[ValuationPoint]:
    """Every recorded valuation, oldest first so a chart reads left to right."""
    player_id = _database_id(session, player_key)
    if player_id is None:
        return []

    rows = session.execute(
        select(FactMarketValue.valued_on, FactMarketValue.market_value_eur)
        .where(FactMarketValue.player_id == player_id)
        .order_by(FactMarketValue.valued_on)
    ).all()
    return [ValuationPoint(valued_on=row[0], market_value_eur=row[1]) for row in rows]


def transfers(session: Session, player_key: str) -> list[TransferRecord]:
    """Every recorded transfer, most recent first.

    Undated transfers sort last rather than being dropped: the Transfermarkt
    dataset carries some without a date, and a career with a gap in it is more
    honest than one silently missing a move.
    """
    player_id = _database_id(session, player_key)
    if player_id is None:
        return []

    rows = session.scalars(
        select(FactTransfer)
        .where(FactTransfer.player_id == player_id)
        .order_by(FactTransfer.transfer_date.desc().nullslast())
    ).all()
    return [
        TransferRecord(
            transfer_date=row.transfer_date,
            season=row.season,
            from_club=row.from_club_name,
            to_club=row.to_club_name,
            fee_eur=row.fee_eur,
            transfer_type=row.transfer_type.value,
        )
        for row in rows
    ]
