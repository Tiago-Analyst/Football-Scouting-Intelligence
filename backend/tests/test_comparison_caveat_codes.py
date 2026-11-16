"""The shortlist comparison's population warnings, as message codes.

The warning body used to travel only as English prose, so a Portuguese comparison
showed a translated heading over an English paragraph. The same two warnings now
also travel as codes, which the interface composes in the reader's language. The
prose stays for any client already reading it, and the two must say the same
thing: one list of warnings, two spellings.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.analytics.percentiles import PercentileScope
from app.api.v1.shortlists import (
    _CAVEAT_CODES,
    MIXED_COMPETITION_CAVEAT,
    MIXED_POSITION_CAVEAT,
    _comparison_caveat,
    _comparison_caveat_codes,
    _comparison_caveat_messages,
)
from app.schemas.api import ComparisonResponse


def column(position_group: str, competition: str) -> SimpleNamespace:
    return SimpleNamespace(
        player=SimpleNamespace(position_group=position_group, competition=competition)
    )


THREE_LEAGUES = [
    column("CM", "Portugal Liga NOS"),
    column("CM", "Netherlands Eredivisie"),
    column("CM", "England Premier League"),
]


def test_three_midfielders_from_three_leagues_warn_about_competition_per_competition() -> None:
    codes = _comparison_caveat_codes(THREE_LEAGUES, PercentileScope.COMPETITION)
    assert codes == ["comparison_caveat_mixed_competition"]


def test_the_same_three_ranked_against_everyone_carry_no_warning() -> None:
    assert _comparison_caveat_codes(THREE_LEAGUES, PercentileScope.GLOBAL) == []
    assert _comparison_caveat(THREE_LEAGUES, PercentileScope.GLOBAL) is None


def test_different_positions_warn_in_either_scope_and_come_first() -> None:
    mixed = [column("CM", "Spain La Liga"), column("CB", "Italy Serie A")]
    assert _comparison_caveat_codes(mixed, PercentileScope.COMPETITION) == [
        "comparison_caveat_mixed_position",
        "comparison_caveat_mixed_competition",
    ]
    assert _comparison_caveat_codes(mixed, PercentileScope.GLOBAL) == [
        "comparison_caveat_mixed_position"
    ]


def test_one_position_and_one_competition_carry_no_warning() -> None:
    same = [column("CM", "Spain La Liga"), column("CM", "Spain La Liga")]
    assert _comparison_caveat_codes(same, PercentileScope.COMPETITION) == []
    assert _comparison_caveat(same, PercentileScope.COMPETITION) is None


@pytest.mark.parametrize("scope", list(PercentileScope))
def test_the_prose_is_exactly_the_codes_in_order(scope: PercentileScope) -> None:
    mixed = [column("CM", "Spain La Liga"), column("CB", "Italy Serie A")]
    codes = _comparison_caveat_codes(mixed, scope)
    assert _comparison_caveat(mixed, scope) == " ".join(_CAVEAT_CODES[code] for code in codes)


def test_each_code_maps_to_the_prose_it_always_had() -> None:
    assert _CAVEAT_CODES == {
        "comparison_caveat_mixed_position": MIXED_POSITION_CAVEAT,
        "comparison_caveat_mixed_competition": MIXED_COMPETITION_CAVEAT,
    }


def test_the_response_carries_the_codes_and_defaults_to_none() -> None:
    assert ComparisonResponse.model_fields["caveat_messages"].default_factory is list
    empty = ComparisonResponse(context=None, players=[])
    assert empty.caveat is None
    assert empty.caveat_messages == []


@pytest.mark.parametrize("scope", list(PercentileScope))
def test_the_messages_are_the_codes_in_the_same_order(scope: PercentileScope) -> None:
    mixed = [column("CM", "Spain La Liga"), column("CB", "Italy Serie A")]
    assert [m.code for m in _comparison_caveat_messages(mixed, scope)] == _comparison_caveat_codes(
        mixed, scope
    )
    assert _comparison_caveat_messages([column("CM", "Spain La Liga")], scope) == []
