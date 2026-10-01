"""The reading of a profile, which must never say more than the numbers do.

Every sentence this module produces is a threshold applied to a percentile the
reader can see above it. These tests are mostly about the things it must
refuse to say: that an unsupplied metric is a weakness, that a role whose
definition is half missing describes the player, that a statistic about events
is evidence about intentions.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.analytics.interpretation import (
    MAX_FINDINGS,
    NOT_CAPTURED,
    MetricReading,
    RoleReading,
    ScoreReading,
    interpret,
)


def read(**overrides: object):  # type: ignore[no-untyped-def]
    """A profile with nothing remarkable in it, for one thing to be changed."""
    defaults: dict[str, object] = {
        "role": None,
        "scores": [],
        "metrics": [],
        "minutes": 1800,
        "sample_band_label": "Established sample",
        "detailed_coverage_pct": 92.0,
        "position_label": "CB",
    }
    defaults.update(overrides)
    return interpret(**defaults)  # type: ignore[arg-type]


class TestWhichMetricsAreNamed:
    def test_a_high_percentile_is_a_strength(self) -> None:
        reading = read(metrics=[MetricReading("Interceptions /90", 91.0)])
        assert [f.label for f in reading.strengths] == ["Interceptions /90"]
        assert reading.strengths[0].reading == "strong statistical output"
        assert not reading.watch_outs

    def test_a_low_percentile_is_a_watch_out(self) -> None:
        reading = read(metrics=[MetricReading("Key passes /90", 12.0)])
        assert [f.label for f in reading.watch_outs] == ["Key passes /90"]
        assert not reading.strengths

    def test_the_middle_is_not_mentioned_at_all(self) -> None:
        """A profile where everything is average should say nothing about any
        of it, rather than listing the least average thing as a strength."""
        reading = read(
            metrics=[
                MetricReading("Passes /90", 55.0),
                MetricReading("Tackles /90", 48.0),
                MetricReading("Duels won /90", 62.0),
            ]
        )
        assert reading.strengths == []
        assert reading.watch_outs == []

    def test_an_inverse_metric_is_read_the_right_way_round(self) -> None:
        """Rarely dispossessed is an 8th percentile on the metric and a
        strength. Reading the printed number would have called it a weakness -
        the same mistake the percentile bar's colour was making."""
        reading = read(metrics=[MetricReading("Dispossessed /90", 8.0, lower_is_better=True)])
        assert [f.label for f in reading.strengths] == ["Dispossessed /90"]
        assert reading.strengths[0].percentile == pytest.approx(92.0)
        assert not reading.watch_outs

    def test_an_inverse_metric_at_the_wrong_end_is_a_watch_out(self) -> None:
        reading = read(metrics=[MetricReading("Dispossessed /90", 95.0, lower_is_better=True)])
        assert [f.label for f in reading.watch_outs] == ["Dispossessed /90"]
        assert reading.watch_outs[0].percentile == pytest.approx(5.0)

    def test_the_strongest_evidence_leads(self) -> None:
        reading = read(
            metrics=[
                MetricReading("Blocks /90", 74.0),
                MetricReading("Interceptions /90", 96.0),
                MetricReading("Clearances /90", 85.0),
            ]
        )
        assert [f.label for f in reading.strengths] == [
            "Interceptions /90",
            "Clearances /90",
            "Blocks /90",
        ]

    def test_watch_outs_lead_with_the_weakest(self) -> None:
        reading = read(
            metrics=[
                MetricReading("Key passes /90", 30.0),
                MetricReading("Crosses /90", 4.0),
            ]
        )
        assert [f.label for f in reading.watch_outs] == ["Crosses /90", "Key passes /90"]

    def test_a_long_list_is_cut_to_something_readable(self) -> None:
        """Fifteen strengths is no strengths."""
        reading = read(metrics=[MetricReading(f"Metric {i} /90", 80.0 + i) for i in range(15)])
        assert len(reading.strengths) == MAX_FINDINGS

    def test_the_claim_never_outruns_the_percentile(self) -> None:
        firm = read(metrics=[MetricReading("A", 94.0)]).strengths[0]
        milder = read(metrics=[MetricReading("A", 72.0)]).strengths[0]
        assert firm.reading == "strong statistical output"
        assert milder.reading == "above-average output"


