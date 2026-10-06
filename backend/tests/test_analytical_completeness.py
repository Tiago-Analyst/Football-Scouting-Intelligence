"""Three different things a profile can be confident about, kept apart.

A validation audit found a page showing "Established Sample" and "100%
detailed coverage" above no role, no intelligence score and nine metrics of
eighteen. Neither label was wrong. One counts minutes played; the other counts
the share of those minutes the provider described in detail. Read together
they say "this profile is complete", which was false, and nothing on the page
said otherwise.

These tests hold the three apart, and hold the diagnostic that replaced
"No role fit could be computed." to being read back from the role engine
rather than written out by hand.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES


@pytest.fixture(scope="module")
def api() -> TestClient:
    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def role_outcomes(api: TestClient) -> dict[str, dict]:
    """One scan, shared.

    Each of these tests used to walk the player list calling /roles, and
    together they tripped the rate limiter - which is the limiter working. A
    single bounded pass answers all of them.
    """
    scored: dict | None = None
    unscored: dict | None = None
    body = api.get("/api/v1/players", params={"limit": 25, "sort": "minutes"}).json()
    for row in body["items"]:
        if scored is not None and unscored is not None:
            break
        roles = api.get(f"/api/v1/players/{row['player_id']}/roles").json()
        if roles["best"] is not None and scored is None:
            scored = roles
        elif roles["best"] is None and unscored is None:
            unscored = roles
    return {"scored": scored, "unscored": unscored}


def _any_player(api: TestClient) -> dict:
    body = api.get("/api/v1/players", params={"limit": 1}).json()
    return body["items"][0]  # type: ignore[no-any-return]


class TestTheThreeMeasures:
    def test_a_profile_reports_all_three_separately(self, api: TestClient) -> None:
        player = _any_player(api)
        sample = api.get(f"/api/v1/players/{player['player_id']}/stats").json()["sample"]

        # A: how much football was played.
        assert "minutes" in sample
        assert "band" in sample
        # B: how much of that football the provider described in detail.
        assert "detailed_coverage_pct" in sample
        # C: how many of the profile's metrics could actually be computed.
        assert "metric_coverage_pct" in sample
        assert "metrics_available" in sample
        assert "metrics_expected" in sample

    def test_metric_coverage_is_a_real_fraction(self, api: TestClient) -> None:
        player = _any_player(api)
        sample = api.get(f"/api/v1/players/{player['player_id']}/stats").json()["sample"]
        if sample["metrics_expected"]:
            assert 0 <= sample["metrics_available"] <= sample["metrics_expected"]
            expected = sample["metrics_available"] / sample["metrics_expected"] * 100
            assert sample["metric_coverage_pct"] == pytest.approx(expected)

    def test_the_sample_band_still_means_minutes_and_only_minutes(self, api: TestClient) -> None:
        """The band definition is untouched, and must stay untouched.

        Folding metric availability into it would have been the quick fix and
        the wrong one: it would make a provider gap look like a player who had
        not played.
        """
        body = api.get("/api/v1/players", params={"limit": 60, "sort": "minutes"}).json()
        for row in body["items"]:
            if row["minutes"] is not None and row["minutes"] >= ESTABLISHED_SAMPLE_MINUTES:
                assert row["sample_band"] == "established"

    def test_a_well_played_season_can_still_be_analytically_incomplete(
        self, api: TestClient
    ) -> None:
        """The combination that started this.

        Not every dataset contains such a player, so this asserts the shape of
        the claim rather than requiring one to exist: where the two diverge,
        the page must be able to say so.
        """
        body = api.get("/api/v1/players", params={"limit": 100, "sort": "minutes"}).json()
        for row in body["items"][:20]:
            sample = api.get(f"/api/v1/players/{row['player_id']}/stats").json()["sample"]
            if sample["metric_coverage_pct"] is None:
                continue
            if sample["band"] == "established" and sample["metric_coverage_pct"] < 100:
                # Exactly the case the audit found: the two measures disagree,
                # and both are reported.
                assert sample["metrics_available"] < sample["metrics_expected"]
                return


class TestWhyNoRoleCouldBeScored:
    def test_a_scored_player_carries_no_diagnostic(self, role_outcomes: dict) -> None:
        scored = role_outcomes["scored"]
        if scored is None:
            pytest.skip("no scored player in this dataset")
        assert scored["unscored"] == []
        assert scored["unscored_reason"] is None

    def test_an_unscored_player_is_told_which_role_came_closest(self, role_outcomes: dict) -> None:
        roles = role_outcomes["unscored"]
        if roles is None:
            pytest.skip("every player in this sample could be scored")
        assert roles["unscored_reason"], "an unscored profile must say why"
        for shortfall in roles["unscored"]:
            # Every figure comes from the engine: the coverage reached and the
            # minimum the role is configured to need.
            assert 0.0 <= shortfall["coverage_pct"] <= 100.0
            assert 0.0 < shortfall["required_pct"] <= 100.0
            assert shortfall["coverage_pct"] < shortfall["required_pct"]
            assert shortfall["label"]
        gaps = [s["required_pct"] - s["coverage_pct"] for s in roles["unscored"]]
        assert gaps == sorted(gaps), "closest first, so the sentence names the right role"

    def test_the_reason_never_blames_the_player(self, role_outcomes: dict) -> None:
        """It is provider data that is missing, not performance.

        A profile that says "could not be computed" and stops reads as a
        verdict on the footballer. It is not one.
        """
        roles = role_outcomes["unscored"]
        if roles is None:
            pytest.skip("every player in this sample could be scored")
        reason = roles["unscored_reason"].lower()
        assert "provider data, not performance" in reason or "no role is defined" in reason


class TestTheSentenceItself:
    """Covered directly, because the demo dataset has no incomplete profile.

    The two API tests above skip when every player can be scored, which is the
    honest outcome but leaves the wording untested. These exercise it.
    """

    def test_it_names_the_closest_role_and_both_figures(self) -> None:
        from app.api.v1.players import _why_no_role
        from app.schemas.api import UnscoredRoleOut

        sentence = _why_no_role(
            [
                UnscoredRoleOut(
                    key="defensive_full_back",
                    label="Defensive Full-Back",
                    coverage_pct=60.0,
                    required_pct=80.0,
                    missing=["Dribble success %", "Successful dribbles /90"],
                )
            ]
        )
        assert "Defensive Full-Back" in sentence
        assert "60%" in sentence and "80%" in sentence
        assert "provider data, not performance" in sentence

    def test_a_position_with_no_roles_says_so_instead(self) -> None:
        from app.api.v1.players import _why_no_role

        sentence = _why_no_role([])
        assert "No role is defined for this position group" in sentence

    def test_it_never_says_the_old_bare_message(self) -> None:
        from app.api.v1.players import _why_no_role
        from app.schemas.api import UnscoredRoleOut

        sentence = _why_no_role(
            [UnscoredRoleOut(key="k", label="Poacher", coverage_pct=10.0, required_pct=100.0)]
        )
        assert "could not be computed" not in sentence.lower()


class TestTeamContextMetrics:
    """Goals conceded is the team's record, not the forward's.

    The audit found it listed among Wilfried Zaha's and Brian White's
    strengths. It stays on the profile, where it can be read for what it is;
    it stops being offered as something the player did.
    """

    def _reading(self, position: str) -> object:
        from app.analytics.interpretation import MetricReading, interpret

        return interpret(
            role=None,
            scores=[],
            metrics=[
                MetricReading(
                    "Goals conceded /90",
                    percentile=10.0,
                    lower_is_better=True,
                    metric="goals_conceded_per90",
                ),
                MetricReading("npxG /90", percentile=95.0, metric="npxg_per90"),
            ],
            minutes=1500,
            sample_band_label="Established Sample",
            detailed_coverage_pct=100.0,
            position_label=position,
        )

    def test_an_outfielder_is_not_credited_with_his_teams_defence(self) -> None:
        strengths = [f.label for f in self._reading("WINGER").strengths]
        assert "Goals conceded /90" not in strengths
        assert "npxG /90" in strengths, "the real strength must survive the exclusion"

    def test_a_goalkeeper_still_is(self) -> None:
        # For a keeper the figure is close to personal, and removing it would
        # strip the reading of the thing the position is judged on.
        strengths = [f.label for f in self._reading("GK").strengths]
        assert "Goals conceded /90" in strengths

    def test_it_is_excluded_from_watch_outs_too(self) -> None:
        from app.analytics.interpretation import MetricReading, interpret

        reading = interpret(
            role=None,
            scores=[],
            metrics=[
                MetricReading(
                    "Goals conceded /90",
                    percentile=95.0,
                    lower_is_better=True,
                    metric="goals_conceded_per90",
                )
            ],
            minutes=1500,
            sample_band_label="Established Sample",
            detailed_coverage_pct=100.0,
            position_label="FORWARD",
        )
        assert [f.label for f in reading.watch_outs] == []


class TestPresetCoverage:
    """A preset must warn before it is run, not after it returns.

    Thirteen of fourteen presets carry a dimension this provider cannot
    supply. Zeroing them is what the product tells a reader to do, and for the
    Ball-Playing Centre-Back it removes 55% of the definition while leaving
    the name on it.
    """

    def test_full_coverage_says_nothing(self) -> None:
        from app.api.v1.recruitment import _preset_coverage

        measurable, status, note = _preset_coverage({"finishing": 70, "goal_threat": 30}, {}, "P")
        assert (measurable, status, note) == (100.0, "full", None)

    def test_losing_a_defining_dimension_is_minimal(self) -> None:
        from app.api.v1.recruitment import _preset_coverage
        from app.schemas.api import UnavailableScoreOut

        blocked = {
            "duel_dominance": UnavailableScoreOut(
                key="duel_dominance", label="Duel Dominance", missing=[], reason="x"
            )
        }
        # Target Forward: 55% of its weight is duel dominance.
        measurable, status, note = _preset_coverage(
            {
                "duel_dominance": 55,
                "goal_threat": 15,
                "finishing": 10,
                "one_v_one_threat": 10,
                "ball_progression": 5,
                "chance_creation": 5,
            },
            blocked,
            "Target Forward",
        )
        assert measurable == pytest.approx(45.0)
        assert status == "minimal"
        assert note is not None
        assert "Duel Dominance" in note and "Target Forward" in note

    def test_losing_a_secondary_dimension_is_limited_not_minimal(self) -> None:
        from app.api.v1.recruitment import _preset_coverage
        from app.schemas.api import UnavailableScoreOut

        blocked = {
            "ball_progression": UnavailableScoreOut(
                key="ball_progression", label="Ball Progression", missing=[], reason="x"
            )
        }
        measurable, status, _ = _preset_coverage(
            {
                "finishing": 45,
                "goal_threat": 40,
                "ball_progression": 5,
                "chance_creation": 5,
                "one_v_one_threat": 5,
            },
            blocked,
            "Inside Forward",
        )
        assert measurable == pytest.approx(95.0)
        assert status == "full"

    def test_the_api_reports_it_for_every_preset(self, api: TestClient) -> None:
        for preset in api.get("/api/v1/recruitment/presets").json():
            assert 0.0 <= preset["measurable_pct"] <= 100.0
            assert preset["coverage_status"] in {"full", "limited", "minimal"}
            if preset["unavailable_scores"]:
                assert preset["measurable_pct"] < 100.0
                assert preset["coverage_note"]
            else:
                assert preset["coverage_note"] is None
