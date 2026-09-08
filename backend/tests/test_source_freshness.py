"""Checked, loaded, published - three timestamps that are not each other.

`fact_data_quality.executed_at` was once the only per-source timestamp and the
site had nothing else to read, which let the page say "performance data updated
today" about data a fortnight old: checks run against whatever is serving.

The staging schema then split the remaining pair. A load writes to
`analytics_staging`, and a staging load that fails identity resolution or a
quality gate never becomes production - so `fact_source_load.loaded_at` stopped
meaning "the figures on screen changed" and started meaning "a refresh got as
far as staging". Freshness reads `fact_source_publication` instead, which is
written inside the promotion transaction and therefore cannot exist for a
dataset nobody is being served.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import FactDataQuality, FactSourceLoad, FactSourcePublication
from app.services.quality_service import (
    freshness,
    last_load_attempts,
    last_loads,
    last_publications,
)

pytestmark = pytest.mark.integration


def a_load(session: Session, source: str, when: datetime, rows: int = 100) -> None:
    session.add(FactSourceLoad(source=source, loaded_at=when, rows_loaded=rows))
    session.flush()


def a_publication(
    session: Session,
    source: str,
    when: datetime,
    rows: int = 100,
    generation_id: str | None = None,
) -> None:
    session.add(
        FactSourcePublication(
            source=source,
            generation_id=generation_id,
            published_at=when,
            rows_published=rows,
        )
    )
    session.flush()


def a_check(session: Session, source: str, when: datetime, status: str = "pass") -> None:
    session.add(
        FactDataQuality(
            source=source,
            entity="player",
            check_name="a_check",
            status=status,
            record_count=1,
            executed_at=when,
        )
    )
    session.flush()


class TestTheLoadLedger:
    """Unchanged, and still worth having: `/health` reports load attempts so an
    operator can see the pipeline running even while nothing is publishing."""

    def test_the_latest_load_wins(self, db_session: Session) -> None:
        old = datetime.now(UTC) - timedelta(days=10)
        new = datetime.now(UTC) - timedelta(days=1)
        a_load(db_session, "a_test_source", old, rows=10)
        a_load(db_session, "a_test_source", new, rows=20)

        loaded_at, rows = last_loads(db_session)["a_test_source"]
        assert loaded_at == new
        assert rows == 20

    def test_sources_are_reported_separately(self, db_session: Session) -> None:
        """The requirement in one assertion.

        A single "updated today" label would be wrong whenever one source
        refreshed and the other did not, which is the normal case: the
        performance and market pipelines run on different schedules.
        """
        recent = datetime.now(UTC) - timedelta(hours=2)
        stale = datetime.now(UTC) - timedelta(days=14)
        a_load(db_session, "source_recent", recent)
        a_load(db_session, "source_stale", stale)

        loads = last_loads(db_session)
        assert loads["source_recent"][0] != loads["source_stale"][0]

    def test_a_source_never_loaded_is_absent_rather_than_guessed(self, db_session: Session) -> None:
        assert "never_loaded_source" not in last_loads(db_session)


class TestFreshnessKeepsThemApart:
    def test_a_check_today_does_not_make_the_data_fresh(self, db_session: Session) -> None:
        """The mistake the publication table exists to prevent."""
        published = datetime.now(UTC) - timedelta(days=14)
        checked = datetime.now(UTC) - timedelta(minutes=5)
        a_publication(db_session, "divergent_source", published)
        a_check(db_session, "divergent_source", checked)

        entry = next(f for f in freshness(db_session) if f.source == "divergent_source")
        assert entry.age_days == 0, "the checks did run today"
        assert entry.data_age_days == 14, "and the data is still a fortnight old"
        assert entry.last_published_at == published
        assert entry.last_checked_at == checked

    def test_a_staging_load_today_does_not_make_the_data_fresh_either(
        self, db_session: Session
    ) -> None:
        """The live failure this pass was written for.

        A refresh loads FootyStats into staging at 10:00 and identity
        resolution fails at 10:20. Production is untouched and the site is
        still serving the fortnight-old dataset - so the reported age must
        still be a fortnight, however recently the loader ran.
        """
        published = datetime.now(UTC) - timedelta(days=14)
        loaded = datetime.now(UTC) - timedelta(minutes=20)
        a_publication(db_session, "stalled_refresh_source", published, rows=50_000)
        a_load(db_session, "stalled_refresh_source", loaded, rows=61_000)
        a_check(db_session, "stalled_refresh_source", datetime.now(UTC))

        entry = next(f for f in freshness(db_session) if f.source == "stalled_refresh_source")
        assert entry.data_age_days == 14, "nothing new has been published"
        assert entry.last_published_at == published
        assert entry.rows_published == 50_000, "the served rows, not the staged ones"
        assert entry.last_load_attempt_at == loaded, "the attempt is still visible"

    def test_an_unpublished_source_reports_nothing_rather_than_the_load_time(
        self, db_session: Session
    ) -> None:
        """Absent, not inferred.

        A source that has only ever been loaded into staging has never reached
        a reader. Reporting the load time as the data age would be the original
        bug arriving through a different table.
        """
        loaded = datetime.now(UTC) - timedelta(hours=1)
        a_load(db_session, "never_published_source", loaded)
        a_check(db_session, "never_published_source", datetime.now(UTC))

        entry = next(f for f in freshness(db_session) if f.source == "never_published_source")
        assert entry.last_published_at is None
        assert entry.data_age_days is None
        assert entry.rows_published is None
        assert entry.last_load_attempt_at == loaded

    def test_an_unrecorded_publication_reports_nothing_rather_than_the_check_time(
        self, db_session: Session
    ) -> None:
        a_check(db_session, "checked_only_source", datetime.now(UTC))

        entry = next(f for f in freshness(db_session) if f.source == "checked_only_source")
        assert entry.last_published_at is None
        assert entry.data_age_days is None
        assert entry.rows_published is None
        assert entry.last_load_attempt_at is None


class TestThePublicationLedger:
    def test_the_latest_publication_wins(self, db_session: Session) -> None:
        old = datetime.now(UTC) - timedelta(days=10)
        new = datetime.now(UTC) - timedelta(days=1)
        a_publication(db_session, "a_published_source", old, rows=10)
        a_publication(db_session, "a_published_source", new, rows=20)

        published_at, rows = last_publications(db_session)["a_published_source"]
        assert published_at == new
        assert rows == 20

    def test_one_provider_publishing_does_not_refresh_the_other(self, db_session: Session) -> None:
        """A promotion publishes the whole universe and only one provider in it
        is new. The other's data is the one published a fortnight ago, and its
        freshness must say so."""
        market_published = datetime.now(UTC) - timedelta(minutes=5)
        performance_published = datetime.now(UTC) - timedelta(days=14)
        a_publication(db_session, "market_source", market_published)
        a_publication(db_session, "performance_source", performance_published)
        a_check(db_session, "market_source", datetime.now(UTC))
        a_check(db_session, "performance_source", datetime.now(UTC))

        entries = {f.source: f for f in freshness(db_session)}
        assert entries["market_source"].data_age_days == 0
        assert entries["performance_source"].data_age_days == 14

    def test_attempts_are_reported_separately(self, db_session: Session) -> None:
        loaded = datetime.now(UTC) - timedelta(minutes=3)
        a_load(db_session, "attempt_only_source", loaded)
        assert last_load_attempts(db_session)["attempt_only_source"] == loaded
        assert "attempt_only_source" not in last_publications(db_session)


class TestTheLoaderRecordsIt:
    def test_a_load_is_recorded_inside_its_own_transaction(self, db_session: Session) -> None:
        """Which is what makes a rolled-back load unable to claim a refresh.

        The row is written by `ProviderLoader.record_load` before the commit,
        so a load that fails its checks discards the claim along with the data
        it was about. Asserted here by rolling back and finding nothing.
        """
        a_load(db_session, "rolled_back_source", datetime.now(UTC))
        assert "rolled_back_source" in last_loads(db_session)

        db_session.rollback()
        assert "rolled_back_source" not in last_loads(db_session)

    def test_the_loader_writes_one(self) -> None:
        """The call is present in the load sequence rather than optional."""
        import inspect

        from pipelines.load.load_providers import ProviderLoader

        run = inspect.getsource(ProviderLoader.run)
        assert "self.record_load()" in run
        assert run.index("self.persist_checks()") < run.index("self.record_load()")
