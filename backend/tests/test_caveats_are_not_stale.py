"""A caveat may not contradict what the provider actually supplies.

THE DEFECT
==========

Availability facts were written by hand into `config/player_roles.yaml` and
went stale exactly as one would expect, because nothing connected them to the
mapping they described:

- **Ball-Winning Midfielder** said it was computed without the ball security
  score. Ball security is at 100% coverage and has been for some time.
- **Direct Winger** said it was computed without inverse dispossessions. That
  role is at 100% coverage with nothing missing at all.

Both were true when written. Neither had any way of noticing the provider had
started supplying the field, so the site went on apologising for data it had -
which is worse than saying nothing, because a reader who checks finds the
metric present and stops trusting the rest of the page.

THE RULE
========

Anything derivable is derived. `RoleScore.availability_note` is generated from
what was actually missing for that player; the hand-written `caveat` keeps only
what no availability report can know - that tackle counts are attempts rather
than successes, that goalkeeping figures are team-dependent.

These tests hold that line: a caveat that names a metric, or states a
percentage, is a caveat that can go stale.
"""

from __future__ import annotations

import re

import pytest

from app.analytics.roles import load_roles

# Metric-shaped words. A caveat may discuss a *concept* ("aerial duel
# efficiency"); what it may not do is name the field, because naming the field
# is making a claim about the mapping.
METRIC_NAME = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}\b")


@pytest.fixture(scope="module")
def availability():  # type: ignore[no-untyped-def]
    """What the configuration and mapping say is available, right now."""
    from pipelines.quality.config_availability import measure

    roles, scores, _vectors, _absent = measure()
    return {line.label: line for line in [*roles, *scores]}


class TestCaveatsStateNothingDerivable:
    def test_no_caveat_names_a_metric_field(self) -> None:
        offenders = []
        for key, role in load_roles().items():
            if not role.caveat:
                continue
            for match in METRIC_NAME.findall(role.caveat):
                offenders.append(f"{key}: {match}")
        assert offenders == [], (
            f"these caveats name provider fields, which is a claim about the mapping "
            f"that nothing keeps in step: {offenders}"
        )

    def test_no_caveat_states_a_weight_percentage(self) -> None:
        """ "That component carried 15%" is derivable, and so it is derived."""
        offenders = [
            key for key, role in load_roles().items() if role.caveat and "%" in role.caveat
        ]
        assert offenders == [], offenders

    def test_no_caveat_claims_a_named_score_is_unsupported(self) -> None:
        """The Ball-Winning Midfielder defect, asserted directly."""
        offenders = []
        for key, role in load_roles().items():
            caveat = (role.caveat or "").lower()
            for score in role.score_weights:
                readable = score.replace("_", " ")
                if readable in caveat and (
                    "without" in caveat or "not suppl" in caveat or "does not support" in caveat
                ):
                    offenders.append(f"{key}: {score}")
        assert offenders == [], offenders


class TestARoleCannotBeFullyCoveredAndApologise:
    def test_a_role_at_full_coverage_carries_no_availability_caveat(
        self,
        availability,  # type: ignore[no-untyped-def]
    ) -> None:
        """The Direct Winger defect: 100% coverage, nothing missing, and a
        caveat saying a component was unavailable."""
        offenders = []
        for role in load_roles().values():
            line = availability.get(role.label)
            if line is None or line.missing:
                continue
            caveat = (role.caveat or "").lower()
            for phrase in ("computed without", "does not supply", "not supplied", "unavailable"):
                if phrase in caveat:
                    offenders.append(f"{role.label}: says {phrase!r} at 100% coverage")
        assert offenders == [], offenders

    def test_the_two_roles_the_brief_named_are_clean(
        self,
        availability,  # type: ignore[no-untyped-def]
    ) -> None:
        roles = load_roles()

        winger = availability["Direct Winger"]
        assert winger.missing == []
        assert not (roles["direct_winger"].caveat or "").strip(), (
            "the Direct Winger caveat described a metric it is not missing"
        )

        midfielder = roles["ball_winning_midfielder"]
        assert "ball security" not in (midfielder.caveat or "").lower(), (
            "the Ball-Winning Midfielder caveat still names a score that is available"
        )
        assert availability["Ball Security"].missing == [], (
            "ball security has become unavailable; the caveat above may need to return"
        )


class TestTheGeneratedNoteIsTheOneThatCanBeQuantitative:
    def test_it_names_exactly_what_was_missing(self) -> None:
        from app.analytics.percentiles import ComparisonContext, PercentileScope
        from app.analytics.roles import RoleScore
        from app.analytics.scoring import ScoreComponent
        from app.schemas.canonical import PositionGroup

        context = ComparisonContext(
            scope=PercentileScope.COMPETITION,
            position_group=PositionGroup.CM,
            season_id="2026/27",
            competition_ids=("c",),
            population_size=50,
            minimum_minutes=0,
        )
        score = RoleScore(
            key="k",
            label="Test Role",
            score=60.0,
            coverage=0.7,
            context=context,
            components=[ScoreComponent(metric="passes_per90", weight=70.0, value=60.0)],
            missing=["progressive_passes_per90"],
            caveat="A qualitative note.",
        )

        note = score.availability_note
        assert note is not None
        assert "progressive_passes_per90" in note
        assert "70%" in note
        # And the two are joined for display, in that order.
        assert score.explanation is not None
        assert score.explanation.startswith("Computed from 70%")
        assert score.explanation.endswith("A qualitative note.")

    def test_a_fully_covered_role_generates_no_note(self) -> None:
        from app.analytics.percentiles import ComparisonContext, PercentileScope
        from app.analytics.roles import RoleScore
        from app.schemas.canonical import PositionGroup

        context = ComparisonContext(
            scope=PercentileScope.COMPETITION,
            position_group=PositionGroup.CM,
            season_id="2026/27",
            competition_ids=("c",),
            population_size=50,
            minimum_minutes=0,
        )
        score = RoleScore(
            key="k",
            label="Test Role",
            score=60.0,
            coverage=1.0,
            context=context,
            components=[],
            missing=[],
            caveat="A qualitative note.",
        )
        assert score.availability_note is None
        assert score.explanation == "A qualitative note."


class TestTheGeneratedReportIsTheSourceOfTruth:
    def test_the_committed_report_matches_the_configuration(self) -> None:
        """It is generated, and CI checks it. Asserted here too because the
        whole approach rests on it being regenerated rather than edited.
        """
        from pipelines.quality.config_availability import main

        assert main(["--check"]) == 0

    def test_it_says_it_is_generated(self) -> None:
        import pathlib

        report = pathlib.Path(__file__).resolve().parents[2] / "docs" / "config_availability.md"
        head = report.read_text(encoding="utf-8")[:600].lower()
        assert "generated" in head
        assert "do not edit" in head