class TestWhatItRefusesToSay:
    def test_an_unsupplied_metric_is_not_a_weakness(self) -> None:
        """Absent is not nought. A metric the provider does not collect says
        nothing about the player and must not be read as poor output."""
        reading = read(
            metrics=[
                MetricReading(
                    "Progressive passes /90",
                    None,
                    unavailable_reason="Not supplied by the provider",
                )
            ]
        )
        assert reading.watch_outs == []
        assert reading.strengths == []
        assert any("Progressive passes /90" in line for line in reading.unavailable)

    def test_a_thin_role_describes_what_was_measured_not_the_role(self) -> None:
        reading = read(
            role=RoleReading(
                label="Ball-Playing Centre-Back",
                score=78.0,
                percentile=88.0,
                coverage=0.6,
                is_limited=True,
                missing=("Progressive passes /90",),
            )
        )
        joined = " ".join(reading.profile)
        assert "on the part of that definition the data covers" in joined
        assert "Best fit among the roles evaluated is" not in joined

    def test_a_complete_role_is_described_plainly(self) -> None:
        reading = read(
            role=RoleReading(label="Defensive Stopper", score=81.0, percentile=93.0, coverage=1.0)
        )
        assert "Best fit among the roles evaluated is Defensive Stopper" in reading.profile[0]

    def test_a_role_that_could_not_be_ranked_says_so(self) -> None:
        reading = read(role=RoleReading(label="Defensive Stopper", score=81.0, percentile=None))
        assert "Too few comparable players" in reading.profile[0]

    def test_a_renormalised_role_score_is_not_presented_as_a_penalty(self) -> None:
        reading = read(
            role=RoleReading(
                label="Deep-Lying Playmaker",
                score=70.0,
                percentile=80.0,
                coverage=0.7,
                is_limited=True,
                missing=("Progressive passes /90",),
            )
        )
        note = " ".join(reading.unavailable)
        assert "not lowered by the absence" in note
        assert "describes less of the role than the name suggests" in note

    @pytest.mark.parametrize(
        "forbidden",
        [
            "intelligent",
            "elite",
            "press resistant",
            "mentally",
            "world class",
            "composure",
            "leader",
        ],
    )
    def test_the_vocabulary_never_claims_a_trait(self, forbidden: str) -> None:
        """The provider counts events. Every word that explains *why* an event
        happened is inference wearing the clothes of a measurement."""
        reading = read(
            role=RoleReading("Defensive Stopper", 81.0, 93.0),
            scores=[ScoreReading("Defensive Activity", 88.0), ScoreReading("Ball Security", 31.0)],
            metrics=[
                MetricReading("Interceptions /90", 96.0),
                MetricReading("Key passes /90", 8.0),
                MetricReading("Dispossessed /90", 12.0, lower_is_better=True),
                MetricReading("Progressive passes /90", None, unavailable_reason="absent"),
            ],
        )
        everything = " ".join(
            [
                *reading.profile,
                *[f.reading for f in reading.strengths],
                *[f.reading for f in reading.watch_outs],
                *reading.unavailable,
                *reading.confidence,
            ]
        ).lower()
        assert forbidden not in everything


class TestConfidence:
    def test_the_sample_is_stated_with_its_minutes(self) -> None:
        reading = read(minutes=2340, sample_band_label="Established sample")
        assert "Established sample - 2,340 minutes played." in reading.confidence

    def test_high_detailed_coverage_says_the_rates_rest_on_most_of_it(self) -> None:
        reading = read(detailed_coverage_pct=92.0)
        assert any("92% of those minutes" in line for line in reading.confidence)
        assert any("rest on most of the football played" in line for line in reading.confidence)

    def test_low_detailed_coverage_says_limited_evidence(self) -> None:
        reading = read(detailed_coverage_pct=31.0)
        assert any("limited evidence" in line for line in reading.confidence)

    def test_unknown_coverage_is_named_rather_than_assumed(self) -> None:
        reading = read(detailed_coverage_pct=None)
        assert any("unknown" in line for line in reading.confidence)

    def test_a_small_sample_is_still_read(self) -> None:
        """Nothing is withheld for low minutes; the band is the caveat."""
        reading = read(minutes=90, sample_band_label="Very low sample")
        assert reading.confidence
        assert "Very low sample - 90 minutes played." in reading.confidence


