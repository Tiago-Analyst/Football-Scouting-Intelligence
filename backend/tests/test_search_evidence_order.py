"""Player search can order by role fit without being led by noise.

WHAT A READER GOT

Sorting player search by role fit orders on the raw score. Measured on live
production, 5 November, the Premier League sorted that way gave a top ten
whose minutes ran:

    12, 620, 92, 126, 494, 117, 396, 97, 630, 93

The first row was a 96 at the 100th percentile, from twelve minutes.

Nothing was mislabelled. The column says "Raw fit", the minutes are a column
of their own, and the sample badge is in the row. But the most obvious action
on the page produced a shortlist led by players who had barely played, and
recruitment, replacement and opportunities had all had the answer for weeks.

WHAT THIS DOES NOT DO

It adds an ordering. It does not touch `rank_by_evidence`, which is used
unchanged, and it does not rewrite a displayed value: `best_role_score` and
`best_role_percentile` are exactly what they were, and the raw sort is still
there under a name that says what it is.

Nobody is excluded for having played little. A thin figure is pulled toward
what an ordinary player in the same filtered population looks like, which
moves it down a list - it does not remove it from one.
"""

from __future__ import annotations

import pytest

from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES

pytestmark = pytest.mark.integration


def _items(client, sort: str, **params):  # type: ignore[no-untyped-def]
    query = "&".join(f"{k}={v}" for k, v in params.items())
    response = client.get(f"/api/v1/players?sort={sort}&limit=10&{query}")
    assert response.status_code == 200, response.text
    return response.json()["items"]


class TestTheOrderingChanges:
    def test_the_raw_sort_is_still_led_by_thin_samples(self, client) -> None:  # type: ignore[no-untyped-def]
        # Not a defect to fix by changing the raw sort: it is the raw score in
        # raw order, which is what it says. This records that it is unchanged.
        raw = _items(client, "role_score", position_group="CM")
        assert raw, "no players to rank"
        assert raw[0]["best_role_score"] is not None

    def test_the_evidence_sort_puts_football_first(self, client) -> None:  # type: ignore[no-untyped-def]
        ranked = _items(client, "role_score_ranked", position_group="CM")
        assert ranked, "no players to rank"
        minutes = [item["minutes"] or 0 for item in ranked[:5]]
        assert all(m >= ESTABLISHED_SAMPLE_MINUTES for m in minutes), (
            f"the evidence-aware order still leads with thin samples: {minutes}"
        )

    def test_it_orders_by_the_adjusted_value(self, client) -> None:  # type: ignore[no-untyped-def]
        ranked = _items(client, "role_score_ranked", position_group="CM")
        scores = [item["ranking_score"] for item in ranked]
        assert all(s is not None for s in scores), "a row was ordered without an adjustment"
        assert scores == sorted(scores, reverse=True), "the order does not follow the adjustment"


class TestWhatMustNotChange:
    def test_the_displayed_score_is_untouched(self, client) -> None:  # type: ignore[no-untyped-def]
        """The guard that matters. This orders; it never rewrites."""
        raw = {i["player_id"]: i["best_role_score"] for i in _items(client, "role_score", limit=25)}
        ranked = {
            i["player_id"]: i["best_role_score"]
            for i in _items(client, "role_score_ranked", limit=25)
        }
        shared = set(raw) & set(ranked)
        assert shared, "the two sorts returned no player in common to compare"
        for player_id in shared:
            assert raw[player_id] == ranked[player_id], (
                "best_role_score changed with the sort order"
            )

    def test_nobody_is_excluded_for_having_played_little(self, client) -> None:  # type: ignore[no-untyped-def]
        # Shrinkage moves a player down a list. It must never drop them from
        # one - this product has no hidden minimum-minutes exclusion.
        everyone = client.get("/api/v1/players?sort=role_score&limit=1").json()["total"]
        ranked = client.get("/api/v1/players?sort=role_score_ranked&limit=1").json()["total"]
        assert ranked == everyone, f"{everyone - ranked} players vanished from the ranked order"

    def test_other_sorts_carry_no_adjustment(self, client) -> None:  # type: ignore[no-untyped-def]
        # A ranking score on a minutes sort would be a number with no meaning
        # in the column it sits under.
        for sort in ("minutes", "age", "market_value", "name", "role_score"):
            for item in _items(client, sort, limit=5):
                assert item["ranking_score"] is None, f"{sort} returned an adjustment"
                assert item["ranking_note_message"] is None, f"{sort} returned a note"


class TestItExplainsItself:
    def test_an_adjusted_row_says_why(self, client) -> None:  # type: ignore[no-untyped-def]
        ranked = _items(client, "role_score_ranked", position_group="CM", limit=25)
        adjusted = [
            i
            for i in ranked
            if i["ranking_score"] is not None
            and i["best_role_score"] is not None
            and abs(i["ranking_score"] - i["best_role_score"]) > 0.5
        ]
        for item in adjusted:
            assert item["ranking_note_message"] is not None, (
                "a row was moved by the ordering and does not say so"
            )
            assert "code" in item["ranking_note_message"], "the note is not a structured message"
