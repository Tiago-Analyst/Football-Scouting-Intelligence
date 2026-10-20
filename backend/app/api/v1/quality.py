"""Data quality endpoint.

Public, and deliberately so. Section 24 requires quality checks to be recorded;
publishing them is what makes the record mean anything to the person reading a
percentile. Someone deciding whether to trust a ranking should be able to see
when the data was last loaded and what the automated checks said about it.

Nothing here reveals an implementation. It reports what was checked, when, and
the outcome — not the queries, the thresholds' derivation, or any provider
field name.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SessionDep, SettingsDep
from app.schemas.api import (
    AnalyticsFreshnessOut,
    CandidateChecksOut,
    CompetitionIdentityCoverageOut,
    DataQualityResponse,
    DerivedMetricOut,
    IdentityCoverageOut,
    MetricAvailabilityOut,
    ProviderQualityOut,
    PublishedChecksOut,
    QualityCheckOut,
    RefreshGenerationOut,
    RefreshStatusOut,
    SourceFreshnessOut,
    VolumesOut,
)
from app.services import quality_service as svc
from app.services.analytics_service import get_analytics_view, view_is_stale

router = APIRouter(prefix="/api/v1", tags=["quality"])

#: Shown with the report. The checks describe the *pipeline's* health, and a
#: reader could easily take a wall of green ticks as a statement about the
#: analysis itself.
QUALITY_MEANING = (
    "These checks describe the data that was loaded: whether it arrived, whether it is "
    "internally consistent, and how much of it is present. They do not assess whether a "
    "metric measures what its name suggests, and they cannot tell you that a ranking is "
    "correct — only that the figures behind it are present and self-consistent."
)

#: Said plainly because the site is running on fabricated data and a page full
#: of passing checks is exactly where that could be forgotten.
NO_CHECKS_YET = (
    "No load has recorded a quality check yet. Until one has, nothing on this page "
    "describes the data being served."
)


@router.get("/data-quality", response_model=DataQualityResponse)
def get_data_quality(db: SessionDep, settings: SettingsDep) -> DataQualityResponse:
    """Freshness, volumes, reconciliation and the most recent checks per source.

    Operational rather than analytical: how much is loaded, how current it is,
    how much of it two sources agreed on, and what the provider cannot supply
    at all. Nothing here exposes a connection string, a credential or a log.
    """
    checks = svc.latest_checks(db)
    candidates = svc.candidate_checks(db)
    providers = svc.provider_quality(db)
    sources = svc.freshness(db)
    counts = svc.volumes(db)
    identity = svc.identity_coverage(db)
    unavailable, derived = svc.metric_availability(settings)
    view = get_analytics_view()

    return DataQualityResponse(
        identity=IdentityCoverageOut(
            players=identity.players,
            matched=identity.matched,
            unmatched=identity.unmatched,
            matched_share=identity.matched_share,
            manual_overrides=identity.manual_overrides,
            ambiguous=identity.ambiguous,
        ),
        identity_by_competition=[
            CompetitionIdentityCoverageOut(
                competition_id=c.competition_id,
                name=c.name,
                players=c.players,
                matched=c.matched,
                matched_share=c.matched_share,
            )
            for c in svc.identity_coverage_by_competition(db)
        ],
        average_detailed_coverage_pct=svc.average_detailed_coverage(db),
        unavailable_metrics=svc.unavailable_metrics(settings),
        unavailable_detail=[
            MetricAvailabilityOut(metric=m.metric, label=m.label, reason=m.reason)
            for m in unavailable
        ],
        derived_metrics=[
            DerivedMetricOut(metric=d.metric, label=d.label, formula=d.formula) for d in derived
        ],
        analytics=AnalyticsFreshnessOut(
            players=len(view.players),
            competitions=len(view.competitions),
            built_at=view.built_at,
            is_stale=view_is_stale(),
        ),
        refresh=_refresh_out(svc.refresh_status(db)),
        meaning=QUALITY_MEANING,
        notice=None if checks else NO_CHECKS_YET,
        volumes=VolumesOut(
            players=counts.players,
            competitions=counts.competitions,
            clubs=counts.clubs,
            player_seasons=counts.player_seasons,
        ),
        sources=[
            SourceFreshnessOut(
                source=item.source,
                last_checked_at=item.last_checked_at,
                age_days=item.age_days,
                checks_run=item.checks_run,
                failures=item.failures,
                warnings=item.warnings,
                last_published_at=item.last_published_at,
                data_age_days=item.data_age_days,
                rows_published=item.rows_published,
                last_load_attempt_at=item.last_load_attempt_at,
            )
            for item in sources
        ],
        checks=[_check_out(item) for item in checks],
        published_generation_id=svc.published_generation_id(db),
        candidate=[_candidate_out(group) for group in candidates],
        providers=[
            ProviderQualityOut(
                source=item.source,
                published=(
                    PublishedChecksOut(
                        source=item.published.source,
                        refresh_id=item.published.refresh_id,
                        generation_id=item.published.generation_id,
                        published_at=item.published.published_at,
                        executed_at=item.published.executed_at,
                        checks=[_check_out(c) for c in item.published.checks],
                    )
                    if item.published
                    else None
                ),
                candidate=_candidate_out(item.candidate) if item.candidate else None,
            )
            for item in providers
        ],
    )


def _candidate_out(group) -> CandidateChecksOut:  # type: ignore[no-untyped-def]
    return CandidateChecksOut(
        source=group.source,
        refresh_id=group.refresh_id,
        generation_id=group.generation_id,
        executed_at=group.executed_at,
        checks=[_check_out(item) for item in group.checks],
    )


def _check_out(item) -> QualityCheckOut:  # type: ignore[no-untyped-def]
    return QualityCheckOut(
        source=item.source,
        entity=item.entity,
        check_name=item.check_name,
        status=item.status,
        record_count=item.record_count,
        detail=item.detail,
        executed_at=item.executed_at,
        refresh_id=item.refresh_id,
        generation_id=item.generation_id,
        context=item.context,
    )


def _generation_out(summary) -> RefreshGenerationOut:  # type: ignore[no-untyped-def]
    return RefreshGenerationOut(
        generation_id=summary.generation_id,
        status=summary.status,
        created_at=summary.created_at,
        last_updated_at=summary.last_updated_at,
        published_at=summary.published_at,
        total_expected_players=summary.total_expected_players,
        completed_players=summary.completed_players,
        failed_players=summary.failed_players,
        completion_pct=summary.completion_pct,
        competitions_complete=summary.competitions_complete,
        competitions_expected=summary.competitions_expected,
        complete=summary.complete,
    )


def _refresh_out(status) -> RefreshStatusOut | None:  # type: ignore[no-untyped-def]
    """`None` stays `None`: no generation directory means nothing to show, and
    an empty progress bar would imply a stalled refresh."""
    if status is None:
        return None
    return RefreshStatusOut(
        state=status.state,
        state_key=status.state_key,
        published=_generation_out(status.published) if status.published else None,
        current=_generation_out(status.current) if status.current else None,
    )
