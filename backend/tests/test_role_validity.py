"""Full, Partial and Unavailable: what each means and what each publishes.

Core validity and metric coverage answer different questions and are kept
apart everywhere here. Coverage asks how much of a role's configured
definition could be measured. Validity asks whether the concepts that make the
role that role are measurable at all. A percentage cannot distinguish 20% of
periphery missing from a defining component being absent, which is how a
centre-back with no measure of progression came to be ranked as a ball-playing
centre-back alongside ones that had it.

Constructed rather than sampled: the demo dataset supplies everything, so no
role is ever Partial in it, and a rule that is never exercised is a rule
nobody is holding.
"""

from __future__ import annotations

import pathlib

import pytest

from app.analytics.metrics import DerivedMetric
from app.analytics.percentiles import ComparisonContext
from app.analytics.roles import (
    SECONDARY_COVERAGE_FLOOR,
    CoreDimensionStatus,
    RoleFit,
    RoleScore,
    RoleValidity,
    get_roles,
    normalise_fits,
)
from app.analytics.scoring import ScoreComponent

CONTEXT = ComparisonContext(
    scope="competition",
    competition_ids=frozenset({"c1"}),
    season_id="2026-2027",
    position_group="CB",
    population_size=50,
    minimum_minutes=0,
)


def dimension(name: str, satisfied: bool) -> CoreDimensionStatus:
    return CoreDimensionStatus(
        name=name,
        satisfied=satisfied,
        available=("metric_a",) if satisfied else (),
        missing=() if satisfied else ("metric_a",),
    )


def role_score(
    key: str = "ball_playing_centre_back",
    *,
    score: float | None = 70.0,
    coverage: float = 0.9,
    validity: RoleValidity = RoleValidity.FULL,
    dimensions: tuple[CoreDimensionStatus, ...] = (),
) -> RoleScore:
    return RoleScore(
        key=key,
        label=key.replace("_", " ").title(),
        score=score,
        coverage=coverage,
        context=CONTEXT,
        components=[ScoreComponent(metric="metric_a", weight=100.0, value=score)],
        missing=[],
        validity=validity,
        core_dimensions=dimensions,
    )


class TestTheConfiguredDimensions:
    def test_every_role_declares_its_defining_concepts(self) -> None:
        missing = [k for k, r in get_roles().items() if not r.core_dimensions]
        assert missing == [], f"roles with no core dimensions: {missing}"

    def test_a_dimension_only_names_metrics_the_role_scores_from(self) -> None:
        """Otherwise it is a requirement nothing in the role could satisfy."""
        for key, role in get_roles().items():
            weighted = set(role.metric_weights)
            for name, metrics in role.core_dimensions.items():
                stray = sorted(m.value for m in metrics if m not in weighted)
                assert stray == [], f"{key} dimension '{name}' names unweighted metrics: {stray}"

    def test_the_target_forwards_aerial_dimension_is_efficiency_not_volume(self) -> None:
        """Aerials won is output. Aerial duel win % is efficiency.

        Volume without a denominator cannot tell a dominant target man from
        one who contests constantly and loses, and for a role where aerials
        are nearly half the weight that is not a detail. Satisfying the
        dimension with `aerial_duels_won_per90` would be inventing a
        measurement the provider does not supply.
        """
        aerial = get_roles()["target_forward"].core_dimensions["aerial efficiency"]
        assert aerial == (DerivedMetric.AERIAL_DUEL_WIN_PERCENTAGE,)
        assert DerivedMetric.AERIAL_DUELS_WON_PER90 not in aerial

    def test_the_shot_stoppers_core_is_shot_stopping_alone(self) -> None:
        """Inside-box saves describe a kind of save, not the ability to make them."""
        core = get_roles()["shot_stopper"].core_dimensions
        assert core == {"shot stopping": (DerivedMetric.SAVE_PERCENTAGE,)}


