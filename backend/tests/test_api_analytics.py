"""Analytical API endpoints.

Two kinds of assertion here. The ordinary ones check filters, pagination and
shapes. The ones that matter more check that the API cannot present a number
without the qualifications the spec attaches to it: the comparison population,
the sample-size band, and the statements about what a score is not.
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient

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
def a_midfielder(api: TestClient) -> dict:
    """A midfielder the percentile engine can actually rank.

    Taking the first row was enough while the database always held the dense
    demo universe. Against real data most players sit in a competition and
    position group with fewer than the ten comparable player-seasons a
    percentile needs, so the first row has an empty comparison population and
    every test built on it fails for a reason that is not a fault.
    """
    # A defensive midfielder first, because that is the shape these tests were
    # written around; any outfield player if no midfielder is rankable, because
    # what the tests actually need is a populated comparison group.
    for params in (
        {"position_group": "DM", "minutes_min": 900, "limit": 25, "sort": "role_score"},
        {"minutes_min": 900, "limit": 60, "sort": "role_score"},
    ):
        response = api.get("/api/v1/players", params=params)
        assert response.status_code == 200
        for item in response.json()["items"]:
            stats = api.get(f"/api/v1/players/{item['player_id']}/stats").json()
            # A percentile the engine actually produced. `context` sits at the
            # top of the response rather than on each metric, so looking for it
            # there finds nothing and skips every test built on this fixture.
            if any(metric.get("percentile") is not None for metric in stats.get("metrics", [])):
                return item

    pytest.skip(
        "no loaded player has a comparison population; these paths need a "
        "competition with at least ten players in one position group"
    )


@pytest.fixture(scope="module")
def stats(api: TestClient, a_midfielder: dict) -> dict:
    return api.get(f"/api/v1/players/{a_midfielder['player_id']}/stats").json()


@pytest.fixture(scope="module")
def a_replaceable_player(api: TestClient) -> dict:
    """A player who actually has comparable peers.

    Replacement is built on similarity, and similarity now withholds pairs that
    do not resemble each other rather than padding a list to length. So a target
    with no close peers correctly yields no replacements - which is the right
    behaviour and the wrong fixture for testing that replacements are ranked.
    """
    items = api.get(
        "/api/v1/players", params={"minutes_min": 900, "limit": 60, "sort": "role_score"}
    ).json()["items"]
    for item in items:
        similar = api.get(
            f"/api/v1/players/{item['player_id']}/similar", params={"limit": 5}
        ).json()
        if similar.get("results"):
            return item
    pytest.skip("no loaded player has a comparable peer to be replaced by")


@pytest.fixture(scope="module")
def similar(api: TestClient, a_midfielder: dict) -> dict:
    return api.get(
        f"/api/v1/players/{a_midfielder['player_id']}/similar", params={"limit": 10}
    ).json()


class TestPlayerSearch:
    def test_returns_a_page_of_players(self, api: TestClient) -> None:
        body = api.get("/api/v1/players", params={"limit": 5}).json()
        assert len(body["items"]) == 5
        assert body["total"] > 5
        assert body["limit"] == 5

    def test_never_returns_the_whole_database(self, api: TestClient) -> None:
        """Section 27: the browser must not receive 20,000 players to filter."""
        response = api.get("/api/v1/players", params={"limit": 500})
        assert response.status_code == 422

    def test_position_filter_narrows_results(self, api: TestClient) -> None:
        body = api.get("/api/v1/players", params={"position_group": "GK", "limit": 20}).json()
        assert body["items"]
        assert all(p["position_group"] == "GK" for p in body["items"])

    def test_age_filter_is_applied(self, api: TestClient) -> None:
        body = api.get("/api/v1/players", params={"age_max": 21, "limit": 20}).json()
        assert body["items"]
        assert all(p["age"] is not None and p["age"] <= 21 for p in body["items"])

    def test_minutes_filter_is_applied(self, api: TestClient) -> None:
        body = api.get("/api/v1/players", params={"minutes_min": 2000, "limit": 20}).json()
        assert all(p["minutes"] >= 2000 for p in body["items"])

    def test_name_search_matches(self, api: TestClient, a_midfielder: dict) -> None:
        needle = a_midfielder["name"].split(" ")[0]
        body = api.get("/api/v1/players", params={"search": needle, "limit": 20}).json()
        assert any(needle in p["name"] for p in body["items"])

    def test_pagination_moves_through_results(self, api: TestClient) -> None:
        first = api.get("/api/v1/players", params={"limit": 5, "offset": 0}).json()
        second = api.get("/api/v1/players", params={"limit": 5, "offset": 5}).json()
        assert {p["player_id"] for p in first["items"]} != {p["player_id"] for p in second["items"]}

    def test_every_row_carries_its_sample_band(self, api: TestClient) -> None:
        """Rule 23: a per-90 figure from 200 minutes must not look identical to
        one from 3,000."""
        body = api.get("/api/v1/players", params={"limit": 20, "minutes_min": 0}).json()
        assert all(p["sample_band"] in {"full", "low", "insufficient"} for p in body["items"])


class TestPlayerProfile:
    def test_returns_a_player(self, api: TestClient, a_midfielder: dict) -> None:
        body = api.get(f"/api/v1/players/{a_midfielder['player_id']}").json()
        assert body["name"] == a_midfielder["name"]

    def test_unknown_player_is_a_404(self, api: TestClient) -> None:
        assert api.get("/api/v1/players/does-not-exist").status_code == 404

    def test_demo_data_is_flagged(self, api: TestClient, a_midfielder: dict) -> None:
        body = api.get(f"/api/v1/players/{a_midfielder['player_id']}").json()
        assert body["is_mock"] is True


class TestTheWholeProfileAtOnce:
    """One request that answers what four used to.

    It exists so the deploy can render every profile ahead of time - four calls
    across five and a half thousand pages is twenty-two thousand round trips,
    which the rate limit refuses. The risk that buys is two routes drifting
    apart, so these compare them rather than checking the shape.
    """

    def test_it_matches_the_individual_endpoints(self, api: TestClient, a_midfielder: dict) -> None:
        player_id = a_midfielder["player_id"]
        composite = api.get(f"/api/v1/players/{player_id}/profile").json()

        assert composite["player"] == api.get(f"/api/v1/players/{player_id}").json()
        assert composite["stats"] == api.get(f"/api/v1/players/{player_id}/stats").json()
        assert (
            composite["similar"]
            == api.get(f"/api/v1/players/{player_id}/similar", params={"limit": 6}).json()
        )

        roles = api.get(f"/api/v1/players/{player_id}/roles")
        # 404 there means "no role could be fitted", which is not a failure of
        # the profile - the composite reports it as an absence and carries on.
        assert composite["roles"] == (roles.json() if roles.status_code == 200 else None)

    def test_defaults_are_stated_rather_than_inherited(
        self, api: TestClient, a_midfielder: dict
    ) -> None:
        """Calling a handler directly hands it `Query(...)` objects, not values.

        A default that arrives as its own marker object is the quiet way this
        breaks, so the count is checked against the number asked for.
        """
        player_id = a_midfielder["player_id"]
        body = api.get(f"/api/v1/players/{player_id}/profile", params={"similar_limit": 3}).json()
        assert len(body["similar"]["results"]) <= 3
        assert body["stats"]["context"] is None or isinstance(
            body["stats"]["context"]["population_size"], int
        )

    def test_an_unknown_player_is_not_found(self, api: TestClient) -> None:
        assert api.get("/api/v1/players/no-such-player/profile").status_code == 404


class TestPlayerStats:
    def test_returns_metrics_with_percentiles(self, stats: dict) -> None:
        assert stats["metrics"]
        assert any(m["percentile"] is not None for m in stats["metrics"])

    def test_every_percentile_stays_in_range(self, stats: dict) -> None:
        for metric in stats["metrics"]:
            if metric["percentile"] is not None:
                assert 0.0 <= metric["percentile"] <= 100.0

    def test_the_comparison_population_is_always_present(self, stats: dict) -> None:
        """Section 25 forbids hiding the reference group."""
        context = stats["context"]
        assert context is not None
        assert context["label"]
        assert context["population_size"] > 0

    def test_no_context_claims_to_be_strength_adjusted(self, stats: dict) -> None:
        assert stats["context"]["strength_adjusted"] is False

    def test_the_sample_band_is_explained(self, stats: dict) -> None:
        assert stats["sample"]["band"] in {"full", "low", "insufficient"}
        assert stats["sample"]["explanation"]

    def test_inverse_metrics_are_marked(self, stats: dict) -> None:
        """The UI has to say that being dispossessed often is bad, or a high
        percentile there reads as good."""
        inverse = [m for m in stats["metrics"] if m["lower_is_better"]]
        assert inverse

    def test_scores_decompose_into_components(self, stats: dict) -> None:
        available = [s for s in stats["scores"] if s["score"] is not None]
        assert available
        for score in available:
            assert score["components"]
            total = sum(c["contribution"] or 0.0 for c in score["components"])
            assert total == pytest.approx(score["score"], abs=0.01)

    def test_a_global_scope_carries_the_cross_league_caveat(
        self, api: TestClient, a_midfielder: dict
    ) -> None:
        body = api.get(
            f"/api/v1/players/{a_midfielder['player_id']}/stats", params={"scope": "global"}
        ).json()
        context = body["context"]
        # The warning belongs to a comparison that actually crosses leagues, and
        # a global scope does not guarantee one: if every comparable player
        # happens to sit in a single competition, there is no cross-league
        # effect to warn about. Asserting the caveat unconditionally only held
        # while the seeded universe always spanned several competitions.
        spans_leagues = len(context["competition_ids"]) > 1
        assert bool(context["caveat"]) is spans_leagues

    def test_an_unknown_scope_is_rejected(self, api: TestClient, a_midfielder: dict) -> None:
        response = api.get(
            f"/api/v1/players/{a_midfielder['player_id']}/stats", params={"scope": "galaxy"}
        )
        assert response.status_code == 422


class TestRoles:
    def test_returns_a_best_role_and_alternatives(
        self, api: TestClient, a_midfielder: dict
    ) -> None:
        body = api.get(f"/api/v1/players/{a_midfielder['player_id']}/roles").json()
        assert body["best"]["score"] is not None
        assert isinstance(body["alternatives"], list)

    def test_alternatives_never_beat_the_best(self, api: TestClient, a_midfielder: dict) -> None:
        body = api.get(f"/api/v1/players/{a_midfielder['player_id']}/roles").json()
        for alternative in body["alternatives"]:
            assert alternative["score"] <= body["best"]["score"]

    def test_the_meaning_of_a_role_score_is_returned(
        self, api: TestClient, a_midfielder: dict
    ) -> None:
        """Rules 20 and 21: never presented as quality or probability."""
        body = api.get(f"/api/v1/players/{a_midfielder['player_id']}/roles").json()
        assert "not player quality" in body["meaning"]
        assert "not a probability" in body["meaning"]

    def test_role_definitions_never_expose_their_weights(self, api: TestClient) -> None:
        """Section 28: the frontend receives results, not implementations."""
        roles = api.get("/api/v1/roles").json()
        assert len(roles) == 15
        for role in roles:
            assert set(role) == {"key", "label", "description", "position_groups", "caveat"}


class TestSimilarity:
    def test_returns_ranked_results(self, similar: dict) -> None:
        scores = [r["similarity"] for r in similar["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_results_share_the_targets_position(self, similar: dict) -> None:
        target_group = similar["target"]["position_group"]
        assert all(r["player"]["position_group"] == target_group for r in similar["results"])

    def test_the_target_is_not_returned(self, similar: dict) -> None:
        target = similar["target"]["player_id"]
        assert all(r["player"]["player_id"] != target for r in similar["results"])

    def test_profile_strength_is_reported(self, similar: dict) -> None:
        """Cosine ignores magnitude, so a shape match between a much stronger
        and a much weaker player must be visible."""
        for result in similar["results"]:
            assert 0.0 <= result["profile_strength_ratio"] <= 1.0
            assert isinstance(result["comparable_strength"], bool)

    def test_similarity_is_never_called_a_probability(self, similar: dict) -> None:
        assert "not a probability" in similar["meaning"]

    def test_filters_narrow_the_pool(self, api: TestClient, a_midfielder: dict) -> None:
        body = api.get(
            f"/api/v1/players/{a_midfielder['player_id']}/similar",
            params={"different_competition": True, "limit": 10},
        ).json()
        target_competition = body["target"]["competition"]
        assert all(r["player"]["competition"] != target_competition for r in body["results"])


class TestRecruitment:
    def test_ranks_players_against_a_profile(self, api: TestClient) -> None:
        body = api.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_security": 60, "chance_creation": 40},
                "filters": {"position_groups": ["DM"], "min_minutes": 900},
                "limit": 10,
            },
        ).json()
        assert body["items"]
        scores = [c["score"] for c in body["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_an_unscoreable_profile_says_which_score_and_why(self, api: TestClient) -> None:
        """Ball Progression needs progressive passes, which the provider does
        not supply, so weighting it matches nobody.

        Returning nothing is correct. Returning nothing without saying why is
        not: the page looked identical to a search whose filters were too
        narrow, and widening them is the one remedy that cannot help.
        """
        body = api.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_progression": 100},
                "filters": {"position_groups": ["DM"], "min_minutes": 900},
                "limit": 10,
            },
        ).json()
        assert body["items"] == []
        assert body["considered"] > 0, "candidates were admitted, so the data is to blame"

        unavailable = body["unavailable_scores"]
        assert [u["key"] for u in unavailable] == ["ball_progression"]
        # The component missing for *every* candidate, not one player's list: a
        # component missing for one player is a thin comparison population.
        assert unavailable[0]["missing"] == ["progressive_passes_per90"]
        assert "narrowing the filters will not" in body["explanation"]

    def test_filters_matching_nobody_do_not_blame_the_data(self, api: TestClient) -> None:
        """With no candidate admitted, every score is trivially unproducible.
        Saying so would send someone to fix data that is fine."""
        body = api.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_security": 100},
                "filters": {"position_groups": ["DM"], "min_minutes": 99_000},
                "limit": 10,
            },
        ).json()
        assert body["considered"] == 0
        assert body["unavailable_scores"] == []
        assert body["explanation"] == "No player matched these filters."

    def test_a_working_profile_explains_nothing(self, api: TestClient) -> None:
        """An explanation on a page that worked is noise."""
        body = api.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_security": 60, "chance_creation": 40},
                "filters": {"position_groups": ["DM"], "min_minutes": 900},
                "limit": 10,
            },
        ).json()
        assert body["items"]
        assert body["explanation"] is None
        assert body["unavailable_scores"] == []

    def test_a_cross_league_ranking_carries_its_caveat(self, api: TestClient) -> None:
        """Recruitment ranks across competitions, and the specification forbids
        presenting that as strength-adjusted.

        Worth asserting because it silently was not happening: percentile
        populations were grouped by the provider's season id, and FootyStats
        issues one per competition, so every population held a single league.
        """
        body = api.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_security": 100},
                "filters": {"position_groups": ["DM"], "min_minutes": 900},
                "limit": 10,
            },
        ).json()
        competitions = {c["player"]["competition"] for c in body["items"]}
        if len(competitions) > 1:
            assert body["context_caveat"]

    def test_every_candidate_explains_itself(self, api: TestClient) -> None:
        """Section 13: every recommendation must be explainable."""
        body = api.post(
            "/api/v1/recruitment/search",
            json={"weights": {"ball_progression": 100}, "limit": 5},
        ).json()
        for candidate in body["items"]:
            assert candidate["components"]
            assert all(c["label"] for c in candidate["components"])

    def test_weights_need_not_sum_to_one_hundred(self, api: TestClient) -> None:
        body = api.post(
            "/api/v1/recruitment/search",
            json={"weights": {"ball_progression": 3, "ball_security": 1}, "limit": 3},
        )
        assert body.status_code == 200

    def test_an_unknown_score_is_rejected(self, api: TestClient) -> None:
        response = api.post("/api/v1/recruitment/search", json={"weights": {"not_a_score": 100}})
        assert response.status_code == 422

    def test_no_positive_weight_is_rejected(self, api: TestClient) -> None:
        response = api.post("/api/v1/recruitment/search", json={"weights": {"ball_progression": 0}})
        assert response.status_code == 422

    def test_filters_are_applied(self, api: TestClient) -> None:
        body = api.post(
            "/api/v1/recruitment/search",
            json={
                "weights": {"ball_progression": 100},
                "filters": {"max_age": 22, "position_groups": ["CM"]},
                "limit": 10,
            },
        ).json()
        for candidate in body["items"]:
            assert candidate["player"]["age"] <= 22
            assert candidate["player"]["position_group"] == "CM"


class TestReplacement:
    def test_ranks_replacements(self, api: TestClient, a_replaceable_player: dict) -> None:
        body = api.post(
            "/api/v1/replacement/search",
            json={"player_id": a_replaceable_player["player_id"], "limit": 10},
        ).json()
        assert body["items"]
        scores = [c["overall"] for c in body["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_market_fit_is_absent_without_a_budget(
        self, api: TestClient, a_midfielder: dict
    ) -> None:
        """Nothing to fit against, so the component is left out rather than
        invented."""
        body = api.post(
            "/api/v1/replacement/search",
            json={"player_id": a_midfielder["player_id"], "limit": 5},
        ).json()
        assert all(c["market_fit"] is None for c in body["items"])

    def test_market_fit_appears_with_a_budget(
        self, api: TestClient, a_replaceable_player: dict
    ) -> None:
        body = api.post(
            "/api/v1/replacement/search",
            json={
                "player_id": a_replaceable_player["player_id"],
                "filters": {"max_market_value_eur": 20_000_000},
                "limit": 5,
            },
        ).json()
        assert any(c["market_fit"] is not None for c in body["items"])

    def test_the_meaning_is_returned(self, api: TestClient, a_midfielder: dict) -> None:
        body = api.post(
            "/api/v1/replacement/search",
            json={"player_id": a_midfielder["player_id"], "limit": 3},
        ).json()
        assert "not a probability" in body["meaning"]

    def test_an_unknown_player_is_a_404(self, api: TestClient) -> None:
        response = api.post("/api/v1/replacement/search", json={"player_id": "nope"})
        assert response.status_code == 404


class TestOpportunities:
    def test_the_funnel_labels_the_criterion_it_actually_applied(self, api: TestClient) -> None:
        """Regression. The wording lived in one list and the tests in another,
        and they drifted: the minutes filter was reported as "Best role score at
        least 80". A funnel that confidently accounts for the wrong thing is
        worse than no funnel.

        Checked by moving one threshold at a time and seeing which line moves.
        """
        base = api.get("/api/v1/opportunities", params={"min_role_score": 50}).json()
        stricter = api.get("/api/v1/opportunities", params={"min_role_score": 95}).json()

        def removed_by(body: dict, needle: str) -> int:
            step = next(s for s in body["funnel"] if needle in s["criterion"])
            return step["removed"]

        assert removed_by(stricter, "role score") > removed_by(base, "role score")
        # Nothing before it in the screen should have moved.
        assert removed_by(stricter, "Age at most") == removed_by(base, "Age at most")

    def test_the_funnel_accounts_for_everyone(self, api: TestClient) -> None:
        """Each step starts where the previous one finished, so the numbers can
        be read straight down without a gap to wonder about."""
        body = api.get("/api/v1/opportunities").json()
        funnel = body["funnel"]
        assert funnel
        for earlier, later in pairwise(funnel):
            assert later["remaining"] + later["removed"] == earlier["remaining"]
        assert funnel[-1]["remaining"] == body["total"]

    def test_a_thin_result_names_the_binding_constraint(self, api: TestClient) -> None:
        """One survivor out of five thousand is either a strict screen or a
        broken one, and the list alone cannot tell them apart."""
        body = api.get("/api/v1/opportunities").json()
        if body["total"] > 10:
            pytest.skip("the screen is not thin enough to need explaining")
        assert body["explanation"]
        strictest = max(body["funnel"], key=lambda s: s["removed"])
        assert strictest["criterion"] in body["explanation"]

    def test_a_lapsed_contract_is_not_offered_as_expiring(self, api: TestClient) -> None:
        """900 players with contracts recorded as ending years ago passed the
        "expiring within 18 months" filter, because -31 months is under any
        threshold."""
        body = api.get("/api/v1/opportunities", params={"contract_within_months": 18}).json()
        today = date.today()
        for item in body["items"]:
            expires = item["player"].get("contract_expires")
            if expires:
                assert date.fromisoformat(expires) >= today, item["player"]["name"]

    def test_returns_players_meeting_the_criteria(self, api: TestClient) -> None:
        body = api.get(
            "/api/v1/opportunities", params={"max_age": 23, "min_role_score": 70, "limit": 10}
        ).json()
        assert body["items"]
        for entry in body["items"]:
            assert entry["player"]["age"] <= 23
            assert entry["best_role_score"] >= 70

    def test_every_entry_says_why_it_appeared(self, api: TestClient) -> None:
        body = api.get("/api/v1/opportunities", params={"min_role_score": 70}).json()
        for entry in body["items"]:
            assert len(entry["reasons"]) >= 3

    def test_nobody_is_labelled_undervalued(self, api: TestClient) -> None:
        """Section 16 forbids that claim without a validated valuation model."""
        body = api.get("/api/v1/opportunities").json()
        assert "not identified as" in body["disclaimer"]
        assert "undervalued" in body["disclaimer"]
        rendered = str(body["items"]).lower()
        assert "undervalued" not in rendered

    def test_the_criteria_are_stated_back(self, api: TestClient) -> None:
        body = api.get("/api/v1/opportunities", params={"max_age": 21}).json()
        assert any("21" in criterion for criterion in body["criteria"])


class TestReferenceData:
    def test_competitions_are_listed_with_counts(self, api: TestClient) -> None:
        body = api.get("/api/v1/competitions").json()
        assert body
        assert all(c["player_count"] > 0 for c in body)
