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

from app.api.deps import SessionDep
from app.schemas.api import (
    DataQualityResponse,
    QualityCheckOut,
    SourceFreshnessOut,
    VolumesOut,
)
from app.services import quality_service as svc

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
def get_data_quality(db: SessionDep) -> DataQualityResponse:
    """Freshness, volumes and the most recent automated checks per source."""
    checks = svc.latest_checks(db)
    sources = svc.freshness(db)
    counts = svc.volumes(db)

    return DataQualityResponse(
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
            )
            for item in sources
        ],
        checks=[
            QualityCheckOut(
                source=item.source,
                entity=item.entity,
                check_name=item.check_name,
                status=item.status,  # type: ignore[arg-type]
                record_count=item.record_count,
                detail=item.detail,
                executed_at=item.executed_at,
            )
            for item in checks
        ],
    )
