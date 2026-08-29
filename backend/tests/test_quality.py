"""Data quality reporting.

The dependency map is the part worth testing hardest. It is *measured* rather
than declared — blank one canonical metric and see what stops computing — and a
measurement that quietly returns nothing would make every downstream claim about
disabled features vacuous while looking like it worked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pipelines.quality.coverage import (
    MetricCoverage,
    absent_metrics,
    dependency_map,
    impact_of_absence,
)
from pipelines.quality.report import coverage_checks, freshness_checks, integrity_checks
from sqlalchemy.orm import Session

from app.analytics.intelligence import get_definitions
from app.analytics.metrics import DerivedMetric
from app.analytics.roles import get_roles
from app.models import FactDataQuality
from app.schemas.canonical import CanonicalMetric
from app.services import quality_service as svc

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# The measured dependency map
# ---------------------------------------------------------------------------


class TestDependencyMap:
    def test_it_covers_every_canonical_metric(self) -> None:
        assert set(dependency_map()) == set(CanonicalMetric)

    def test_it_actually_found_dependencies(self) -> None:
        """A measurement that returned nothing would look like a clean bill of
        health while establishing nothing at all."""
        assert sum(len(v) for v in dependency_map().values()) > 50

    def test_neither_minutes_field_is_critical_on_its_own(self) -> None:
        """`minutes` and `recorded_minutes` are a fallback pair.

        The engine divides by the minutes the statistics cover where a provider
        supplies them and by total minutes otherwise, so blanking either alone
        changes nothing. Asserted because it is surprising, and because the
        one-at-a-time map cannot express what follows.
        """
        assert dependency_map()[CanonicalMetric.MINUTES] == frozenset()
        assert dependency_map()[CanonicalMetric.RECORDED_MINUTES] == frozenset()

    def test_a_ratio_depends_on_both_of_its_inputs(self) -> None:
        dependencies = dependency_map()
        assert DerivedMetric.PASS_COMPLETION in dependencies[CanonicalMetric.PASSES]
        assert DerivedMetric.PASS_COMPLETION in dependencies[CanonicalMetric.PASSES_COMPLETED]

    def test_metrics_nothing_depends_on_are_reported_as_such(self) -> None:
        """Not a defect — but a metric nothing computes from is worth knowing
        about, because losing it costs nothing downstream."""
        unused = {m for m, deps in dependency_map().items() if not deps}
        assert CanonicalMetric.STARTS in unused

    def test_penalties_taken_has_dependents(self) -> None:
        """A regression guard on the probe record.

        It once set `penalties_taken` equal to `shots`, so non-penalty shots was
        zero, `shot_conversion` and `shot_quality` divided by zero and were None
        in the baseline — and the measurement concluded, wrongly, that nothing
        depended on penalties at all.
        """
        assert dependency_map()[CanonicalMetric.PENALTIES_TAKEN]

    def test_every_derived_metric_is_reachable(self) -> None:
        """No derived metric may be invisible to the dependency measurement.

        One that never computes in the baseline looks exactly like one nothing
        depends on, and would be silently missing from every impact report.
        """
        reachable = {d for deps in dependency_map().values() for d in deps}
        assert set(DerivedMetric) - reachable == set()


class TestImpactOfAbsence:
    def test_no_absence_costs_nothing(self) -> None:
        impact = impact_of_absence(set())
        assert impact.derived_metrics == frozenset()
        assert impact.scores == frozenset()
        assert impact.roles == frozenset()

    def test_losing_both_minutes_fields_disables_everything(self) -> None:
        """Every per-90 divides by one of them, so losing both takes the whole
        analytical layer.

        This is the case that one-at-a-time measurement cannot see: each field
        alone is covered by the other, so unioning their individual results
        concludes that losing both costs nothing. `impact_of_absence` blanks the
        actual set instead, which is why this passes.
        """
        impact = impact_of_absence({CanonicalMetric.MINUTES, CanonicalMetric.RECORDED_MINUTES})
        assert len(impact.derived_metrics) > 25
        assert DerivedMetric.GOALS_PER90 in impact.derived_metrics
        assert impact.roles == frozenset(get_roles())
        assert impact.scores == frozenset(get_definitions())

    def test_losing_one_minutes_field_disables_nothing(self) -> None:
        """The fallback, stated as an outcome rather than as a mechanism."""
        assert impact_of_absence({CanonicalMetric.MINUTES}).roles == frozenset()
        assert impact_of_absence({CanonicalMetric.RECORDED_MINUTES}).roles == frozenset()

    def test_a_role_survives_a_loss_it_documented(self) -> None:
        """Roles that declare a `min_coverage` below 1.0 have decided, in
        writing, which component they can do without. The impact analysis must
        honour that or it over-reports: it once called all eleven roles touched
        by an absent metric lost, when nine of them renormalise and carry a
        caveat instead."""
        impact = impact_of_absence({CanonicalMetric.AERIAL_DUELS})
        assert "target_forward" not in impact.roles
        assert "defensive_stopper" not in impact.roles

    def test_a_role_still_fails_when_its_defining_component_goes(self) -> None:
        """`min_coverage` is a floor, not a licence. Progressive passing is 30%
        of a deep-lying playmaker and is what the name promises; the role stays
        disabled rather than measuring something else."""
        impact = impact_of_absence({CanonicalMetric.PROGRESSIVE_PASSES})
        assert "deep_lying_playmaker" in impact.roles
        assert "ball_playing_centre_back" in impact.roles

    def test_an_unused_metric_disables_nothing(self) -> None:
        impact = impact_of_absence({CanonicalMetric.STARTS})
        assert impact.roles == frozenset()
        assert impact.scores == frozenset()


# ---------------------------------------------------------------------------
# Coverage classification
# ---------------------------------------------------------------------------


def coverage(
    metric: CanonicalMetric, rows: int, populated: int, best: float = 0.0
) -> MetricCoverage:
    return MetricCoverage(
        metric=metric,
        rows=rows,
        populated=populated,
        best_group="GK" if best else None,
        best_group_coverage=best,
    )


class TestCoverageClassification:
    def test_full_coverage_is_complete(self) -> None:
        assert coverage(CanonicalMetric.MINUTES, 100, 100, 1.0).status == "complete"

    def test_nothing_populated_is_absent(self) -> None:
        assert coverage(CanonicalMetric.XG, 100, 0).status == "absent"

    def test_no_rows_is_unknown_not_absent(self) -> None:
        """An empty table tells you nothing about the provider."""
        assert coverage(CanonicalMetric.XG, 0, 0).status == "unknown"

    def test_a_goalkeeping_metric_is_position_specific_not_sparse(self) -> None:
        """The first version of this check reported saves as sparse at 12%,
        which is not a data problem — it is the share of players who are
        goalkeepers. A check that cries wolf on correct data gets ignored."""
        saves = coverage(CanonicalMetric.SAVES, 1000, 125, best=1.0)
        assert saves.status == "position_specific"
        assert saves.is_position_specific

    def test_genuinely_patchy_data_is_still_sparse(self) -> None:
        """The position-aware rule must not swallow a real gap: patchy
        everywhere, including where the metric belongs."""
        assert coverage(CanonicalMetric.TACKLES, 1000, 200, best=0.3).status == "sparse"

    def test_partial_coverage_is_distinguished_from_complete(self) -> None:
        assert coverage(CanonicalMetric.TACKLES, 1000, 800, best=0.8).status == "partial"

    def test_absent_metrics_are_extracted(self) -> None:
        rows = [
            coverage(CanonicalMetric.MINUTES, 100, 100, 1.0),
            coverage(CanonicalMetric.XG, 100, 0),
            coverage(CanonicalMetric.SAVES, 100, 12, best=1.0),
        ]
        assert absent_metrics(rows) == {CanonicalMetric.XG}


# ---------------------------------------------------------------------------
# The report, against the real database
# ---------------------------------------------------------------------------


class TestReportAgainstTheDatabase:
    def test_freshness_reports_per_source(self, db_session: Session) -> None:
        checks = freshness_checks(db_session)
        assert checks
        assert all(c.status in {"pass", "warn", "fail"} for c in checks)

    def test_coverage_checks_run(self, db_session: Session) -> None:
        checks = coverage_checks(db_session)
        names = {c.name for c in checks}
        assert "minutes_coverage" in names
        assert "metrics_absent" in names

    def test_integrity_checks_run(self, db_session: Session) -> None:
        names = {c.name for c in integrity_checks(db_session)}
        assert names == {"position_group_mapped", "no_orphan_stats"}

    def test_a_check_never_reports_an_unknown_status(self, db_session: Session) -> None:
        """The database constrains status to three values; a fourth would be
        rejected at write time, which is a bad place to find out."""
        from pipelines.quality.report import run

        assert all(c.status in {"pass", "warn", "fail"} for c in run(db_session))


class TestQualityService:
    def test_freshness_summarises_the_latest_run(self, db_session: Session) -> None:
        db_session.add_all(
            [
                FactDataQuality(
                    source="probe",
                    entity="e",
                    check_name="old",
                    status="fail",
                    record_count=1,
                    executed_at=datetime.now(UTC) - timedelta(days=3),
                ),
                FactDataQuality(
                    source="probe",
                    entity="e",
                    check_name="new",
                    status="pass",
                    record_count=1,
                    executed_at=datetime.now(UTC),
                ),
            ]
        )
        db_session.flush()

        probe = next(f for f in svc.freshness(db_session) if f.source == "probe")
        # Only the newest run counts: an old failure that has since been fixed
        # must not keep the page red.
        assert probe.checks_run == 1
        assert probe.failures == 0

    def test_only_the_newest_run_is_listed(self, db_session: Session) -> None:
        checks = svc.latest_checks(db_session)
        by_source: dict[str, set[datetime]] = {}
        for check in checks:
            by_source.setdefault(check.source, set()).add(check.executed_at)
        assert all(len(times) == 1 for times in by_source.values())

    def test_volumes_are_counted(self, db_session: Session) -> None:
        counts = svc.volumes(db_session)
        assert counts.players > 0
        assert counts.player_seasons > 0


class TestQualityEndpoint:
    def test_it_is_public(self, client: TestClient) -> None:
        """Transparency about the data is not gated behind an account."""
        client.cookies.clear()
        assert client.get("/api/v1/data-quality").status_code == 200

    def test_it_returns_what_the_page_needs(self, client: TestClient) -> None:
        body = client.get("/api/v1/data-quality").json()
        assert set(body) == {"meaning", "notice", "volumes", "sources", "checks"}
        assert body["volumes"]["players"] > 0

    def test_the_caveat_travels_with_the_ticks(self, client: TestClient) -> None:
        """A wall of green could easily be read as "the analysis is correct"."""
        body = client.get("/api/v1/data-quality").json()
        assert "do not assess" in body["meaning"]

    def test_no_check_reports_an_unknown_status(self, client: TestClient) -> None:
        body = client.get("/api/v1/data-quality").json()
        assert all(c["status"] in {"pass", "warn", "fail"} for c in body["checks"])


class TestVerificationBeforePublishing:
    """Specification section 23: a failed validation publishes nothing.

    The loader's `--verify` runs this suite *inside* the load transaction and
    rolls back on any failure. These cover the detection half; the rollback
    itself is three lines in `load_providers.main` and was exercised against the
    real database by forcing a failure on a `--replace` load and confirming the
    row counts were unchanged afterwards.
    """

    def test_a_healthy_database_produces_no_failures(self, db_session: Session) -> None:
        from pipelines.quality.report import run

        assert [c for c in run(db_session) if c.failed] == []

    def test_an_impossible_threshold_is_detected_as_a_failure(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If this stopped failing, `--verify` would wave everything through
        and the section 23 guarantee would be vacuous."""
        import pipelines.quality.report as report

        monkeypatch.setattr(report, "MIN_MINUTES_COVERAGE", 1.01)
        failures = [c for c in report.run(db_session) if c.failed]
        assert [c.name for c in failures] == ["minutes_coverage"]

    def test_warnings_alone_never_block_a_publish(self, db_session: Session) -> None:
        """Staleness and absent metrics are facts about a source, not faults in
        a refresh. Blocking on them would stop the pipeline for something no
        rerun can fix."""
        from pipelines.quality.report import run

        checks = run(db_session)
        assert all(not c.failed for c in checks if c.status == "warn")
