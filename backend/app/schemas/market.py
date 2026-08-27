"""Canonical market and identity model.

The application's own vocabulary for who a player is and what the market says
about them. Populated from the public Transfermarkt dataset today; the shape is
provider-independent so a different market source could replace it without
touching anything downstream.

Same discipline as the performance model:

- **Absent is not zero.** A market value of `None` means the source does not
  carry one. `0` would assert the player is worth nothing, which is a different
  and much stronger claim.
- **Contract expiry is optional by nature.** The spec describes it as available
  only "where available", so code consuming it must handle absence rather than
  assume a date exists.

`normalized_name` exists for identity resolution, which must never join on a
raw display name across providers.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.canonical import PositionGroup, PreferredFoot


class TransferType(StrEnum):
    """How a move was completed.

    `UNKNOWN` is deliberate: a source that does not state the type must not be
    silently recorded as a permanent transfer.
    """

    PERMANENT = "permanent"
    LOAN = "loan"
    LOAN_END = "loan_end"
    FREE = "free"
    YOUTH = "youth"
    RETIRED = "retired"
    UNKNOWN = "unknown"


# Letters Unicode decomposition cannot handle. NFKD splits a base letter from a
# combining accent, but these are distinct letters with no combining form, so
# they survive decomposition and are then stripped as punctuation - turning
# "Odegaard" into "degaard" and "Andelo" into "an elo". Both spellings are
# common in football, so this is a correctness requirement for identity
# resolution, not a nicety.
_TRANSLITERATIONS = str.maketrans(
    {
        "ø": "o",
        "Ø": "o",
        "đ": "d",
        "Đ": "d",
        "ð": "d",
        "Ð": "d",
        "ł": "l",
        "Ł": "l",
        "ß": "ss",
        "æ": "ae",
        "Æ": "ae",
        "œ": "oe",
        "Œ": "oe",
        "þ": "th",
        "Þ": "th",
        "ı": "i",  # noqa: RUF001 - the dotless i is what is being folded
        "İ": "i",
        "ħ": "h",
        "Ħ": "h",
        "ŧ": "t",
        "Ŧ": "t",
    }
)


def normalize_name(name: str) -> str:
    """Fold a display name into a comparable key.

    Lowercased, accents stripped, punctuation removed, whitespace collapsed.
    Providers disagree constantly on diacritics and hyphenation, so a raw name
    is not a join key - and even this is only ever one signal among date of
    birth, nationality and club (spec section 6).
    """
    transliterated = name.translate(_TRANSLITERATIONS)
    decomposed = unicodedata.normalize("NFKD", transliterated)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_accents.lower()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


class MarketCompetition(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_competition_id: str
    name: str
    country: str | None = None
    tier: str | None = Field(
        default=None, description="Source tier label, kept raw rather than coerced to a number."
    )


class MarketClub(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_club_id: str
    name: str
    source_competition_id: str | None = None
    country: str | None = None


class MarketPlayer(BaseModel):
    """Player identity and current market standing, as one source reports it."""

    model_config = ConfigDict(frozen=True)

    source_player_id: str
    full_name: str
    normalized_name: str

    date_of_birth: date | None = None
    nationality: str | None = None
    secondary_nationality: str | None = None

    preferred_foot: PreferredFoot | None = None
    height_cm: int | None = Field(default=None, ge=100, le=250)

    raw_position: str | None = Field(
        default=None, description="Source position label, retained so a mapping stays auditable."
    )
    raw_sub_position: str | None = None
    position_group: PositionGroup | None = Field(
        default=None,
        description="Standardised group. None when the source label has no confident mapping.",
    )

    current_club_id: str | None = None
    current_competition_id: str | None = None

    market_value_eur: int | None = Field(
        default=None,
        ge=0,
        description="Current valuation. None means unreported, which is not the same as zero.",
    )
    contract_expires: date | None = None

    def age_at(self, reference: date) -> int | None:
        """Age in completed years, or None without a date of birth."""
        if self.date_of_birth is None:
            return None
        born = self.date_of_birth
        return (
            reference.year - born.year - ((reference.month, reference.day) < (born.month, born.day))
        )


class MarketValuePoint(BaseModel):
    """One dated valuation. The series forms market value history."""

    model_config = ConfigDict(frozen=True)

    source_player_id: str
    valued_on: date
    market_value_eur: int = Field(ge=0)
    source_club_id: str | None = None
    source_competition_id: str | None = None


class TransferRecord(BaseModel):
    """One completed move.

    `fee_eur` of `None` means no fee was reported, which covers loans, free
    transfers and undisclosed fees alike - three different situations that must
    not be flattened into zero.
    """

    model_config = ConfigDict(frozen=True)

    source_player_id: str
    transfer_date: date | None = None
    season: str | None = None
    from_club_id: str | None = None
    from_club_name: str | None = None
    to_club_id: str | None = None
    to_club_name: str | None = None
    fee_eur: int | None = Field(default=None, ge=0)
    market_value_at_transfer_eur: int | None = Field(default=None, ge=0)
    transfer_type: TransferType = TransferType.UNKNOWN


class MarketProviderInfo(BaseModel):
    """What a market source is, and whether its schema has been verified."""

    model_config = ConfigDict(frozen=True)

    name: str
    is_mock: bool
    validated: bool = Field(
        description="True only once the source's real schema has been profiled and mapped."
    )
    snapshot_date: date | None = None
    licence: str | None = None
    source_url: str | None = None
    notes: str | None = None
