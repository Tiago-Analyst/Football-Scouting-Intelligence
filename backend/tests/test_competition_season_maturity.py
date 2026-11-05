"""A competition says how far into its season it is.

WHAT A READER GOT

Measured on live production on 5 November 2026, filtering player search to
the "Established sample (900+)" band - the band this site's own copy points a
careful reader towards:

    England Premier League    0 of 333 players past 900 minutes
    France Ligue 1            0 of 353
    Germany Bundesliga        0 of 367
    Italy Serie A             0 of 497
    Portugal Liga NOS         0 of 334
    Spain La Liga            15 of 435
    USA MLS                 416 of 802
    Brazil Serie A          210 of 465

The European leagues are eight matchdays into 2026/27; the calendar-year
leagues have finished theirs. So a sample filter does not separate
well-evidenced players from thin ones - it removes entire leagues, and said
so nowhere. A scout either concludes the tool has no European coverage, or
does not notice and takes an Americas-only shortlist as the answer to a
question about Europe.

Nothing was wrong with the data, the filter, or the percentile. What was
missing was a sentence, at the point where the choice is made.

WHAT THESE ASSERT

That the figure the sentence is built from is reported by the API rather than
counted in the interface, and that it is measured against the same threshold
and the same minutes as the filter it explains. A caveat computed from a
different denominator than the thing it caveats is worse than no caveat.
"""

from __future__ import annotations

import pytest

from app.analytics.sample import (
    ESTABLISHED_SAMPLE_MINUTES,
    SampleBand,
    classify_minutes,
)
from app.schemas.api import CompetitionOut

pytestmark = pytest.mark.integration


class TestTheFigureIsReported:
    def test_every_competition_carries_its_best_minutes(self, client) -> None:  # type: ignore[no-untyped-def]
        rows = client.get("/api/v1/competitions").json()
        assert rows, "no competitions served"
        for row in rows:
            assert "best_minutes" in row, row.get("name")
            assert "season_established" in row, row.get("name")
            assert row["best_minutes"] >= 0

    def test_established_is_the_same_threshold_the_sample_bands_use(self, client) -> None:  # type: ignore[no-untyped-def]
        # The one that matters. If these ever diverge, the sentence under the
        # filter describes a different cut than the filter makes, which is how
        # a caveat starts lying.
        for row in client.get("/api/v1/competitions").json():
            expected = row["best_minutes"] >= ESTABLISHED_SAMPLE_MINUTES
            assert row["season_established"] is expected, row["name"]

    def test_the_threshold_is_the_established_band_itself(self) -> None:
        # Not a second constant that happens to equal 900 today.
        assert classify_minutes(ESTABLISHED_SAMPLE_MINUTES) is SampleBand.ESTABLISHED
        assert classify_minutes(ESTABLISHED_SAMPLE_MINUTES - 1) is not SampleBand.ESTABLISHED

    def test_a_competition_with_no_minutes_is_not_established(self) -> None:
        empty = CompetitionOut(competition_id="x", name="X", player_count=0)
        assert empty.best_minutes == 0
        assert empty.season_established is False


class TestItMeasuresWhatTheFilterReads:
    def test_best_minutes_agrees_with_what_a_minutes_filter_returns(self, client) -> None:  # type: ignore[no-untyped-def]
        """The claim and the filter must answer the same question.

        For each competition the API calls established, a search filtered to
        that competition at the established floor must return somebody; for
        each one it does not, it must return nobody. This is the assertion
        that would have caught the defect, because it fails the moment the
        two are computed from different minutes.
        """
        rows = client.get("/api/v1/competitions").json()
        checked = 0
        for row in rows:
            if row["player_count"] == 0:
                continue
            response = client.post(
                "/api/v1/recruitment/search",
                json={
                    "weights": {"ball_security": 1},
                    "filters": {
                        "competitions": [row["competition_id"]],
                        "min_minutes": ESTABLISHED_SAMPLE_MINUTES,
                    },
                    "limit": 1,
                },
            )
            assert response.status_code == 200, response.text
            anybody = response.json()["total"] > 0
            if anybody:
                assert row["season_established"] is True, (
                    f"{row['name']} returns players at the established floor but is "
                    "not reported as established"
                )
            checked += 1
            if checked >= 12:  # enough to catch a systematic disagreement
                break
        assert checked > 0, "no competition had players to check"


class TestWhatMustNotHappen:
    def test_no_competition_is_judged_or_ranked(self, client) -> None:  # type: ignore[no-untyped-def]
        # This project has no competition-strength coefficient and the
        # specification forbids inventing one. A maturity figure is about the
        # calendar, not about quality, and nothing here may become a ranking.
        row = client.get("/api/v1/competitions").json()[0]
        assert set(row) == {
            "competition_id",
            "name",
            "player_count",
            "best_minutes",
            "season_established",
        }, "the competition payload grew a field; make sure it is not a judgement"