class TestTheRule:
    def test_all_dimensions_met_is_full(self) -> None:
        from app.analytics.roles import _validity

        assert (
            _validity(70.0, 0.9, (dimension("a", True), dimension("b", True))) is RoleValidity.FULL
        )

    def test_one_dimension_unmet_is_partial(self) -> None:
        from app.analytics.roles import _validity

        verdict = _validity(70.0, 0.9, (dimension("a", True), dimension("b", False)))
        assert verdict is RoleValidity.PARTIAL

    def test_high_coverage_does_not_rescue_a_missing_core_dimension(self) -> None:
        """The case the percentage floor could not see."""
        from app.analytics.roles import _validity

        assert _validity(70.0, 0.95, (dimension("progression", False),)) is RoleValidity.PARTIAL

    def test_low_coverage_with_every_dimension_met_is_still_full(self) -> None:
        """And the mirror image: core validity is the primary gate."""
        from app.analytics.roles import _validity

        assert (
            _validity(70.0, SECONDARY_COVERAGE_FLOOR, (dimension("a", True),)) is RoleValidity.FULL
        )

    def test_too_little_measured_is_unavailable(self) -> None:
        from app.analytics.roles import _validity

        assert _validity(70.0, 0.4, (dimension("a", True),)) is RoleValidity.UNAVAILABLE

    def test_no_score_is_unavailable(self) -> None:
        from app.analytics.roles import _validity

        assert _validity(None, 0.9, (dimension("a", True),)) is RoleValidity.UNAVAILABLE

    def test_a_role_with_no_declared_dimensions_is_full(self) -> None:
        """Absence of a declaration is not a finding about the football."""
        from app.analytics.roles import _validity

        assert _validity(70.0, 0.9, ()) is RoleValidity.FULL


class TestWhatEachStatePublishes:
    def _normalised(self, scores: list[RoleScore]) -> RoleFit:
        population = {f"p{i}": RoleFit(best=s, alternatives=[]) for i, s in enumerate(scores)}
        return normalise_fits(population)["p0"]

    def test_a_full_role_keeps_its_percentile(self) -> None:
        fit = self._normalised([role_score(score=float(60 + i)) for i in range(30)])
        assert fit.best is not None
        assert fit.best.role_fit_percentile is not None
        assert fit.best.role_fit_percentile_reason is None

    def test_a_partial_role_keeps_its_raw_fit(self) -> None:
        partial = role_score(
            score=72.0, validity=RoleValidity.PARTIAL, dimensions=(dimension("progression", False),)
        )
        fit = self._normalised([partial] + [role_score(score=float(60 + i)) for i in range(29)])
        evidence = fit.partial_evidence
        assert evidence, "a partial role must still be reported"
        assert evidence[0].score == 72.0, "the raw fit is real and is not withheld"

    def test_a_partial_role_publishes_no_percentile(self) -> None:
        partial = role_score(
            score=72.0, validity=RoleValidity.PARTIAL, dimensions=(dimension("progression", False),)
        )
        fit = self._normalised([partial] + [role_score(score=float(60 + i)) for i in range(29)])
        shown = fit.partial_evidence[0]
        assert shown.role_fit_percentile is None
        assert shown.role_fit_percentile_reason is not None
        assert "progression" in shown.role_fit_percentile_reason

    def test_partial_scores_do_not_place_full_ones(self) -> None:
        """The comparison the missing metric forbids, in the other direction.

        A partial score sitting in the distribution would move every full
        player's percentile, silently, using a number built from less.
        """
        full = [role_score(score=float(50 + i)) for i in range(30)]
        with_partial = [
            *full,
            role_score(
                score=99.0,
                validity=RoleValidity.PARTIAL,
                dimensions=(dimension("progression", False),),
            ),
        ]
        a = self._normalised(full).best
        b = normalise_fits(
            {f"p{i}": RoleFit(best=s, alternatives=[]) for i, s in enumerate(with_partial)}
        )["p0"].best
        assert a is not None and b is not None
        assert a.role_fit_percentile == b.role_fit_percentile

    def test_missing_is_not_zero_anywhere_in_this(self) -> None:
        partial = role_score(
            score=72.0, validity=RoleValidity.PARTIAL, dimensions=(dimension("progression", False),)
        )
        fit = self._normalised([partial] + [role_score(score=float(60 + i)) for i in range(29)])
        shown = fit.partial_evidence[0]
        assert shown.role_fit_percentile is None, "withheld, not zero"
        assert shown.score == 72.0


