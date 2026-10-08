"""The all-leagues percentile is a rank of observed values, and stays one.

THE PRODUCT DECISION

A calibration audit measured what the current definition costs: a player under
180 minutes reaches the top tenth of an all-leagues metric 17.4% of the time
against 2.1% for a player with a full season, because the loaded competitions
are at different points in their seasons and a per-90 from one match is as
extreme as the data allows.

The decision was to keep the definition and say what the population is made
of, rather than to normalise the number. Season maturity is context and
evidence; it is not folded into a published figure that a reader can otherwise
check against the per-90 printed beside it.

These hold the calculation to that. Everything here is about what the engine
must NOT start doing - the copy that carries the explanation is guarded in
`frontend/tests/cross-league-percentile.test.mjs`.

See `docs/cross_league_percentiles.md`.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from app.analytics import percentiles as percentiles_module
from app.analytics.percentiles import PercentileScope
from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api() -> TestClient:
    from app.core.config import get_settings
    from app.main import create_app
    from tests.conftest import build_settings

    settings = build_settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def view():
    from app.services.analytics_service import get_analytics_view

    loaded = get_analytics_view()
    if loaded.percentiles is None or loaded.percentiles.eligible_count < 50:
        pytest.skip("needs a loaded population")
    return loaded


class TestTheCalculationIsUntouched:
    def test_the_rank_is_of_the_observed_value_and_nothing_else(self, view) -> None:
        """Recomputed by hand from the population, for a real player."""
        engine = view.percentiles
        group, season = next(iter(engine._by_group))
        records = engine._population_for(group, season, None)
        if len(records) < 30:
            pytest.skip("needs a populated group")

        from app.analytics.metrics import DerivedMetric

        metric = DerivedMetric.TACKLES_PER90
        values = sorted(v for r in records if (v := r.metrics.get(metric)) is not None)
        if len(values) < 30:
            pytest.skip("needs a populated metric")

        for record in records[:25]:
            value = record.metrics.get(metric)
            if value is None:
                continue
            ranked = engine.rank(record, metric, scope=PercentileScope.GLOBAL)
            if ranked.percentile is None:
                continue
            # The share of the population at or below this value, which is
            # what a percentile of observed values is and all it is.
            at_or_below = sum(1 for v in values if v <= value)
            expected = 100 * at_or_below / len(values)
            assert abs(ranked.percentile - expected) < 12.0, (
                f"{record.player_key} on {metric.value}: engine {ranked.percentile:.1f}, "
                f"plain rank {expected:.1f}"
            )

    def test_minutes_do_not_enter_the_ranking(self) -> None:
        """No maturity, evidence or sample term in the rank itself.

        The engine measures maturity to describe the population. It must not
        use it to place anyone in it.
        """
        source = inspect.getsource(percentiles_module.PercentileEngine.rank)
        for forbidden in ("minutes", "maturity", "evidence_weight", "shrink", "established"):
            assert forbidden not in source, f"`rank` references {forbidden}"

    def test_no_strength_coefficient_exists(self) -> None:
        import re

        # Identifiers, not prose. The module says in two places that a
        # league-strength coefficient is NOT applied, and a guard that trips
        # on its own disclaimer teaches people to delete the guard.
        #
        # Whole words, because "elo" is inside "below" and "developed".
        body = inspect.getsource(percentiles_module).lower()
        for forbidden in ("league_strength", "strength_coefficient", "uefa", "elo"):
            assert not re.search(rf"\b{re.escape(forbidden)}\b", body), (
                f"percentiles references {forbidden}"
            )

    def test_that_guard_can_actually_fail(self) -> None:
        """It was silently vacuous once, so it is checked against itself.

        A control character reached the pattern in place of a word boundary,
        so it matched nothing and the assertion passed whatever the source
        said. A guard that cannot fail is worse than no guard: it is counted.
        """
        import re

        pattern = rf"\b{re.escape('elo')}\b"
        assert re.search(pattern, "an elo coefficient applied here")
        assert not re.search(pattern, "below the developed median")


class TestThePopulationIsNotRestricted:
    def test_every_competition_is_in_the_all_leagues_population(self, view) -> None:
        """No competition is excluded for being early in its season."""
        engine = view.percentiles
        group, season = next(iter(engine._by_group))
        records = engine._population_for(group, season, None)
        loaded = {r.competition_id for r in engine._by_group[(group, season)]}
        included = {r.competition_id for r in records}
        assert included == loaded

    def test_short_samples_are_in_it(self, view) -> None:
        """Minutes band a figure; they do not decide who is compared."""
        engine = view.percentiles
        group, season = next(iter(engine._by_group))
        records = engine._population_for(group, season, None)
        thin = [r for r in records if (r.rateable_minutes or 0) < ESTABLISHED_SAMPLE_MINUTES]
        assert thin, "no short-sample player is in the all-leagues population"

    def test_the_population_is_not_split_by_sample_band(self, view) -> None:
        """One population, not four. Bands would be a threshold discontinuity."""
        engine = view.percentiles
        group, season = next(iter(engine._by_group))
        records = engine._population_for(group, season, None)
        minutes = sorted((r.rateable_minutes or 0) for r in records)
        assert minutes[0] < ESTABLISHED_SAMPLE_MINUTES <= minutes[-1], (
            "the all-leagues population no longer spans the sample bands"
        )


class TestTheSeungWonJeongCase:
    """An established player with a low all-leagues rank is not a defect.

    The audited case: 1,912 minutes, 0.50 successful dribbles per 90 - above
    the median established player's 0.369 - at the 10th all-leagues percentile.
    The percentile describes position in the observed distribution; the sample
    describes how much football produced the value. Both are true at once.

    Pinned as a property rather than as his numbers, which move with every
    refresh.
    """

    def test_an_established_player_may_rank_low_and_still_read_as_established(
        self, api: TestClient, view
    ) -> None:
        from app.analytics.metrics import DerivedMetric

        engine = view.percentiles
        metric = DerivedMetric.SUCCESSFUL_DRIBBLES_PER90

        found = None
        for key, record in view.players.items():
            if (record.minutes or 0) < ESTABLISHED_SAMPLE_MINUTES:
                continue
            metrics = view.player_metrics(key)
            if metrics is None or metrics.metrics.get(metric) is None:
                continue
            ranked = engine.rank(metrics, metric, scope=PercentileScope.GLOBAL)
            if ranked.percentile is not None and ranked.percentile <= 25:
                found = (key, record, ranked)
                break

        if found is None:
            pytest.skip("no established player ranks low on this metric in this data")

        key, record, ranked = found
        response = api.get(f"/api/v1/players/{key}/stats")
        assert response.status_code == 200
        body = response.json()

        # The sample is still reported, and still says established.
        player = api.get(f"/api/v1/players/{key}").json()
        assert player["sample_band"] == "established"
        assert (player["minutes"] or 0) >= ESTABLISHED_SAMPLE_MINUTES

        # And the population that produced the low rank describes itself.
        context = body.get("global_context")
        assert context is not None
        assert context["competitions_in_population"] >= 1
        assert "median_minutes" in context

    def test_the_population_says_how_far_into_its_seasons_it_is(
        self, api: TestClient, view
    ) -> None:
        """The qualification the decision rests on has to actually be sent."""
        for key in list(view.players)[:40]:
            body = api.get(f"/api/v1/players/{key}/stats").json()
            context = body.get("global_context")
            if context is None:
                continue
            assert "competitions_established" in context
            assert "established_share" in context
            assert "is_early_season" in context
            return
        pytest.skip("no player produced an all-leagues context")


class TestEvidenceStaysOutOfTheNumber:
    def test_the_stats_response_carries_no_adjusted_percentile(self, api: TestClient, view) -> None:
        """One percentile per scope. A second, adjusted one would be the
        redefinition this decision refused."""
        for key in list(view.players)[:40]:
            body = api.get(f"/api/v1/players/{key}/stats").json()
            metrics = body.get("metrics") or []
            if not metrics:
                continue
            for metric in metrics:
                for forbidden in (
                    "adjusted_percentile",
                    "shrunk_percentile",
                    "maturity_adjusted_percentile",
                    "evidence_adjusted_percentile",
                ):
                    assert forbidden not in metric, f"{forbidden} is being returned"
            return
        pytest.skip("no player produced metrics")
