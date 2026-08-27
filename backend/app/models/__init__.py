"""ORM models.

Importing this package registers every table on `Base.metadata`, which is what
`alembic revision --autogenerate` compares against the live database. A model
not reachable from here is invisible to migrations.
"""

from app.models.accounts import UserAccount, UserSession
from app.models.dimensions import (
    BridgePlayerSource,
    DimClub,
    DimCompetition,
    DimPlayer,
    DimSeason,
)
from app.models.facts import (
    FactDataQuality,
    FactMarketValue,
    FactPlayerSeasonStats,
    FactTransfer,
)
from app.models.shortlists import Shortlist, ShortlistEntry

__all__ = [
    "BridgePlayerSource",
    "DimClub",
    "DimCompetition",
    "DimPlayer",
    "DimSeason",
    "FactDataQuality",
    "FactMarketValue",
    "FactPlayerSeasonStats",
    "FactTransfer",
    "Shortlist",
    "ShortlistEntry",
    "UserAccount",
    "UserSession",
]