class TestBestRoleSelection:
    def _fit(self, scores: list[RoleScore]) -> RoleFit:
        others = [role_score(key="defensive_stopper", score=float(40 + i)) for i in range(30)]
        population = {"p0": RoleFit(best=scores[0], alternatives=scores[1:])}
        population.update({f"q{i}": RoleFit(best=s, alternatives=[]) for i, s in enumerate(others)})
        return normalise_fits(population)["p0"]

    def test_the_best_role_is_a_fully_supported_one(self) -> None:
        strong_partial = role_score(
            key="ball_playing_centre_back",
            score=95.0,
            validity=RoleValidity.PARTIAL,
            dimensions=(dimension("progression", False),),
        )
        weaker_full = role_score(key="defensive_stopper", score=55.0)
        fit = self._fit([strong_partial, weaker_full])
        assert fit.best is not None
        assert fit.best.key == "defensive_stopper"

    def test_but_the_strong_partial_is_not_discarded(self) -> None:
        """It is a real finding about the player, reported beside the headline."""
        strong_partial = role_score(
            key="ball_playing_centre_back",
            score=95.0,
            validity=RoleValidity.PARTIAL,
            dimensions=(dimension("progression", False),),
        )
        fit = self._fit([strong_partial, role_score(key="defensive_stopper", score=55.0)])
        assert [s.key for s in fit.partial_evidence] == ["ball_playing_centre_back"]
        assert fit.partial_evidence[0].score == 95.0

    def test_with_no_full_role_there_is_no_best_role(self) -> None:
        """Rather than promoting an incomparable number into the headline."""
        partial = role_score(
            key="ball_playing_centre_back",
            score=88.0,
            validity=RoleValidity.PARTIAL,
            dimensions=(dimension("progression", False),),
        )
        fit = self._fit([partial])
        assert fit.best is None
        assert fit.partial_evidence and fit.partial_evidence[0].score == 88.0

    def test_partial_evidence_is_ordered_by_raw_fit(self) -> None:
        weak = role_score(
            key="ball_playing_centre_back",
            score=40.0,
            validity=RoleValidity.PARTIAL,
            dimensions=(dimension("progression", False),),
        )
        strong = role_score(
            key="deep_lying_playmaker",
            score=80.0,
            validity=RoleValidity.PARTIAL,
            dimensions=(dimension("progression", False),),
        )
        fit = self._fit([weak, strong])
        assert [s.key for s in fit.partial_evidence] == [
            "deep_lying_playmaker",
            "ball_playing_centre_back",
        ]


class TestTheProvisionalFloor:
    def test_it_is_one_number_for_every_role(self) -> None:
        """Fifteen tuned ones would repeat the mistake min_coverage made:
        thresholds that encode provider availability rather than need."""
        assert isinstance(SECONDARY_COVERAGE_FLOOR, float)
        assert 0.0 < SECONDARY_COVERAGE_FLOOR < 1.0

    def test_it_is_documented_as_provisional(self) -> None:
        import app.analytics.roles as module

        text = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        # The comment block attached to the definition, not a fixed window
        # before the first mention - the constant is referred to in prose
        # elsewhere in the file and a window walks onto the wrong one.
        at = text.index("SECONDARY_COVERAGE_FLOOR = ")
        marker = text[max(0, at - 1400) : at]
        assert "PROVISIONAL" in marker, "the floor must say it is not a methodological finding"
        assert "football decision" in marker


@pytest.mark.parametrize(
    "key",
    [
        "ball_playing_centre_back",
        "deep_lying_playmaker",
        "defensive_full_back",
        "target_forward",
        "shot_stopper",
        "defensive_stopper",
        "ball_winning_midfielder",
        "box_to_box_midfielder",
    ],
)
def test_the_audited_roles_all_declare_dimensions(key: str) -> None:
    """The eight named for revalidation."""
    role = get_roles()[key]
    assert role.core_dimensions, f"{key} declares no defining concepts"
    for name, metrics in role.core_dimensions.items():
        assert metrics, f"{key} dimension '{name}' is empty"


