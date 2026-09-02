"""When the data was loaded, which is not when it was checked.

`fact_data_quality.executed_at` was the only per-source timestamp, and the site
had nothing else to read. It answers a different question: checks run against
data nobody reloaded, and a load that rolled back leaves the previous run's
checks sitting there looking recent. Reading one as the other lets the page say
"performance data updated today" about data a fortnight old.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import FactDataQuality, FactSourceLoad
from app.services.quality_service import freshness, last_loads

pytestmark = pytest.mark.integration


def a_load(session: Session, source: str, when: datetime, rows: int = 100) -> None:
    session.add(FactSourceLoad(source=source, loaded_at=when, rows_loaded=rows))
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


class TestTheLoadTimestamp:
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


class TestFreshnessKeepsTheTwoApart:
    def test_a_check_today_does_not_make_the_data_fresh(self, db_session: Session) -> None:
        """The mistake this whole table exists to prevent."""
        loaded = datetime.now(UTC) - timedelta(days=14)
        checked = datetime.now(UTC) - timedelta(minutes=5)
        a_load(db_session, "divergent_source", loaded)
        a_check(db_session, "divergent_source", checked)

        entry = next(f for f in freshness(db_session) if f.source == "divergent_source")
        assert entry.age_days == 0, "the checks did run today"
        assert entry.data_age_days == 14, "and the data is still a fortnight old"
        assert entry.last_loaded_at == loaded
        assert entry.last_checked_at == checked

    def test_an_unrecorded_load_reports_nothing_rather_than_the_check_time(
        self, db_session: Session
    ) -> None:
        """Absent, not inferred.

        A source loaded before this was recorded has an unknown load time, and
        the honest answer is to say so - filling it in from the check time is
        precisely the error being fixed.
        """
        a_check(db_session, "checked_only_source", datetime.now(UTC))

        entry = next(f for f in freshness(db_session) if f.source == "checked_only_source")
        assert entry.last_loaded_at is None
        assert entry.data_age_days is None
        assert entry.rows_loaded is None


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
