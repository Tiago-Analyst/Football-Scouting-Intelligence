"""Named roles translated into recruitment-builder weights.

A preset is a starting point, not a ranking. These assert the translation is
faithful to the role it is named after, that it does not quietly invent
emphasis for the parts of a role the intelligence scores cannot carry, and
that it declines rather than mislead when too little of a role survives.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from app.analytics.intelligence import (
    IntelligenceScoreEngine,
    ScoreDefinition,
    get_definitions,
)
from app.analytics.metrics import DerivedMetric
from app.analytics.percentiles import PercentileEngine
from app.analytics.presets import (
    MINIMUM_EXPRESSIBLE,
    STEP,
    RolePreset,
    derive,
    get_presets,
)
from app.analytics.roles import RoleDefinition, get_roles
from app.schemas.canonical import PositionGroup


def role(
    metrics: dict[DerivedMetric, float],
    scores: dict[str, float] | None = None,
) -> RoleDefinition:
    return RoleDefinition(
        key="test_role",
        label="Test Role",
        description="",
        position_groups=(PositionGroup.CM,),
        metric_weights=metrics,
        score_weights=scores or {},
    )


class TestTheTranslation:
    def test_a_preset_sums_to_one_hundred(self) -> None:
        for preset in get_presets():
            assert sum(preset.weights.values()) == pytest.approx(100.0)

    def test_every_weight_lands_on_a_step_the_form_can_hold(self) -> None:
        """The builder's inputs step by five. A preset of 37 would be rounded
        by the first person who touched the form, silently."""
        for preset in get_presets():
            for weight in preset.weights.values():
                assert weight % STEP == 0
                assert weight > 0

    def test_every_weight_names_a_real_intelligence_score(self) -> None:
        known = set(get_definitions())
        for preset in get_presets():
            assert set(preset.weights) <= known

    def test_a_role_weighted_on_one_score_alone_translates_to_that_score(self) -> None:
        finishing = get_definitions()["finishing"]
        metric = next(iter(finishing.components))
        preset = derive(role({metric: 10.0}))
        assert preset is not None
        assert set(preset.weights) <= {"finishing", *_sharers(metric)}

    def test_a_role_that_weights_a_score_directly_needs_no_translation(self) -> None:
        preset = derive(role({}, {"ball_security": 40.0, "duel_dominance": 10.0}))
        assert preset is not None
        assert preset.weights == {"ball_security": 80.0, "duel_dominance": 20.0}
        assert preset.expressible == pytest.approx(1.0)

    def test_the_relative_order_of_a_role_survives_the_translation(self) -> None:
        """Rounding may move a weight by a couple of points. It may not turn
        the emphasis of a role upside down."""
        for preset in get_presets():
            ordered = list(preset.weights.values())
            assert ordered == sorted(ordered, reverse=True)


class TestWhatItRefusesToInvent:
    def test_an_unmapped_component_is_dropped_and_named(self) -> None:
        """Rule 6 in miniature. A metric no intelligence score contains has
        nowhere to go, and spreading its weight over the others would invent
        an emphasis the role never had."""
        orphan = _unmapped_metric()
        security = next(iter(get_definitions()["ball_security"].components))
        preset = derive(role({security: 50.0, orphan: 50.0}))

        assert preset is not None
        assert preset.unmapped == (orphan.value,)
        assert preset.expressible == pytest.approx(0.5)
        assert orphan.value not in preset.weights

    def test_a_role_the_scores_cannot_describe_gets_no_preset(self) -> None:
        assert derive(role({_unmapped_metric(): 100.0})) is None

    def test_a_role_mostly_outside_the_scores_gets_no_preset(self) -> None:
        """Better no starting point than one carrying a role's name and a
        minority of its meaning."""
        security = next(iter(get_definitions()["ball_security"].components))
        preset = derive(role({security: 1.0, _unmapped_metric(): 9.0}))
        assert preset is None

    def test_the_goalkeeping_role_is_absent_rather_than_approximated(self) -> None:
        keys = {preset.key for preset in get_presets()}
        assert "shot_stopper" in get_roles()
        assert "shot_stopper" not in keys

    def test_expressible_reports_what_actually_survived(self) -> None:
        for preset in get_presets():
            assert MINIMUM_EXPRESSIBLE <= preset.expressible <= 1.0
            assert (preset.expressible < 1.0) == bool(preset.unmapped)


class TestItIsNotASecondScoringEngine:
    def test_a_preset_carries_no_ranking_of_its_own(self) -> None:
        """A preset is eight numbers for a form. If it ever starts carrying
        players or scores, it has become a second engine."""
        fields = set(RolePreset.__dataclass_fields__)
        assert not fields & {"players", "candidates", "score", "results"}

    def test_presets_are_derived_from_the_role_config_not_restated(self) -> None:
        """A hand-written preset table would drift the first time a role was
        retuned, and nothing would notice."""
        for preset in get_presets():
            definition = get_roles()[preset.key]
            assert preset.label == definition.label
            assert preset.position_groups == tuple(g.value for g in definition.position_groups)
            assert preset.caveat == definition.caveat

    def test_a_shared_metric_is_split_rather_than_assigned_to_a_winner(self) -> None:
        """Completed passes counts towards both ball progression and ball
        security. Giving it to one of them would overstate that score by the
        whole weight of the metric."""
        shared = next(
            m
            for m in DerivedMetric
            if len(_sharers(m)) > 1 and m in get_definitions()["ball_progression"].components
        )
        carriers = _sharers(shared)
        preset = derive(role({shared: 100.0}))
        assert preset is not None
        assert set(preset.weights) == carriers
        assert preset.expressible == pytest.approx(1.0)


def _sharers(metric: DerivedMetric) -> set[str]:
    return {key for key, definition in get_definitions().items() if metric in definition.components}


def _unmapped_metric() -> DerivedMetric:
    covered: set[DerivedMetric] = set()
    definitions: dict[str, ScoreDefinition] = get_definitions()
    for definition in definitions.values():
        covered |= set(definition.components)
    return next(m for m in DerivedMetric if m not in covered)


class TestSayingSoBeforeTheSearch:
    """Which emphases this load cannot produce, answered in advance.

    The builder could only say a profile was unscorable after running the
    search and coming back empty - which reads as "no player matched your
    filters" and blames the filters for the data. A score no player can be
    given is a property of the load, knowable before anybody presses anything.
    """

    def test_a_score_missing_a_component_is_reported_unproducible(self) -> None:
        definitions = get_definitions()
        progression = definitions["ball_progression"]
        present = frozenset(m for m in DerivedMetric if m in progression.components)
        dropped = next(iter(progression.components))

        engine = IntelligenceScoreEngine(
            percentiles=cast(PercentileEngine, None),
            definitions={"ball_progression": progression},
        )
        verdict = engine.unproducible(present - {dropped})

        assert "ball_progression" in verdict
        assert dropped.value in verdict["ball_progression"]

    def test_a_score_with_everything_present_is_not_reported(self) -> None:
        definitions = get_definitions()
        engine = IntelligenceScoreEngine(
            percentiles=cast(PercentileEngine, None), definitions=definitions
        )
        assert engine.unproducible(frozenset(DerivedMetric)) == {}

    def test_the_verdict_follows_the_definition_rather_than_a_second_rule(self) -> None:
        """A definition that tolerates a gap must be reported as producible.
        Reimplementing the coverage rule here is how the warning starts
        disagreeing with the search it is warning about."""
        definitions = get_definitions()
        security = definitions["ball_security"]
        tolerant = replace(security, min_coverage=0.1)
        dropped = next(iter(tolerant.components))

        engine = IntelligenceScoreEngine(
            percentiles=cast(PercentileEngine, None), definitions={"ball_security": tolerant}
        )
        present = frozenset(m for m in tolerant.components if m is not dropped)
        assert engine.unproducible(present) == {}

    def test_nothing_present_blocks_everything(self) -> None:
        engine = IntelligenceScoreEngine(
            percentiles=cast(PercentileEngine, None), definitions=get_definitions()
        )
        assert set(engine.unproducible(frozenset())) == set(get_definitions())
