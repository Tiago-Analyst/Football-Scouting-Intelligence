"""The population a reader is shown is the one their percentiles came from.

WHAT A READER GOT

Live production, 6 November 2026. One goalkeeper, one season, one
competition, described in the same words on two pages:

    player profile         Goalkeepers - Colombia Categoria Primera A - 2026    53
    shortlist comparison   Goalkeepers - Colombia Categoria Primera A - 2026     0

The percentiles either side were identical and correct - 23.80 at the 97th,
0.17 at the 90th, 0.08 at the 99th, the same on both pages. Only the
population they claimed to be measured against disagreed, and one of the two
said the ranking was against nobody.

WHY

`population_size` is per metric: it counts the players carrying a value for
that metric, in that competition, in that season. Both endpoints picked their
header context by walking `PROFILE_METRICS` and taking the first entry
present - including a metric the provider supplies for no goalkeeper in that
league, whose population is a truthful nought.

The profile was fixed when this was found there, with a comment explaining
exactly this. The shortlist comparison was not, because the rule lived in a
`next(...)` expression rather than in a function, and a rule written twice is
a rule that will be fixed once.

WHAT THESE ASSERT

That the rule is one function, that both endpoints call it, and that it skips
an unranked metric while still answering for a player who ranked on nothing.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.analytics.metrics import DerivedMetric
from app.analytics.percentiles import ComparisonContext, PercentileResult, PercentileScope
from app.api.v1 import shortlists as shortlists_api
from app.api.v1.players import PROFILE_METRICS, ranked_context
from app.schemas.canonical import PositionGroup


def _context(population: int) -> ComparisonContext:
    return ComparisonContext(
        scope=PercentileScope.COMPETITION,
        position_group=PositionGroup.GK,
        season_id="2026",
        competition_ids=("footystats:1",),
        population_size=population,
        minimum_minutes=0,
    )


def _result(metric: DerivedMetric, *, percentile: float | None, population: int) -> PercentileResult:
    return PercentileResult(
        metric=metric,
        value=1.0 if percentile is not None else None,
        percentile=percentile,
        oriented=percentile,
        lower_is_better=False,
        context=_context(population),
        unavailable_reason=None if percentile is not None else "metric not available",
    )


class TestTheContextComesFromAMetricThatRanked:
    def test_an_unranked_first_metric_does_not_name_the_population(self) -> None:
        """The production case, in miniature.

        The first metric in the list is one the provider does not supply for
        anybody in this competition, so its population is nought. The second
        ranked against fifty-three players. Fifty-three is the number the
        reader is looking at.
        """
        first, second = PROFILE_METRICS[0], PROFILE_METRICS[1]
        ranked = {
            first: _result(first, percentile=None, population=0),
            second: _result(second, percentile=74.0, population=53),
        }
        context = ranked_context(ranked, None)
        assert context is not None
        assert context.population_size == 53

    def test_a_ranked_first_metric_is_still_used(self) -> None:
        first, second = PROFILE_METRICS[0], PROFILE_METRICS[1]
        ranked = {
            first: _result(first, percentile=12.0, population=41),
            second: _result(second, percentile=74.0, population=53),
        }
        assert ranked_context(ranked, None).population_size == 41

    def test_a_player_who_ranked_on_nothing_still_gets_a_context(self) -> None:
        """A named population of nought is honest when nothing was ranked.

        It is dishonest the moment something was, which is the whole of the
        bug above. Falling back to None instead would take the reference group
        off the page, which section 25 forbids.
        """
        first = PROFILE_METRICS[0]
        ranked = {first: _result(first, percentile=None, population=0)}
        context = ranked_context(ranked, None)
        assert context is not None
        assert context.population_size == 0

    def test_nothing_ranked_and_nothing_present_is_no_context(self) -> None:
        assert ranked_context({}, None) is None


class TestTheRuleLivesInOnePlace:
    def test_the_comparison_calls_it_rather_than_deriving_it(self) -> None:
        source = inspect.getsource(shortlists_api.compare)
        assert "ranked_context(ranked, view)" in source, (
            "the shortlist comparison derives its own context again"
        )
        assert "to_context(ranked[" not in source, (
            "the shortlist comparison walks PROFILE_METRICS itself again"
        )

    def test_no_endpoint_keeps_a_private_copy_of_the_walk(self) -> None:
        """The shape that let one of the two be fixed and the other not.

        `next((to_context(ranked[m].context, ...) for m in PROFILE_METRICS ...)`
        written inline is a rule nobody can see is duplicated. It belongs to
        `ranked_context` and nowhere else.
        """
        api = Path(shortlists_api.__file__).parent
        offenders = []
        for path in sorted(api.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "for m in PROFILE_METRICS" not in text:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if "to_context(ranked[" in line and path.name != "players.py":
                    offenders.append(f"{path.name}:{line_no}")
        assert offenders == [], f"an inline context walk came back: {offenders}"

    def test_players_keeps_exactly_one_walk_and_it_is_the_helper(self) -> None:
        source = inspect.getsource(ranked_context)
        assert source.count("for m in PROFILE_METRICS") == 2, (
            "the helper no longer tries a ranked metric first and then any metric"
        )
        assert "percentile is not None" in source
