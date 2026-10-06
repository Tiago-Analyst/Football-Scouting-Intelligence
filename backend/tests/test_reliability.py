"""Reliability-aware ordering: what it must do, and what it must never do.

Every test here is a rule the audit's findings turned into a requirement. The
two that matter most pull in opposite directions, and both have to hold: a
28-minute player must stop topping a list on volatile per-90 figures, and a
genuinely outstanding short-sample player must still be able to beat a
mediocre established one. A rule that only satisfies one of them is a gate
wearing a different hat.
"""

from __future__ import annotations

import pytest

from app.analytics.reliability import (
    FULL_EVIDENCE_MINUTES,
    RankingAdjustment,
    evidence_weight,
    rank_by_evidence,
    shrink,
)
from app.analytics.sample import ESTABLISHED_SAMPLE_MINUTES


class TestEvidenceWeight:
    def test_a_full_season_is_ranked_on_its_own_terms(self) -> None:
        assert evidence_weight(ESTABLISHED_SAMPLE_MINUTES) == 1.0

    def test_more_than_a_full_season_is_not_rewarded_further(self) -> None:
        # Otherwise minutes would keep tilting the order long past the point
        # where the per-90 has settled, and an ever-present player would
        # outrank a better one for being ever-present.
        assert evidence_weight(3000) == evidence_weight(ESTABLISHED_SAMPLE_MINUTES)

    def test_it_borrows_the_established_threshold_rather_than_inventing_one(self) -> None:
        assert FULL_EVIDENCE_MINUTES == ESTABLISHED_SAMPLE_MINUTES

    @pytest.mark.parametrize(
        ("minutes", "expected"),
        [(0, 0.0), (28, 28 / 900), (180, 0.2), (450, 0.5), (900, 1.0)],
    )
    def test_it_rises_with_minutes(self, minutes: int, expected: float) -> None:
        assert evidence_weight(minutes) == pytest.approx(expected)

    def test_unknown_minutes_weigh_nothing_but_do_not_exclude(self) -> None:
        # Same reasoning as the sample band: without knowing the sample, the
        # honest claim is the weakest one. The caller still gets a number.
        assert evidence_weight(None) == 0.0
        assert shrink(90.0, mean=60.0, weight=evidence_weight(None)) == 60.0


class TestShrinkage:
    def test_a_full_season_is_left_exactly_alone(self) -> None:
        assert shrink(94.0, mean=60.0, weight=1.0) == 94.0

    def test_no_evidence_lands_on_the_population_mean(self) -> None:
        assert shrink(94.0, mean=60.0, weight=0.0) == 60.0

    def test_a_below_average_score_is_pulled_up_not_down(self) -> None:
        # Shrinkage is toward the middle, not downward. A short sample is not
        # evidence of being bad either.
        assert shrink(20.0, mean=60.0, weight=0.5) == 40.0


class TestTheCasesTheAuditFound:
    """Named after the real rows that prompted this."""

    def test_a_28_minute_player_stops_topping_a_centre_backs_list(self) -> None:
        # Gora Diouf, 28 minutes, similarity 96.5, ranked first ahead of
        # established defenders. He stays in the results; he stops leading.
        #
        # Measured against a realistic field rather than a pair: a real
        # similarity search ranks hundreds, and the population he is pulled
        # toward is made of them, not of himself.
        field = [65.0] * 20
        values = [96.5, 70.0, *field]
        played = [28, 1430, *([1200] * 20)]
        diouf, established, *_ = rank_by_evidence(values, played)
        assert diouf.ranked < established.ranked
        assert diouf.raw == 96.5, "the index itself must not be rewritten"

    def test_a_short_sample_outlier_cannot_inflate_its_own_target(self) -> None:
        # The failure mode that leave-one-out exists to prevent. With the
        # candidate inside its own mean, a lone high outlier is shrunk toward
        # a figure it created and barely moves.
        diouf, established = rank_by_evidence([96.5, 70.0], [28, 1430])
        assert diouf.mean == 70.0
        assert established.mean == 96.5

    def test_a_much_stronger_short_sample_player_still_wins(self) -> None:
        # The opposite failure. 95 from 450 minutes is a real signal and must
        # survive; shrinking toward zero instead of toward the mean would bury
        # it, which is why that approach was rejected.
        strong_short, weak_established = rank_by_evidence([95.0, 50.0], [450, 1800])
        assert strong_short.ranked > weak_established.ranked

    def test_13_minutes_remains_eligible(self) -> None:
        # Romeo Vermant ranked fifth on 13 minutes. Eligibility is untouched:
        # he is still returned, still scored, still visible.
        results = rank_by_evidence([74.3, 60.0], [13, 1500])
        assert len(results) == 2
        assert results[0].raw == 74.3

    def test_two_equal_scores_are_separated_by_evidence(self) -> None:
        # Against a field averaging 60, the same raw 80 is worth less from
        # 180 minutes than from 1,800. With no field at all there is nothing
        # to shrink toward and the two stay level, which is also correct.
        field = [60.0] * 10
        short, long, *_ = rank_by_evidence([80.0, 80.0, *field], [180, 1800, *([1200] * 10)])
        assert long.ranked > short.ranked

    def test_established_players_keep_their_raw_order(self) -> None:
        # Past a full season the weight is identical, so ordering among
        # established players is exactly the ordering of their raw scores.
        # Minutes must stop mattering once there is enough of them.
        a, b = rank_by_evidence([70.0, 75.0], [1000, 2200])
        assert a.ranked < b.ranked
        assert a.weight == b.weight == 1.0

    def test_raw_values_are_never_rewritten(self) -> None:
        values = [96.5, 88.0, 12.0]
        results = rank_by_evidence(values, [28, 450, 2000])
        assert [r.raw for r in results] == values

    def test_it_is_deterministic(self) -> None:
        first = rank_by_evidence([90.0, 60.0, 30.0], [100, 900, 450])
        second = rank_by_evidence([90.0, 60.0, 30.0], [100, 900, 450])
        assert [r.ranked for r in first] == [r.ranked for r in second]


class TestExplaining:
    def test_an_adjusted_candidate_can_say_why(self) -> None:
        adjustment = rank_by_evidence([96.5, 70.0], [28, 1430])[0]
        sentence = adjustment.explain(minutes=28, noun="similarity")
        assert sentence is not None
        assert "28 minutes" in sentence
        assert "unchanged" in sentence

    def test_an_unadjusted_candidate_says_nothing(self) -> None:
        # A full-season player was not moved, so there is nothing to explain
        # and a sentence would be noise.
        adjustment = RankingAdjustment(raw=80.0, ranked=80.0, weight=1.0, mean=60.0)
        assert adjustment.explain(minutes=1800) is None

    def test_mismatched_inputs_are_refused(self) -> None:
        with pytest.raises(ValueError):
            rank_by_evidence([1.0, 2.0], [100])