class TestTheLegacyThresholdNoLongerGates:
    """The per-role floors encoded provider availability, not football need.

    Thirteen of fifteen sat exactly one point below the maximum coverage the
    data could reach, and because they ran before core validity they could
    refuse a role whose defining concepts were all measured: twelve
    full-backs at 70% coverage against a 79% floor, with both core dimensions
    satisfied, scored nothing at all.
    """

    def test_the_field_is_named_so_it_cannot_be_reached_for_by_habit(self) -> None:
        role = get_roles()["defensive_full_back"]
        assert not hasattr(role, "min_coverage")
        assert role.legacy_min_coverage == pytest.approx(0.79)

    def test_the_historical_values_are_kept(self) -> None:
        """For migration, diagnostics and the record - not for gating."""
        floors = {k: r.legacy_min_coverage for k, r in get_roles().items()}
        assert floors["shot_stopper"] == 1.0
        assert floors["ball_playing_centre_back"] == pytest.approx(0.59)

    def test_the_scorer_asks_the_shared_floor_and_not_the_role(self) -> None:
        import inspect

        from app.analytics import roles as module

        source = inspect.getsource(module.RoleEngine.score)
        assert "SECONDARY_COVERAGE_FLOOR" in source
        assert "legacy_min_coverage" not in source

    def test_a_core_valid_full_back_at_sixty_percent_is_full(self) -> None:
        """The exact case: below the old 79%, above the shared floor, core met.

        Twelve real players sit here. `duel_win_percentage` evidences
        defensive resistance where `dribbled_past_per90` is absent, which is
        the whole point of dimensions over mandatory metrics.
        """
        role = get_roles()["defensive_full_back"]
        present = {
            "tackles_per90": 70.0,
            "interceptions_per90": 60.0,
            "duel_win_percentage": 65.0,
            "clearances_per90": 55.0,
        }
        components = [
            ScoreComponent(metric=m.value, weight=w, value=present.get(m.value))
            for m, w in role.metric_weights.items()
        ]
        from app.analytics.roles import _validity
        from app.analytics.scoring import weighted_score

        result = weighted_score(components, min_coverage=SECONDARY_COVERAGE_FLOOR)
        assert result.score is not None, "the old floor would have refused this"
        assert result.coverage < role.legacy_min_coverage

        available = {c.metric for c in result.components if c.is_available}
        dimensions = tuple(
            CoreDimensionStatus(
                name=n,
                satisfied=any(m.value in available for m in ms),
                available=tuple(m.value for m in ms if m.value in available),
                missing=tuple(m.value for m in ms if m.value not in available),
            )
            for n, ms in role.core_dimensions.items()
        )
        assert all(d.satisfied for d in dimensions)
        assert _validity(result.score, result.coverage, dimensions) is RoleValidity.FULL

    def test_coverage_below_the_shared_floor_is_never_full(self) -> None:
        """Even when the surviving metrics happen to cover every dimension."""
        from app.analytics.roles import _validity

        verdict = _validity(70.0, SECONDARY_COVERAGE_FLOOR - 0.01, (dimension("a", True),))
        assert verdict is RoleValidity.UNAVAILABLE

    def test_high_coverage_with_a_missing_core_dimension_is_never_full(self) -> None:
        from app.analytics.roles import _validity

        assert _validity(70.0, 0.98, (dimension("progression", False),)) is RoleValidity.PARTIAL

    def test_an_absent_component_stays_absent(self) -> None:
        """Retiring a gate must not start filling gaps."""
        role = get_roles()["defensive_full_back"]
        components = [
            ScoreComponent(
                metric=m.value, weight=w, value=None if m.value.startswith("aerial") else 60.0
            )
            for m, w in role.metric_weights.items()
        ]
        from app.analytics.scoring import weighted_score

        result = weighted_score(components, min_coverage=SECONDARY_COVERAGE_FLOOR)
        absent = [c for c in result.components if not c.is_available]
        assert absent, "the aerial component must still be absent"
        assert all(c.value is None for c in absent), "absent is not zero"
        assert result.coverage < 1.0
