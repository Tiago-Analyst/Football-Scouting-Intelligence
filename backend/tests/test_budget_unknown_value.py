"""One rule for a hard maximum market value: unknown cannot satisfy it.

The replacement finder passed a player of unknown value through a budget and
only then left his affordability blank, so a EUR 100k brief returned four
players nobody knew the price of. The rule is `within_budget`; every surface
with a maximum-value filter uses it (search, similar players, recruitment,
replacements). Opportunities already required a known value. These pin the
rule itself, at the level where the four cases are one line each.
"""

from __future__ import annotations

import pytest

from app.analytics.similarity import SimilarityCandidate, SimilarityFilters, within_budget
from app.schemas.canonical import PositionGroup

BUDGET = 5_000_000


def candidate(value: int | None) -> SimilarityCandidate:
    return SimilarityCandidate(
        player_key="p",
        display_name="P",
        position_group=PositionGroup.CM,
        competition_id="c",
        market_value_eur=value,
    )


TARGET = candidate(1)


class TestTheRule:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (3_000_000, True),  # inside the budget
            (BUDGET, True),  # exactly at it
            (7_000_000, False),  # over it
            (None, False),  # unknown cannot be confirmed
            (0, True),  # a recorded zero is a value, not an absence
        ],
    )
    def test_within_budget(self, value: int | None, expected: bool) -> None:
        assert within_budget(value, BUDGET) is expected


class TestInTheSimilarityFilters:
    def test_no_budget_keeps_unknown_value_eligible(self) -> None:
        assert SimilarityFilters().allows(candidate(None), TARGET)

    def test_a_budget_admits_a_known_value_inside_it(self) -> None:
        assert SimilarityFilters(max_market_value_eur=BUDGET).allows(candidate(3_000_000), TARGET)

    def test_a_budget_refuses_a_known_value_over_it(self) -> None:
        assert not SimilarityFilters(max_market_value_eur=BUDGET).allows(
            candidate(7_000_000), TARGET
        )

    def test_a_budget_refuses_an_unknown_value(self) -> None:
        assert not SimilarityFilters(max_market_value_eur=BUDGET).allows(candidate(None), TARGET)