class TestTheProfileLines:
    def test_the_strongest_dimensions_are_named(self) -> None:
        reading = read(
            scores=[
                ScoreReading("Defensive Activity", 88.0),
                ScoreReading("Duel Dominance", 74.0),
                ScoreReading("Ball Progression", 55.0),
            ]
        )
        line = next(line for line in reading.profile if line.startswith("Strongest"))
        assert "Defensive Activity (88)" in line
        assert "Duel Dominance (74)" in line
        assert "Ball Progression" not in line, "the middle is not a strength"

    def test_the_weakest_are_named_too(self) -> None:
        reading = read(scores=[ScoreReading("Goal Threat", 18.0), ScoreReading("Finishing", 35.0)])
        line = next(line for line in reading.profile if line.startswith("Weakest"))
        assert "Goal Threat (18)" in line

    def test_a_score_that_could_not_be_computed_is_skipped(self) -> None:
        reading = read(scores=[ScoreReading("Finishing", None), ScoreReading("Goal Threat", 92.0)])
        joined = " ".join(reading.profile)
        assert "Goal Threat" in joined
        assert "Finishing" not in joined

    def test_alternatives_are_listed_when_there_are_any(self) -> None:
        reading = read(
            role=RoleReading(
                label="Defensive Stopper",
                score=81.0,
                percentile=93.0,
                alternatives=("Ball-Playing Centre-Back", "Defensive Full-Back"),
            )
        )
        assert any("Also evaluated for" in line for line in reading.profile)


class TestTheEmptyCase:
    def test_a_profile_with_nothing_in_it_reads_as_empty(self) -> None:
        reading = interpret(
            role=None,
            scores=[],
            metrics=[],
            minutes=None,
            sample_band_label=None,
            detailed_coverage_pct=None,
        )
        assert reading.profile == []
        assert reading.strengths == []
        # Coverage being unknown is itself worth saying, so this is not empty.
        assert reading.confidence

    def test_nothing_is_invented_when_there_is_nothing_to_read(self) -> None:
        reading = read(metrics=[], scores=[], role=None)
        assert reading.strengths == []
        assert reading.watch_outs == []
        assert reading.unavailable == []


class TestWhatTheModelDoesNotSee:
    def test_the_list_names_things_a_decision_turns_on(self) -> None:
        joined = " ".join(NOT_CAPTURED).lower()
        for subject in ("injury", "wage", "video", "adapt"):
            assert subject in joined

    def test_it_is_short_enough_to_be_read(self) -> None:
        """A wall of disclaimer gets skipped, and the point is that these are
        read."""
        assert len(NOT_CAPTURED) <= 8


class TestAWeaknessHasToBeRelevant:
    """A goalkeeper ranks second percentile for key passes because nobody
    asked him to make any. Reporting that as a watch-out is true, useless, and
    reads as a deficiency - which is how the first version of this read for
    every keeper in the database."""

    GK_METRICS: ClassVar[list[MetricReading]] = [
        MetricReading("Saves /90", 32.0),
        MetricReading("Key passes /90", 2.0),
        MetricReading("Fouls drawn /90", 4.0),
        MetricReading("Duel win %", 7.0),
    ]

    def test_watch_outs_are_drawn_from_the_role_definition(self) -> None:
        reading = read(
            role=RoleReading(
                label="Shot Stopper",
                score=61.0,
                percentile=38.0,
                components=("Saves /90", "Goals conceded /90", "Clean sheet %"),
            ),
            metrics=self.GK_METRICS,
        )
        assert [f.label for f in reading.watch_outs] == ["Saves /90"]

    def test_a_strength_outside_the_role_is_still_worth_knowing(self) -> None:
        """A centre-back who dribbles well is interesting whatever he is being
        read as. The asymmetry is deliberate."""
        reading = read(
            role=RoleReading(
                label="Defensive Stopper",
                score=81.0,
                percentile=93.0,
                components=("Interceptions /90", "Blocks /90"),
            ),
            metrics=[
                MetricReading("Interceptions /90", 95.0),
                MetricReading("Successful dribbles /90", 91.0),
            ],
        )
        assert [f.label for f in reading.strengths] == [
            "Interceptions /90",
            "Successful dribbles /90",
        ]

    def test_without_a_role_every_metric_is_fair_game(self) -> None:
        """Nothing to be relevant to, so nothing is filtered - the reading is
        about the player rather than about a role."""
        reading = read(role=None, metrics=self.GK_METRICS)
        assert len(reading.watch_outs) == 4

    def test_a_role_with_no_listed_components_does_not_silence_everything(self) -> None:
        reading = read(
            role=RoleReading("Shot Stopper", 61.0, 38.0, components=()),
            metrics=self.GK_METRICS,
        )
        assert reading.watch_outs, "an empty component list is unknown, not empty"
