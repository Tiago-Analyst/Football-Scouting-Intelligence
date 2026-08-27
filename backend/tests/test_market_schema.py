"""Canonical market model.

Name normalisation matters more here than it looks: identity resolution joins
two providers that disagree constantly about accents and punctuation, and a raw
display name is not a join key.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.market import (
    MarketPlayer,
    MarketValuePoint,
    TransferRecord,
    TransferType,
    normalize_name,
)


class TestNormalizeName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Sergio Agüero", "sergio aguero"),
            ("João Félix", "joao felix"),
            ("Kylian Mbappé", "kylian mbappe"),
            ("N'Golo Kanté", "n golo kante"),
            ("Pierre-Emerick Aubameyang", "pierre emerick aubameyang"),
            ("  Extra   Spaces  ", "extra spaces"),
            ("Ødegaard", "odegaard"),
            ("Šešić", "sesic"),
        ],
    )
    def test_folds_accents_punctuation_and_whitespace(self, raw: str, expected: str) -> None:
        assert normalize_name(raw) == expected

    def test_is_idempotent(self) -> None:
        once = normalize_name("Kylian Mbappé")
        assert normalize_name(once) == once

    def test_differently_written_forms_converge(self) -> None:
        """The whole point: two providers spelling one player differently must
        produce the same key."""
        assert normalize_name("Anđelo Šesar") == normalize_name("Andelo Sesar")


class TestMarketPlayer:
    def _player(self, **overrides: object) -> MarketPlayer:
        base: dict[str, object] = {
            "source_player_id": "1",
            "full_name": "Test Player",
            "normalized_name": "test player",
        }
        base.update(overrides)
        return MarketPlayer(**base)  # type: ignore[arg-type]

    def test_age_is_computed_from_date_of_birth(self) -> None:
        player = self._player(date_of_birth=date(2000, 6, 15))
        assert player.age_at(date(2026, 6, 14)) == 25
        assert player.age_at(date(2026, 6, 15)) == 26

    def test_age_is_none_without_a_birth_date(self) -> None:
        assert self._player().age_at(date(2026, 1, 1)) is None

    def test_absent_market_value_is_none_not_zero(self) -> None:
        """None means unreported. Zero would assert the player is worth
        nothing, which is a much stronger and usually false claim."""
        assert self._player().market_value_eur is None

    def test_negative_market_value_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._player(market_value_eur=-1)

    def test_implausible_height_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._player(height_cm=18)


class TestTransferRecord:
    def test_type_defaults_to_unknown(self) -> None:
        """The Transfermarkt dataset carries no transfer type. The default must
        not quietly assert 'permanent'."""
        record = TransferRecord(source_player_id="1")
        assert record.transfer_type is TransferType.UNKNOWN

    def test_zero_fee_and_absent_fee_stay_distinct(self) -> None:
        """A reported free transfer and an unreported fee are different facts."""
        free = TransferRecord(source_player_id="1", fee_eur=0)
        undisclosed = TransferRecord(source_player_id="1")
        assert free.fee_eur == 0
        assert undisclosed.fee_eur is None
        assert free.fee_eur != undisclosed.fee_eur

    def test_negative_fee_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TransferRecord(source_player_id="1", fee_eur=-100)


class TestMarketValuePoint:
    def test_requires_a_date_and_value(self) -> None:
        with pytest.raises(ValidationError):
            MarketValuePoint(source_player_id="1")  # type: ignore[call-arg]

    def test_negative_valuation_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MarketValuePoint(source_player_id="1", valued_on=date(2026, 1, 1), market_value_eur=-5)
