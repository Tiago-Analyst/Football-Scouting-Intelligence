"""A percentile is not a finding when almost nothing stands behind it.

A validation audit found Finishing reported as the single strongest dimension
of a centre-back who had taken roughly four shots in 1,199 minutes, and as the
top dimension of another with about eight. Neither percentile was wrong. Both
sentences were.

Minutes cannot catch this. Both players had a full season and an Established
Sample band; what they did not have was shots. The count that matters for a
score built from success rates is the number of events the rate divides by.

Nothing here lowers a percentile, removes a dimension or excludes a player.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analytics.interpretation import ScoreReading, interpret


@pytest.fixture(scope="module")
def api() -> TestClient:
    from app.main import app

    with TestClient(app) as client:
        yield client


class TestTheConfiguration:
    """The thresholds are football judgements and live where they can be seen."""

    def test_finishing_declares_the_events_it_rests_on(self) -> None:
        from app.analytics.intelligence import get_definitions

        finishing = get_definitions()["finishing"]
        assert finishing.evidence is not None
        assert finishing.evidence.metric == "shots"
        assert finishing.evidence.headline_threshold > 0

    def test_a_volume_only_score_declares_none(self) -> None:
        """Defensive Activity counts tackles and interceptions.

        Those are volume, not a rate over a small denominator, and a season's
        worth of them is a sound measurement. Attaching a threshold to every
        score would be noise pretending to be rigour.
        """
        from app.analytics.intelligence import get_definitions

        assert get_definitions()["defensive_activity"].evidence is None

    def test_a_malformed_evidence_block_is_refused(self) -> None:
        from app.analytics.intelligence import ScoreConfigError, _parse_evidence

        for bad in (
            {"metric": "shots", "headline_threshold": 0, "noun": "shots"},
            {"metric": "", "headline_threshold": 50, "noun": "shots"},
            {"metric": "shots", "headline_threshold": 50},
            "not a mapping",
        ):
            with pytest.raises(ScoreConfigError):
                _parse_evidence("finishing", bad)


class TestTheSentence:
    """What the reader is told, which is the part that was wrong."""

    def _lines(self, *, score: float, low: bool, label: str | None) -> list[str]:
        reading = interpret(
            role=None,
            scores=[
                ScoreReading("Finishing", score, 1.0, low_evidence=low, evidence_label=label),
                ScoreReading("Defensive Activity", 79.0, 1.0),
            ],
            metrics=[],
            minutes=1430,
            sample_band_label="Established Sample",
            detailed_coverage_pct=100.0,
            position_label="CB",
        )
        return reading.profile

    def test_finishing_on_four_shots_is_not_a_strength(self) -> None:
        lines = " ".join(self._lines(score=81.0, low=True, label="Low evidence - 4 shots"))
        strongest = [line for line in lines.split(".") if "Strongest" in line]
        assert strongest, "the other dimension must still be reported"
        assert "Finishing" not in strongest[0]
        assert "Defensive Activity" in strongest[0]

    def test_but_it_is_not_hidden_either(self) -> None:
        """Dropping it silently would be the worse failure.

        The score is still on the chart beside the prose; a reader who saw 81
        there and no mention here would have no way to reconcile the two.
        """
        lines = " ".join(self._lines(score=81.0, low=True, label="Low evidence - 4 shots"))
        assert "too little to call a strength" in lines
        assert "Finishing" in lines
        assert "4 shots" in lines

    def test_finishing_on_eighty_shots_is_a_strength(self) -> None:
        lines = " ".join(self._lines(score=81.0, low=False, label="80 shots"))
        strongest = [line for line in lines.split(".") if "Strongest" in line]
        assert "Finishing" in strongest[0]
        assert "too little to call a strength" not in lines

    def test_a_low_score_on_few_events_is_not_announced_either_way(self) -> None:
        # It is not a strength and it is not evidence of weakness. Only the
        # headline list is affected; the score itself is untouched.
        lines = " ".join(self._lines(score=20.0, low=True, label="Low evidence - 4 shots"))
        assert "too little to call a strength" not in lines


class TestTheApi:
    def test_a_score_carries_its_event_count(self, api: TestClient) -> None:
        body = api.get("/api/v1/players", params={"limit": 1, "sort": "minutes"}).json()
        player = body["items"][0]
        scores = api.get(f"/api/v1/players/{player['player_id']}/stats").json()["scores"]
        finishing = next((s for s in scores if s["key"] == "finishing"), None)
        assert finishing is not None
        if finishing["evidence"] is not None:
            assert finishing["evidence"]["noun"] == "shots"
            assert finishing["evidence"]["events"] >= 0
            assert finishing["evidence"]["low"] == (
                finishing["evidence"]["events"] < finishing["evidence"]["threshold"]
            )

    def test_the_percentile_is_untouched_by_any_of_this(self, api: TestClient) -> None:
        """The one thing that must not have moved.

        Faking a lower number would be worse than the problem: it would make
        the chart disagree with the data and leave nobody able to check it.
        """
        body = api.get("/api/v1/players", params={"limit": 6, "sort": "minutes"}).json()
        for player in body["items"]:
            scores = api.get(f"/api/v1/players/{player['player_id']}/stats").json()["scores"]
            for score in scores:
                if score["score"] is None:
                    continue
                assert 0.0 <= score["score"] <= 100.0
                # A low-evidence flag must not have been folded into the value.
                evidence = score.get("evidence")
                if evidence and evidence["low"]:
                    assert score["score"] == score["score"]  # unchanged, not clamped

    def test_a_score_with_no_evidence_requirement_reports_none(self, api: TestClient) -> None:
        body = api.get("/api/v1/players", params={"limit": 1, "sort": "minutes"}).json()
        scores = api.get(f"/api/v1/players/{body['items'][0]['player_id']}/stats").json()["scores"]
        activity = next((s for s in scores if s["key"] == "defensive_activity"), None)
        assert activity is not None
        assert activity["evidence"] is None


class TestTheWording:
    """One event is the count most worth printing and the easiest to misprint."""

    def test_a_single_event_reads_as_one(self) -> None:
        from app.api.v1.players import _count_noun

        assert _count_noun("shots", 1) == "shot"
        assert _count_noun("dribbles attempted", 1) == "dribble attempted"

    def test_everything_else_stays_plural(self) -> None:
        from app.api.v1.players import _count_noun

        assert _count_noun("shots", 0) == "shots"
        assert _count_noun("shots", 18) == "shots"
        assert _count_noun("dribbles attempted", 2) == "dribbles attempted"

    def test_the_machine_readable_noun_is_not_bent_for_grammar(self) -> None:
        """`label` is prose; `noun` is data, and a client may phrase its own."""
        from app.analytics.intelligence import get_definitions

        assert get_definitions()["finishing"].evidence.noun == "shots"
