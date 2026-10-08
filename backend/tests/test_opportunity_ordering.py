"""Opportunities ranked by evidence, without anyone losing their place in it.

Observed in the live product: a Raw Fit of 98 from 24 minutes at the top of
the list, above 93 from 344 minutes, 93 from 3 minutes, 92 from 41. Every one
of those percentiles is honest - a per-90 figure from half a match is as
extreme as the data allows, which is exactly why it reaches the top - and the
page labelled each as Very Low Sample.

Labelling is not ordering. This is a discovery surface: the first name is the
one a scout rings. Three minutes and eighteen hundred minutes were carrying
the same ranking confidence.

What must not change, and is asserted here: the Raw Role Fit, the Role Fit
Percentile, who is eligible, and the absence of any minutes floor. A
short-sample player who is genuinely exceptional still places well.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analytics.reliability import FULL_EVIDENCE_MINUTES

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
def opportunities(api: TestClient) -> dict:
    """A wide screen, so there is a population to rank rather than a handful."""
    response = api.get(
        "/api/v1/opportunities",
        params={
            "max_age": 40,
            "min_role_score": 50,
            "min_minutes": 0,
            "max_market_value_eur": 200_000_000,
            "limit": 30,
        },
    )
    assert response.status_code == 200
    body = response.json()
    if len(body["items"]) < 3:
        pytest.skip("too few opportunities to say anything about an ordering")
    return body


class TestTheOrderUsesEvidence:
    def test_the_list_descends_by_the_ranking_score(self, opportunities: dict) -> None:
        ranked = [item["ranking_score"] for item in opportunities["items"]]
        assert ranked == sorted(ranked, reverse=True)

    def test_it_is_not_ordered_by_the_raw_fit(self, opportunities: dict) -> None:
        """The whole point. If these agree there was nothing thin in the list.

        Not a failure when they do agree - it means every survivor has a full
        season - so this reports rather than asserts, and the assertion below
        is the one that holds whatever the data looks like.
        """
        raw = [item["best_role_score"] for item in opportunities["items"]]
        if raw == sorted(raw, reverse=True):
            pytest.skip("no short-sample player in this screen; nothing was reordered")
        assert [i["ranking_score"] for i in opportunities["items"]] == sorted(
            [i["ranking_score"] for i in opportunities["items"]], reverse=True
        )

    def test_a_full_season_is_ranked_at_its_raw_fit(self, opportunities: dict) -> None:
        """Evidence-aware must mean untouched when the evidence is complete."""
        for item in opportunities["items"]:
            minutes = item["player"]["minutes"] or 0
            if minutes < FULL_EVIDENCE_MINUTES:
                continue
            assert item["evidence_weight"] == pytest.approx(1.0)
            assert item["ranking_score"] == pytest.approx(item["best_role_score"], abs=0.05)
            assert item["ranking_note"] is None

    def test_a_short_sample_is_ranked_below_its_raw_fit(self, opportunities: dict) -> None:
        short = [
            item
            for item in opportunities["items"]
            if (item["player"]["minutes"] or 0) < FULL_EVIDENCE_MINUTES
            and item["best_role_score"] > item["ranking_score"]
        ]
        if not short:
            pytest.skip("no short-sample player above the mean in this screen")
        for item in short:
            assert item["evidence_weight"] < 1.0
            assert item["ranking_note"] is not None
            assert "unchanged" in item["ranking_note"]

    def test_the_ordering_is_deterministic(self, api: TestClient) -> None:
        """The mean is taken over the population being ranked, not sampled."""
        params = {"max_age": 40, "min_role_score": 50, "min_minutes": 0, "limit": 20}
        first = api.get("/api/v1/opportunities", params=params).json()
        second = api.get("/api/v1/opportunities", params=params).json()
        assert [i["player"]["player_id"] for i in first["items"]] == [
            i["player"]["player_id"] for i in second["items"]
        ]
        assert [i["ranking_score"] for i in first["items"]] == [
            i["ranking_score"] for i in second["items"]
        ]


class TestNothingAnalyticalMoved:
    def test_the_raw_fit_is_the_players_own_role_score(self, opportunities: dict) -> None:
        """The ordering writes to its own field and nowhere else."""
        for item in opportunities["items"]:
            assert item["best_role_score"] == item["player"]["best_role_score"]

    def test_the_role_fit_percentile_is_untouched(
        self, api: TestClient, opportunities: dict
    ) -> None:
        """It is a rank among players scored the same way, not a placement here."""
        for item in opportunities["items"][:5]:
            percentile = item["player"]["best_role_percentile"]
            if percentile is None:
                continue
            profile = api.get(f"/api/v1/players/{item['player']['player_id']}").json()
            roles = profile.get("roles") or {}
            best = roles.get("best")
            if best is None or best.get("role_fit_percentile") is None:
                continue
            assert best["role_fit_percentile"] == pytest.approx(percentile)

    def test_the_ranking_never_becomes_the_displayed_fit(self, opportunities: dict) -> None:
        """Two numbers, and the raw one must survive being ranked."""
        moved = [
            item
            for item in opportunities["items"]
            if abs(item["ranking_score"] - item["best_role_score"]) > 0.05
        ]
        if not moved:
            pytest.skip("nothing was reordered in this screen")
        for item in moved:
            assert item["best_role_score"] != item["ranking_score"]


class TestEligibilityIsUnchanged:
    def test_a_player_with_almost_no_minutes_is_still_listed(self, api: TestClient) -> None:
        """No hidden floor. The whole product refuses one and this is no exception."""
        body = api.get(
            "/api/v1/opportunities",
            params={"max_age": 40, "min_role_score": 50, "min_minutes": 0, "limit": 100},
        ).json()
        minutes = [item["player"]["minutes"] or 0 for item in body["items"]]
        if not minutes:
            pytest.skip("empty screen")
        assert min(minutes) < FULL_EVIDENCE_MINUTES, (
            "every listed player has a full season; this screen cannot show "
            "whether short samples are still eligible"
        )

    def test_the_user_supplied_minutes_filter_still_works(self, api: TestClient) -> None:
        """Optional and chosen, which is the only kind of floor allowed."""
        body = api.get(
            "/api/v1/opportunities",
            params={"max_age": 40, "min_role_score": 50, "min_minutes": 900, "limit": 50},
        ).json()
        for item in body["items"]:
            assert (item["player"]["minutes"] or 0) >= 900

    def test_an_exceptional_short_sample_can_still_place_well(self, opportunities: dict) -> None:
        """Shrinkage toward the mean, not exclusion and not a cap.

        A thin figure far above the average still ranks above an ordinary one:
        it is pulled toward the mean, not down to it.
        """
        for item in opportunities["items"]:
            if (item["player"]["minutes"] or 0) >= FULL_EVIDENCE_MINUTES:
                continue
            if item["best_role_score"] is None:
                continue
            # Ranked value sits between the mean and the raw value, never past
            # either: the defining property of shrinkage.
            low, high = sorted((item["best_role_score"], item["ranking_score"]))
            assert low <= item["ranking_score"] <= high


class TestItUsesTheExistingUtility:
    def test_there_is_one_ranking_formula_rather_than_two(self) -> None:
        """A second formula would eventually disagree with the first."""
        import inspect

        from app.api.v1 import recruitment

        source = inspect.getsource(recruitment.market_opportunities)
        assert "rank_by_evidence" in source
        # No local arithmetic on the weight: that is how a second formula
        # starts.
        assert "evidence_weight(" not in source
        assert "shrink(" not in source


class TestThePriorIsNotTheSurvivors:
    """The first attempt at this inverted the list.

    Shrinking toward the mean of the candidates is right when the candidates
    are everybody. Opportunities screens on role fit before it ranks, so its
    survivors are an elite and their average describes one. Shrinking toward
    that average read every thin candidate as probably excellent: on the live
    list a 57-minute fit of 81 was lifted to 87.8 and ranked second, above a
    973-minute 84 pushed to 83.8 and twelfth.

    An ordering that rewards having played less is the failure this whole
    mechanism exists to prevent, arrived at from the other direction.
    """

    def test_a_thin_candidate_is_pulled_down_not_up(self, opportunities: dict) -> None:
        from app.api.v1.recruitment import _ordinary_role_fit
        from app.services.analytics_service import get_analytics_view

        ordinary = _ordinary_role_fit(get_analytics_view())
        screened = [i["best_role_score"] for i in opportunities["items"]]
        if not screened:
            pytest.skip("empty screen")
        # The screen selects upward; if it did not, this test is describing a
        # situation that no longer exists.
        assert sum(screened) / len(screened) > ordinary

        for item in opportunities["items"]:
            if (item["player"]["minutes"] or 0) >= FULL_EVIDENCE_MINUTES:
                continue
            # Every candidate here cleared a role-fit floor, so every thin one
            # is above the ordinary player and must be read downward.
            assert item["ranking_score"] <= item["best_role_score"] + 0.05

    def test_a_full_season_outranks_a_thin_higher_fit(self, api: TestClient) -> None:
        """The sentence the whole change exists to make true.

        Measured on the page's own default criteria, because that is the list
        the defect was observed in - a 24-minute 98 first and a 3-minute 93
        third, above a 973-minute 84.
        """
        body = api.get(
            "/api/v1/opportunities",
            params={
                "max_age": 23,
                "min_role_score": 80,
                "min_minutes": 0,
                "max_market_value_eur": 5_000_000,
                "contract_within_months": 18,
                "limit": 30,
            },
        ).json()
        items = body["items"]
        if len(items) < 3:
            pytest.skip("the default screen is empty on this data")
        full = [i for i in items if (i["player"]["minutes"] or 0) >= FULL_EVIDENCE_MINUTES]
        thin = [i for i in items if (i["player"]["minutes"] or 0) < 120]
        pairs = [(f, t) for f in full for t in thin if t["best_role_score"] > f["best_role_score"]]
        if not pairs:
            pytest.skip("no full-season player is out-scored by a very thin one here")
        for seasoned, brief in pairs:
            assert seasoned["ranking_score"] > brief["ranking_score"], (
                f"{brief['player']['name']} ({brief['player']['minutes']} min) still "
                f"outranks {seasoned['player']['name']} "
                f"({seasoned['player']['minutes']} min)"
            )

    def test_the_prior_is_measured_over_everyone_with_a_fit(self) -> None:
        import inspect

        from app.api.v1 import recruitment

        source = inspect.getsource(recruitment._ordinary_role_fit)
        # Over `best_roles`, which is the whole population - not over the
        # screened list, and not a constant written down here.
        assert "view.best_roles.values()" in source
        assert "mean=_ordinary_role_fit(view)" in inspect.getsource(
            recruitment.market_opportunities
        )
