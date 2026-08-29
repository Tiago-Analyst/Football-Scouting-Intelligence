"""Measuring what the loaded data can actually produce.

The report exists to answer one question correctly: when a feature produces
nothing, is that the provider or the ingest? Getting it backwards is expensive
in both directions - writing off a feature that only needed more data, or
promising one that can never work.
"""

from __future__ import annotations

import pytest
from pipelines.quality.derived_coverage import DerivedCoverage, FeatureCoverage


def coverage(computed: int, *, eligible: int = 100, best: float = 0.0) -> DerivedCoverage:
    return DerivedCoverage(
        metric="example_per90",
        eligible=eligible,
        computed=computed,
        best_group="CB" if best else None,
        best_group_coverage=best,
    )


class TestMetricStatus:
    def test_nothing_computed_is_absent(self) -> None:
        """A statement about the provider, not a gap to chase."""
        assert coverage(0).status == "absent"

    def test_nothing_loaded_is_unknown_not_absent(self) -> None:
        """An empty database must not read as a provider that supplies nothing."""
        assert coverage(0, eligible=0).status == "unknown"

    def test_a_position_specific_metric_is_judged_where_it_belongs(self) -> None:
        """`save_percentage` covers 12% of players and 100% of goalkeepers.
        Judged overall it looks broken; judged where it belongs it is complete,
        and a check that cries wolf on correct data gets ignored."""
        assert coverage(12, best=1.0).status == "complete"

    def test_genuinely_thin_coverage_is_still_reported(self) -> None:
        assert coverage(30, best=0.4).status == "sparse"

    def test_mostly_there_is_partial(self) -> None:
        assert coverage(80, best=0.8).status == "partial"


def feature(
    *,
    produced: int = 0,
    eligible: int = 100,
    caveated: int = 0,
    absent: tuple[str, ...] = (),
    surviving: float = 1.0,
    threshold: float = 1.0,
) -> FeatureCoverage:
    return FeatureCoverage(
        name="example",
        kind="score",
        eligible=eligible,
        produced=produced,
        caveated=caveated,
        absent_components=absent,
        surviving_weight=surviving,
        min_coverage=threshold,
    )


class TestWhyAFeatureIsWithheld:
    """The distinction the whole report turns on."""

    def test_losing_more_weight_than_the_threshold_allows_is_permanent(self) -> None:
        withheld = feature(absent=("progressive_passes_per90",), surviving=0.55, threshold=1.0)
        assert withheld.is_permanently_withheld
        assert "provider" in withheld.reason

    def test_a_missing_component_it_was_built_to_survive_is_not_permanent(self) -> None:
        """Several roles carry a `min_coverage` set precisely so a known absence
        costs them a caveat rather than their existence. Blaming the provider
        wherever a component is missing would write those off."""
        survivor = feature(absent=("progressive_passes_per90",), surviving=0.85, threshold=0.84)
        assert not survivor.is_permanently_withheld
        assert "sample" in survivor.reason

    def test_the_threshold_is_a_floor_not_a_target(self) -> None:
        """Exactly at the threshold still counts as met."""
        assert not feature(absent=("x",), surviving=0.84, threshold=0.84).is_permanently_withheld

    def test_nothing_absent_means_nothing_to_blame_the_provider_for(self) -> None:
        assert not feature(surviving=1.0).is_permanently_withheld
        assert "sample" in feature(produced=0).reason

    def test_a_feature_that_survives_says_it_was_computed_on_a_subset(self) -> None:
        """Produced, but not from the whole definition. Saying so is the
        difference between a caveat and a quiet substitution."""
        partial = feature(
            produced=90, absent=("progressive_passes_per90",), surviving=0.85, threshold=0.84
        )
        assert partial.status == "available"
        assert "partial" in partial.reason
        assert "renormalised" in partial.reason


class TestFeatureStatus:
    def test_produced_for_nobody_is_withheld(self) -> None:
        assert feature(produced=0).status == "withheld"

    def test_no_eligible_players_is_unknown(self) -> None:
        """A role no loaded player's position matches has not failed."""
        assert feature(produced=0, eligible=0).status == "unknown"

    def test_mostly_caveated_output_is_reported_as_caveated(self) -> None:
        assert feature(produced=40, caveated=30).status == "caveated"

    def test_clean_output_is_available(self) -> None:
        assert feature(produced=40, caveated=2).status == "available"


class TestMeasuringAgainstTheEngines:
    """Counting real output rather than reading the configuration."""

    @pytest.fixture
    def view(self):  # type: ignore[no-untyped-def]
        from app.core.config import get_settings
        from app.services.analytics_service import build_view

        return build_view(get_settings())

    @pytest.mark.integration
    def test_it_measures_the_loaded_universe(self, view) -> None:  # type: ignore[no-untyped-def]
        from pipelines.quality.derived_coverage import measure

        if view.is_empty:
            pytest.skip("nothing loaded")

        metrics, features = measure(view)
        assert metrics, "every derived metric should be reported on"
        assert features, "every score and role should be reported on"

    @pytest.mark.integration
    def test_an_absent_input_and_its_dependants_agree(self, view) -> None:  # type: ignore[no-untyped-def]
        """Two independent methods, one answer. `impact_of_absence` probes a
        synthetic record to find what *cannot* compute; this counts what did.
        If they disagreed, one of them would be wrong about the product."""
        from pipelines.quality.coverage import impact_of_absence
        from pipelines.quality.derived_coverage import measure, source_keys

        from app.schemas.canonical import CanonicalMetric

        if view.is_empty:
            pytest.skip("nothing loaded")
        keys = source_keys("footystats")
        if not keys:
            pytest.skip("footystats is not loaded")

        metrics, features = measure(view, keys=keys)
        absent_derived = {m.metric for m in metrics if m.status == "absent"}
        if not absent_derived:
            pytest.skip("no absent metrics in the loaded data")

        absent_canonical = {
            metric
            for metric in CanonicalMetric
            if any(derived.startswith(metric.value) for derived in absent_derived)
        }
        predicted = impact_of_absence(absent_canonical)
        measured = {f.name for f in features if f.is_permanently_withheld}

        assert measured <= (set(predicted.roles) | set(predicted.scores)), (
            "the measurement withheld something the dependency graph says is computable"
        )
