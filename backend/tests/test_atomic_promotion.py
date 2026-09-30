"""Nothing reaches readers until every check has passed against it.

THE GAP THIS CLOSES
===================

A refresh used to load straight into the served tables. `--verify` ran the
serving quality suite inside that transaction, so a load producing bad data
rolled back. But everything after the commit - identity resolution, the prune,
the data-quality report, the independent analytics validation - ran against
data readers were already being served.

A failure in any of them left the site serving a dataset nothing had finished
checking, recoverable only by somebody noticing.

THE MODEL
=========

A refresh loads into `analytics_staging` and every check runs against it.
Promotion is three schema renames in one transaction, and it is the only moment
anything becomes production.

WHAT MAKES IT POSSIBLE
======================

The analytical tables are closed under foreign keys, and `shortlist_entry`
stores `player_key` as a plain string rather than referencing `dim_player`.
A referencing row in an operational table would break the instant the
referenced table was swapped away. The first test here asserts that property,
because losing it silently would make every other test in this file a lie.
"""

from __future__ import annotations

import pathlib

# ruff: noqa: S608 - every interpolated name here is a module constant
# naming a schema, never a value from outside this file.
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_engine

pytestmark = pytest.mark.integration

SERVING = "analytics"
STAGING = "analytics_staging"

ANALYTICAL = {
    "dim_competition",
    "dim_season",
    "dim_club",
    "dim_player",
    "bridge_player_source",
    "fact_player_season_stats",
    "fact_market_value",
    "fact_transfer",
}

#: Records of what happened, which must outlive the data they describe.
OPERATIONAL = {
    "alembic_version",
    "fact_data_quality",
    "fact_source_load",
    "fact_source_publication",
    "fact_refresh_generation",
    "shortlist",
    "shortlist_entry",
    "user_account",
    "user_session",
}


def tables_in(connection, schema: str) -> set[str]:  # type: ignore[no-untyped-def]
    return {
        row[0]
        for row in connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = :s"), {"s": schema}
        )
    }


class TestTheClusterIsClosedUnderForeignKeys:
    """The property the whole design rests on."""

    def test_nothing_operational_references_the_analytical_tables(self) -> None:
        with get_engine().connect() as connection:
            rows = connection.execute(
                text("""
                    SELECT child_ns.nspname AS child_schema, child.relname AS child,
                           parent_ns.nspname AS parent_schema, parent.relname AS parent
                    FROM pg_constraint con
                    JOIN pg_class child ON child.oid = con.conrelid
                    JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
                    JOIN pg_class parent ON parent.oid = con.confrelid
                    JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
                    WHERE con.contype = 'f'
                """)
            ).all()

        crossing = [
            f"{c_ns}.{child} -> {p_ns}.{parent}"
            for c_ns, child, p_ns, parent in rows
            if c_ns != p_ns
        ]
        assert crossing == [], (
            f"a foreign key crosses schemas, so swapping the analytical schema would "
            f"break it: {crossing}"
        )

    def test_shortlists_hold_a_player_key_rather_than_a_foreign_key(self) -> None:
        """The specific fact that makes the cluster movable.

        If shortlists ever gain a real foreign key to `dim_player`, atomic
        promotion stops being safe and this test is where that is discovered.
        """
        with get_engine().connect() as connection:
            columns = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'shortlist_entry'"
                    )
                )
            }
        assert "player_key" in columns
        assert "player_id" not in columns


class TestTheSchemasAreSplitCorrectly:
    def test_the_analytical_tables_live_in_their_own_schema(self) -> None:
        with get_engine().connect() as connection:
            assert tables_in(connection, SERVING) == ANALYTICAL

    def test_staging_mirrors_it(self) -> None:
        with get_engine().connect() as connection:
            assert tables_in(connection, STAGING) == ANALYTICAL

    def test_the_operational_tables_stay_in_public(self) -> None:
        """Accounts, shortlists and the histories are never swapped."""
        with get_engine().connect() as connection:
            assert tables_in(connection, "public") == OPERATIONAL

    def test_staging_has_the_same_foreign_keys_as_production(self) -> None:
        """`CREATE TABLE ... LIKE` omits foreign keys; the migration replays them."""
        with get_engine().connect() as connection:
            counts = dict(
                connection.execute(
                    text("""
                        SELECT nsp.nspname, count(*)
                        FROM pg_constraint con
                        JOIN pg_class rel ON rel.oid = con.conrelid
                        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                        WHERE con.contype = 'f' AND nsp.nspname IN (:a, :b)
                        GROUP BY nsp.nspname
                    """),
                    {"a": SERVING, "b": STAGING},
                ).all()
            )
        assert counts.get(SERVING) == counts.get(STAGING)
        assert counts.get(SERVING, 0) > 0

    def test_staging_foreign_keys_point_at_staging(self) -> None:
        """Not at production. A staging row referencing a production parent
        would be corrupted the moment the schemas swapped."""
        with get_engine().connect() as connection:
            definitions = [
                row[0]
                for row in connection.execute(
                    text("""
                        SELECT pg_get_constraintdef(con.oid)
                        FROM pg_constraint con
                        JOIN pg_class rel ON rel.oid = con.conrelid
                        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                        WHERE con.contype = 'f' AND nsp.nspname = :s
                    """),
                    {"s": STAGING},
                )
            ]
        assert definitions
        for definition in definitions:
            assert STAGING in definition, definition


class TestTheApplicationStillSeesItsData:
    def test_models_resolve_without_naming_a_schema(self) -> None:
        """The search path does the work, so one set of models serves both."""
        from app.models import DimPlayer

        assert DimPlayer.__table__.schema is None

    def test_the_analytical_tables_are_readable(self) -> None:
        with get_engine().connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM dim_player")).scalar() > 0

    def test_the_operational_tables_are_readable_too(self) -> None:
        """`public` stays behind the analytical schema on the path."""
        with get_engine().connect() as connection:
            connection.execute(text("SELECT count(*) FROM user_account")).scalar()


class TestTheSafetyChecks:
    def test_an_empty_staging_schema_is_refused(self) -> None:
        from pipelines.load.promote import SchemaCounts, check

        reasons = check(
            SchemaCounts(players=50_000, player_seasons=8_701, competitions=112),
            SchemaCounts(players=0, player_seasons=0, competitions=0),
        )
        assert reasons
        assert "nothing to promote" in reasons[0]

    def test_a_large_drop_is_refused(self) -> None:
        """The shape of a load that stopped a third of the way through.

        Internally consistent, and simply missing most of a season - which no
        later check can detect, because everything present is correct.
        """
        from pipelines.load.promote import SchemaCounts, check

        reasons = check(
            SchemaCounts(players=50_000, player_seasons=8_701, competitions=112),
            SchemaCounts(players=18_000, player_seasons=3_000, competitions=40),
        )
        assert reasons
        assert "stopped partway" in reasons[0]

    def test_an_ordinary_refresh_is_allowed(self) -> None:
        from pipelines.load.promote import SchemaCounts, check

        assert (
            check(
                SchemaCounts(players=50_000, player_seasons=8_701, competitions=112),
                SchemaCounts(players=50_400, player_seasons=8_820, competitions=112),
            )
            == []
        )

    def test_a_modest_shrink_is_allowed(self) -> None:
        """Seasons end and competitions drop out. Only a fragment is refused."""
        from pipelines.load.promote import SchemaCounts, check

        assert (
            check(
                SchemaCounts(players=50_000, player_seasons=8_701, competitions=112),
                SchemaCounts(players=48_000, player_seasons=8_000, competitions=110),
            )
            == []
        )

    def test_the_first_promotion_into_an_empty_production_is_allowed(self) -> None:
        from pipelines.load.promote import SchemaCounts, check

        assert (
            check(
                SchemaCounts(players=0, player_seasons=0, competitions=0),
                SchemaCounts(players=100, player_seasons=200, competitions=3),
            )
            == []
        )


class TestTheSwapItself:
    """Performed for real, then undone, on a marker row rather than the dataset."""

    def test_it_exchanges_the_two_schemas_and_rolls_back(self) -> None:
        from pipelines.load.promote import swap

        engine = get_engine()
        marker = "promotion-test-marker"

        with engine.begin() as connection:
            connection.execute(
                text(
                    f'INSERT INTO "{STAGING}".dim_competition '
                    "(competition_id, name, country, source) "
                    "VALUES (:k, :n, :c, :s)"
                ),
                {"k": marker, "n": "Marker", "c": "Nowhere", "s": "test"},
            )

        def marker_in(schema: str) -> bool:
            with engine.connect() as connection:
                return bool(
                    connection.execute(
                        text(
                            f'SELECT count(*) FROM "{schema}".dim_competition '
                            "WHERE competition_id = :k"
                        ),
                        {"k": marker},
                    ).scalar()
                )

        assert marker_in(STAGING) and not marker_in(SERVING)

        try:
            with engine.begin() as connection:
                swap(connection)
            # The staged schema is now serving, and the previous one is staged.
            assert marker_in(SERVING) and not marker_in(STAGING)
        finally:
            # Swap back, whatever happened, then remove the marker.
            with engine.begin() as connection:
                swap(connection)
            with engine.begin() as connection:
                connection.execute(
                    text(f'DELETE FROM "{STAGING}".dim_competition WHERE competition_id = :k'),
                    {"k": marker},
                )

        assert not marker_in(SERVING) and not marker_in(STAGING)

    def test_the_real_dataset_survives_a_round_trip(self) -> None:
        """The promotion path must not be a way to lose production."""
        from pipelines.load.promote import swap

        engine = get_engine()
        with engine.connect() as connection:
            before = connection.execute(
                text(f'SELECT count(*) FROM "{SERVING}".fact_player_season_stats')
            ).scalar()

        with engine.begin() as connection:
            swap(connection)
        with engine.begin() as connection:
            swap(connection)

        with engine.connect() as connection:
            after = connection.execute(
                text(f'SELECT count(*) FROM "{SERVING}".fact_player_season_stats')
            ).scalar()
        assert after == before


class TestRollbackIsTheSameOperation:
    def test_a_rollback_is_not_blocked_by_the_row_count_guard(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """The recovery path must not fail exactly when it is needed.

        Staging is empty here, which the promotion guard refuses outright. A
        rollback is a different decision - go back to what was serving an hour
        ago - and refusing it for the same reason would be refusing to recover.
        """
        from pipelines.load.promote import main

        # No --apply: this reports what it would do and changes nothing.
        assert main(["--rollback"]) == 0
        assert "swap back" in capsys.readouterr().out.lower()

    def test_promotion_of_an_empty_staging_is_refused(self) -> None:
        """The contrast that makes the test above meaningful.

        Asserted against `check` rather than by driving `main`: a `--apply`
        that got past the refusal would really promote, and a test that only
        passes while the developer's staging schema happens to be empty is a
        test that swaps their database the day it stops being.
        """
        from pipelines.load.promote import SchemaCounts, check

        production = SchemaCounts(players=9_000, player_seasons=17_000, competitions=40)
        empty = SchemaCounts(players=0, player_seasons=0, competitions=0)

        reasons = check(production, empty)
        assert reasons
        assert "nothing to promote" in reasons[0]

    def test_promotion_without_a_source_is_refused(self, capsys: pytest.CaptureFixture) -> None:
        """A promotion advances one provider's freshness and only one.

        Publishing a Transfermarkt refresh must not restamp FootyStats: the
        performance figures in that dataset are the ones published a fortnight
        ago. Which provider is new cannot be inferred from row counts, so a
        promotion that does not say is refused rather than guessed.
        """
        from pipelines.load.promote import main

        assert main(["--apply"]) == 2
        assert "--source is required" in capsys.readouterr().err

    def test_the_previous_dataset_lands_in_staging(self) -> None:
        """Which is what makes one swap a complete recovery."""
        from pipelines.load.promote import SERVING, STAGING, swap

        engine = get_engine()
        with engine.connect() as connection:
            served_before = connection.execute(
                text(f'SELECT count(*) FROM "{SERVING}".fact_player_season_stats')
            ).scalar()

        try:
            with engine.begin() as connection:
                swap(connection)
            with engine.connect() as connection:
                staged_after = connection.execute(
                    text(f'SELECT count(*) FROM "{STAGING}".fact_player_season_stats')
                ).scalar()
            assert staged_after == served_before, (
                "the dataset that was serving is not in staging, so a rollback would not restore it"
            )
        finally:
            with engine.begin() as connection:
                swap(connection)


class TestTheTwoSchemasStayIdentical:
    """The ongoing cost of this design, made loud rather than left implicit.

    A migration that adds a column to an analytical table must add it to both
    schemas. Miss one and the failure arrives at the next promotion: the
    swapped-in schema is missing a column the application expects, and the
    error surfaces in the serving layer rather than in the migration that
    caused it.

    So structural parity is asserted here, where a missed migration fails
    immediately and names the difference.
    """

    def _columns(self, connection, schema: str):  # type: ignore[no-untyped-def]
        return {
            (row[0], row[1], row[2], row[3])
            for row in connection.execute(
                text("""
                    SELECT table_name, column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = :s
                """),
                {"s": schema},
            )
        }

    def test_the_columns_match(self) -> None:
        with get_engine().connect() as connection:
            serving = self._columns(connection, SERVING)
            staging = self._columns(connection, STAGING)

        only_serving = sorted(serving - staging)
        only_staging = sorted(staging - serving)
        assert not only_serving, f"missing from staging: {only_serving}"
        assert not only_staging, f"missing from production: {only_staging}"

    def _constraints(self, connection, schema: str):  # type: ignore[no-untyped-def]
        return {
            (row[0], row[1], row[2])
            for row in connection.execute(
                text("""
                    SELECT rel.relname, con.conname, con.contype
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                    WHERE nsp.nspname = :s
                """),
                {"s": schema},
            )
        }

    def test_the_constraints_match(self) -> None:
        """Including the check constraints, which are what stop a bad load."""
        with get_engine().connect() as connection:
            serving = self._constraints(connection, SERVING)
            staging = self._constraints(connection, STAGING)

        assert sorted(serving - staging) == [], "constraints missing from staging"
        assert sorted(staging - serving) == [], "constraints missing from production"

    def test_the_indexes_match(self) -> None:
        """A staging load without production's indexes would be slow and would
        promote into a schema that then stayed slow."""
        with get_engine().connect() as connection:

            def indexes(schema: str) -> set[tuple[str, str]]:
                return {
                    (row[0], row[1])
                    for row in connection.execute(
                        text("SELECT tablename, indexname FROM pg_indexes WHERE schemaname = :s"),
                        {"s": schema},
                    )
                }

            assert indexes(SERVING) == indexes(STAGING)


class TestMigrationsDefaultToPublic:
    def test_alembic_pins_its_search_path(self) -> None:
        """Otherwise a new operational table lands in the analytical schema and
        is swapped away by the next promotion.

        Set on the engine rather than with a statement on the connection.
        Issuing `SET search_path` through `exec_driver_sql` opens an implicit
        transaction that alembic's own `begin_transaction()` cannot manage, so
        every migration reported success and was rolled back when the
        connection closed - silently in both directions, because the version
        table was rolled back with it.
        """
        import pathlib

        env = (pathlib.Path(__file__).resolve().parents[1] / "alembic" / "env.py").read_text(
            encoding="utf-8"
        )
        assert 'connect_args={"options": "-csearch_path=public"}' in env
        # Code lines only: the comment above the fix names the technique it
        # replaced, and a test that could not tell the two apart would forbid
        # explaining the bug.
        code = [line for line in env.splitlines() if not line.lstrip().startswith("#")]
        assert not any("exec_driver_sql" in line for line in code), (
            "a statement on the connection begins a transaction alembic cannot "
            "manage, which makes every migration a silent no-op"
        )

    def test_a_migration_actually_commits(self) -> None:
        """The regression the assertion above protects against.

        A no-op migration is invisible: the schema is unchanged and so is the
        version table, so re-running does the same nothing.

        Compared against whatever alembic's scripts say is head, rather than a
        revision written down here: pinning the id would make this fail on
        every new migration for a reason that has nothing to do with what it
        is testing.
        """
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        backend = pathlib.Path(__file__).resolve().parents[1]
        head = ScriptDirectory.from_config(Config(str(backend / "alembic.ini"))).get_current_head()

        with get_engine().connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar()
        assert version == head, (
            f"the database is at {version} and the scripts are at {head}; "
            f"migrations are not being committed"
        )

    def test_the_version_table_is_operational(self) -> None:
        """It records which migrations ran, not what the data is."""
        with get_engine().connect() as connection:
            assert "alembic_version" in tables_in(connection, "public")
            assert "alembic_version" not in tables_in(connection, SERVING)


class TestPublicationIsPartOfThePromotion:
    """`fact_source_load` stopped being able to answer "is this live?".

    The loader writes it, and the loader writes to staging. A refresh that
    loads at 10:00 and fails identity resolution at 10:20 leaves a load row
    stamped 10:00 while production still serves yesterday - and the site
    footer, reading that ledger, announced 10:00 on every page.

    So publication is recorded by the promotion instead, in the promotion's own
    transaction. These tests are about that transaction rather than about the
    row: a publication row that can be written without the swap, or a swap that
    can commit without the row, puts the two facts back out of step.
    """

    GENERATION = "29990101T000000Z"
    SOURCE = "a_test_provider"

    @pytest.fixture
    def a_complete_generation(self):  # type: ignore[no-untyped-def]
        """A generation waiting to be published, cleaned up afterwards.

        Its own row rather than a borrowed one: the generations in a developer's
        database are real refreshes, and a test that flipped one to PUBLISHED
        would change what the gate does on the next local run.
        """
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.fact_refresh_generation "
                    "(generation_id, source, status, created_at, updated_at, complete, "
                    " total_expected_players, completed_players, failed_players, "
                    " competitions_expected, competitions_complete) "
                    "VALUES (:g, :s, 'COMPLETE', now(), now(), true, 0, 0, 0, 0, 0)"
                ),
                {"g": self.GENERATION, "s": self.SOURCE},
            )
        yield self.GENERATION
        with get_engine().begin() as connection:
            connection.execute(
                text("DELETE FROM public.fact_source_publication WHERE source = :s"),
                {"s": self.SOURCE},
            )
            connection.execute(
                text("DELETE FROM public.fact_refresh_generation WHERE source = :s"),
                {"s": self.SOURCE},
            )

    def _publications(self, connection) -> list[tuple]:  # type: ignore[no-untyped-def]
        return connection.execute(
            text(
                "SELECT generation_id, rows_published FROM public.fact_source_publication "
                "WHERE source = :s"
            ),
            {"s": self.SOURCE},
        ).all()

    def _status(self, connection) -> str | None:  # type: ignore[no-untyped-def]
        return connection.execute(
            text("SELECT status FROM public.fact_refresh_generation WHERE source = :s"),
            {"s": self.SOURCE},
        ).scalar()

    def test_a_promotion_that_rolls_back_publishes_nothing(
        self, a_complete_generation: str
    ) -> None:
        """The property the whole design rests on.

        If the swap is undone, the claim that something was published has to go
        with it - otherwise the site reports a dataset that never reached it.
        """
        from pipelines.load.promote import record_publication, swap

        with get_engine().connect() as connection, connection.begin():
            swap(connection)
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=a_complete_generation,
                rows_published=17_000,
            )
            assert self._publications(connection), "written inside the transaction"
            assert self._status(connection) == "PUBLISHED"
            connection.rollback()

        with get_engine().connect() as connection:
            assert self._publications(connection) == [], "and gone with it"
            assert self._status(connection) == "COMPLETE", "the generation is unpublished too"

    def test_publishing_moves_the_generation_to_published(self, a_complete_generation: str) -> None:
        from pipelines.load.promote import record_publication

        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=a_complete_generation,
                rows_published=17_000,
            )

        with get_engine().connect() as connection:
            assert self._publications(connection) == [(a_complete_generation, 17_000)]
            assert self._status(connection) == "PUBLISHED"

    def test_a_rollback_retracts_the_publication(self, a_complete_generation: str) -> None:
        """A rollback really does un-publish.

        Leaving the row in place would make freshness report the retracted
        dataset, which is the same lie by a different route. The generation
        goes back to VALIDATED so the gate offers it again rather than treating
        it as finished.
        """
        from pipelines.load.promote import record_publication, retract_publication

        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=a_complete_generation,
                rows_published=17_000,
            )

        with get_engine().begin() as connection:
            retracted = retract_publication(connection)

        assert retracted == (self.SOURCE, a_complete_generation)
        with get_engine().connect() as connection:
            assert self._publications(connection) == []
            assert self._status(connection) == "VALIDATED"

    def test_a_failed_generation_is_not_dragged_back_to_life(
        self, a_complete_generation: str
    ) -> None:
        """Publishing is guarded on the current status rather than set blindly.

        A generation abandoned as FAILED has no business becoming PUBLISHED
        because somebody re-ran the promotion, and a publication row is still
        written: something *was* promoted, and the record of it is separate
        from which generation gets the credit.
        """
        from pipelines.load.promote import record_publication

        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.fact_refresh_generation SET status = 'FAILED' WHERE source = :s"
                ),
                {"s": self.SOURCE},
            )
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=a_complete_generation,
                rows_published=17_000,
            )

        with get_engine().connect() as connection:
            assert self._status(connection) == "FAILED"
            assert self._publications(connection) == [(a_complete_generation, 17_000)]

    def test_a_provider_without_a_generation_still_publishes(self) -> None:
        """Transfermarkt is a dataset download, not a resumable fetch.

        `None` is an ordinary answer here, and refusing to record a publication
        without one would leave the market data with no freshness at all.
        """
        from pipelines.load.promote import record_publication

        try:
            with get_engine().begin() as connection:
                record_publication(
                    connection, source=self.SOURCE, generation_id=None, rows_published=80_000
                )
            with get_engine().connect() as connection:
                assert self._publications(connection) == [(None, 80_000)]
        finally:
            with get_engine().begin() as connection:
                connection.execute(
                    text("DELETE FROM public.fact_source_publication WHERE source = :s"),
                    {"s": self.SOURCE},
                )


class TestARefreshKeepsTheOtherProvider:
    """The failure that would have published half a universe.

    Production holds two providers. FootyStats supplies performance;
    Transfermarkt supplies identity, market values and transfers. A refresh
    replaces one of them, and staging was empty - so the next FootyStats
    refresh would have loaded performance data into nothing and promoted it,
    and production would have become a universe with every market value and
    every transfer missing. Silently, because the result is internally
    consistent and simply has no Transfermarkt in it.

    Everything here runs inside a transaction that is rolled back. Staging is a
    real schema on the developer's database, and a test that left it rebuilt
    would be a test that changed what the next promotion promotes.
    """

    def _counts(self, connection, schema: str) -> dict[str, int]:  # type: ignore[no-untyped-def]
        from pipelines.load.prepare_staging import ANALYTICAL_TABLES

        return {
            table: int(
                connection.execute(text(f'SELECT count(*) FROM "{schema}"."{table}"')).scalar() or 0
            )
            for table in ANALYTICAL_TABLES
        }

    def test_seeding_copies_production_row_for_row(self) -> None:
        from pipelines.load.prepare_staging import prepare

        with get_engine().connect() as connection, connection.begin() as transaction:
            production = self._counts(connection, SERVING)
            prepare(connection)
            assert self._counts(connection, STAGING) == production
            transaction.rollback()

    def test_the_seeded_sequences_do_not_hand_out_ids_that_exist(self) -> None:
        """The copy preserves primary keys. A sequence left at 1 would give the
        next insert an id already taken, and every load after a seed would fail
        on its first new player."""
        from pipelines.load.prepare_staging import prepare

        with get_engine().connect() as connection, connection.begin() as transaction:
            prepare(connection)
            rows = connection.execute(
                text(
                    "SELECT c.relname, a.attname, "
                    "  pg_get_serial_sequence(quote_ident(n.nspname) || '.' || "
                    "                         quote_ident(c.relname), a.attname) "
                    "FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "JOIN pg_attribute a ON a.attrelid = c.oid "
                    "WHERE n.nspname = :schema AND a.attnum > 0 AND NOT a.attisdropped "
                    "  AND pg_get_serial_sequence(quote_ident(n.nspname) || '.' || "
                    "                             quote_ident(c.relname), a.attname) IS NOT NULL"
                ),
                {"schema": STAGING},
            ).all()
            assert rows, "the staging schema has sequences to check"

            for table, column, sequence in rows:
                highest = connection.execute(
                    text(f'SELECT max("{column}") FROM "{STAGING}"."{table}"')
                ).scalar()
                if highest is None:
                    continue
                nxt = connection.execute(text(f"SELECT nextval('{sequence}')")).scalar()
                assert nxt > highest, f"{table}.{column} would reissue an existing id"

            transaction.rollback()

    def test_purging_one_provider_leaves_the_other_intact(self) -> None:
        """The cycle in one test: seed, purge the refreshing source, and find
        every other provider still there."""
        from pipelines.load.prepare_staging import prepare

        with get_engine().connect() as connection, connection.begin() as transaction:
            prepare(connection)

            others = {
                table: int(
                    connection.execute(
                        text(
                            f'SELECT count(*) FROM "{STAGING}"."{table}" '
                            f"WHERE source <> 'footystats'"
                        )
                    ).scalar()
                    or 0
                )
                for table in ("fact_market_value", "fact_transfer")
            }

            for table in ("fact_player_season_stats", "fact_market_value", "fact_transfer"):
                connection.execute(
                    text(f'DELETE FROM "{STAGING}"."{table}" WHERE source = :s'),
                    {"s": "footystats"},
                )

            after = {
                table: int(
                    connection.execute(text(f'SELECT count(*) FROM "{STAGING}"."{table}"')).scalar()
                    or 0
                )
                for table in ("fact_market_value", "fact_transfer")
            }
            assert after == others, (
                "purging the refreshing provider took the other one's rows with it"
            )

            transaction.rollback()

    def test_the_seed_is_not_the_leftover_from_the_last_promotion(self) -> None:
        """Why staging is rebuilt rather than inherited.

        The swap leaves the previous production in staging, which is correct
        exactly once. Refresh FootyStats to F2 and publish, then refresh
        Transfermarkt from that staging, and production becomes F1 + T2 - the
        one combination that must never exist. Seeding from *current*
        production is what makes the second refresh start from the first one's
        result.
        """
        import inspect

        from pipelines.load import prepare_staging

        source = inspect.getsource(prepare_staging.prepare)
        assert "TRUNCATE" in source, "staging is emptied before the copy, not appended to"
        assert 'FROM "{SERVING}"' in source or "SERVING" in source


class TestAFailedPublicationIsRetriedRatherThanRefetched:
    """Thirteen hours of API budget, discarded because a step had a bad minute.

    A generation whose fetch finished but whose publication failed used to be
    indistinguishable from no generation at all, so the next cadence run
    started a fresh one and refetched every player.
    """

    def test_a_generation_whose_promotion_failed_stays_publishable(self) -> None:
        """Which is what makes the retry possible: the status only moves inside
        the promotion transaction, so a promotion that did not commit leaves
        the generation exactly where it was."""
        from pipelines.footystats.gate import Action, decide_from_state
        from pipelines.load.resolve_source import CONTINUE_ONLY, START

        for mode in (START, CONTINUE_ONLY):
            decision = decide_from_state(mode, [("20260907T040000Z", "COMPLETE")])
            assert decision.action is Action.PUBLISH_READY, mode
            assert not decision.action.fetches, "the fetch is already done"

    def test_a_validated_generation_is_retried_too(self) -> None:
        """It passed every check and the swap is all that is left."""
        from pipelines.footystats.gate import Action, decide_from_state
        from pipelines.load.resolve_source import START

        decision = decide_from_state(START, [("20260907T040000Z", "VALIDATED")])
        assert decision.action is Action.PUBLISH_READY

    def test_a_published_generation_is_not_retried(self) -> None:
        """It is finished. Picking it up again would republish yesterday."""
        from pipelines.footystats.gate import Action, decide_from_state
        from pipelines.load.resolve_source import CONTINUE_ONLY, START

        assert decide_from_state(START, []).action is Action.START_NEW
        assert decide_from_state(CONTINUE_ONLY, []).action is Action.NOOP

    def test_two_live_generations_stop_rather_than_guess(self) -> None:
        """Continuing the wrong one interleaves two universes, which is the
        failure generations exist to prevent."""
        from pipelines.footystats.gate import Action, decide_from_state
        from pipelines.load.resolve_source import START

        decision = decide_from_state(
            START, [("20260901T040000Z", "IN_PROGRESS"), ("20260907T040000Z", "COMPLETE")]
        )
        # ERROR, not NOOP. A NOOP is a quiet hour and exits 0; two live
        # generations is a broken production state that must turn the
        # workflow red rather than pass every hour in silence.
        assert decision.action is Action.ERROR
        assert not decision.proceed
        assert "manual intervention" in decision.reason


class TestTheValidatedStateIsUsed:
    """Section 7 and 18. COMPLETE -> VALIDATED after every check; a promotion
    that fails leaves VALIDATED behind, and the next run retries from there."""

    GENERATION = "29990102T000000Z"
    SOURCE = "a_validated_provider"

    @pytest.fixture
    def a_complete_generation(self):  # type: ignore[no-untyped-def]
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.fact_refresh_generation "
                    "(generation_id, source, status, created_at, updated_at, complete, "
                    " total_expected_players, completed_players, failed_players, "
                    " competitions_expected, competitions_complete) "
                    "VALUES (:g, :s, 'COMPLETE', now(), now(), true, 0, 0, 0, 0, 0)"
                ),
                {"g": self.GENERATION, "s": self.SOURCE},
            )
        yield self.GENERATION
        with get_engine().begin() as connection:
            connection.execute(
                text("DELETE FROM public.fact_source_publication WHERE source = :s"),
                {"s": self.SOURCE},
            )
            connection.execute(
                text("DELETE FROM public.fact_refresh_generation WHERE source = :s"),
                {"s": self.SOURCE},
            )

    def _status(self) -> str | None:
        with get_engine().connect() as connection:
            return connection.execute(
                text("SELECT status FROM public.fact_refresh_generation WHERE source = :s"),
                {"s": self.SOURCE},
            ).scalar()

    def test_complete_becomes_validated(self, a_complete_generation: str) -> None:
        from pipelines.footystats.publish_status import mark_validated

        assert mark_validated(a_complete_generation, source=self.SOURCE) is True
        assert self._status() == "VALIDATED"

    def test_marking_validated_twice_is_harmless(self, a_complete_generation: str) -> None:
        """A retried run reaches the step again."""
        from pipelines.footystats.publish_status import mark_validated

        mark_validated(a_complete_generation, source=self.SOURCE)
        assert mark_validated(a_complete_generation, source=self.SOURCE) is False
        assert self._status() == "VALIDATED"

    def test_a_published_generation_is_not_dragged_back(self, a_complete_generation: str) -> None:
        from pipelines.footystats.publish_status import mark_validated
        from pipelines.load.promote import record_publication

        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=a_complete_generation,
                rows_published=1,
            )
        assert self._status() == "PUBLISHED"
        assert mark_validated(a_complete_generation, source=self.SOURCE) is False
        assert self._status() == "PUBLISHED"

    def test_a_failed_promotion_leaves_validated_and_the_gate_retries(
        self, a_complete_generation: str
    ) -> None:
        """The retry, end to end at the database level.

        Validated; the promotion transaction rolls back; the status is still
        VALIDATED; the gate answers PUBLISH_READY without fetching; the retry
        succeeds and the generation is PUBLISHED.
        """
        from pipelines.footystats.gate import Action, decide_from_state
        from pipelines.footystats.publish_status import mark_validated
        from pipelines.load.promote import record_publication, swap

        mark_validated(a_complete_generation, source=self.SOURCE)

        # The promotion fails transiently: everything it did is undone.
        with get_engine().connect() as connection, connection.begin():
            swap(connection)
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=a_complete_generation,
                rows_published=1,
            )
            connection.rollback()
        assert self._status() == "VALIDATED", "validation state survived the failed promotion"

        decision = decide_from_state("continue_only", [(a_complete_generation, "VALIDATED")])
        assert decision.action is Action.PUBLISH_READY
        assert not decision.action.fetches, "no refetch"

        # The retry.
        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=a_complete_generation,
                rows_published=1,
            )
        assert self._status() == "PUBLISHED"

    def test_the_promotion_refuses_a_generation_the_database_does_not_expect(
        self, a_complete_generation: str
    ) -> None:
        """Section 4: the named generation is verified against the database
        inside the promotion, not trusted from the command line."""
        from pipelines.load.promote import generation_status

        with get_engine().connect() as connection:
            assert generation_status(connection, self.SOURCE, a_complete_generation) == "COMPLETE"
            assert generation_status(connection, self.SOURCE, "29990909T000000Z") is None


class TestQualityChecksCarryTheirContext:
    """Section 9, 10 and 19. Production is G4; G5 was checked and failed to
    publish. The public page must say G4's checks are G4's and G5's are a
    candidate's, and never the other way round."""

    SOURCE = "a_contextual_provider"
    G4 = "29990104T000000Z"
    G5 = "29990105T000000Z"

    @pytest.fixture
    def two_generations(self):  # type: ignore[no-untyped-def]
        with get_engine().begin() as connection:
            for gid, status in ((self.G4, "PUBLISHED"), (self.G5, "COMPLETE")):
                connection.execute(
                    text(
                        "INSERT INTO public.fact_refresh_generation "
                        "(generation_id, source, status, created_at, updated_at, complete, "
                        " total_expected_players, completed_players, failed_players, "
                        " competitions_expected, competitions_complete) "
                        "VALUES (:g, :s, :st, now(), now(), true, 0, 0, 0, 0, 0)"
                    ),
                    {"g": gid, "s": self.SOURCE, "st": status},
                )
            connection.execute(
                text(
                    "INSERT INTO public.fact_source_publication "
                    "(source, refresh_id, generation_id, published_at, rows_published) "
                    "VALUES (:s, :g, :g, now() - interval '2 days', 10)"
                ),
                {"s": self.SOURCE, "g": self.G4},
            )
            for gid, context, when, status in (
                (self.G4, "PUBLISHED", "now() - interval '2 days'", "pass"),
                (self.G5, "CANDIDATE", "now()", "warn"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO public.fact_data_quality "
                        "(source, entity, check_name, status, record_count, detail, executed_at, "
                        " refresh_id, generation_id, context) "
                        f"VALUES (:s, 'player', 'a_check', :st, 1, NULL, {when}, :g, :g, :c)"
                    ),
                    {"s": self.SOURCE, "st": status, "g": gid, "c": context},
                )
        yield
        with get_engine().begin() as connection:
            for table in (
                "fact_data_quality",
                "fact_source_publication",
                "fact_refresh_generation",
            ):
                connection.execute(
                    text(f"DELETE FROM public.{table} WHERE source = :s"),
                    {"s": self.SOURCE},
                )

    def test_the_published_checks_are_the_published_generations(self, two_generations) -> None:  # type: ignore[no-untyped-def]
        from sqlalchemy.orm import Session

        from app.services.quality_service import latest_checks, published_generation_id

        with Session(get_engine()) as session:
            mine = [c for c in latest_checks(session) if c.source == self.SOURCE]
            assert [c.generation_id for c in mine] == [self.G4]
            assert mine[0].context == "PUBLISHED"
            assert mine[0].status == "pass", "G5's warning is not shown as production's"
            assert published_generation_id(session, source=self.SOURCE) == self.G4

    def test_the_candidate_checks_are_reported_separately(self, two_generations) -> None:  # type: ignore[no-untyped-def]
        from sqlalchemy.orm import Session

        from app.services.quality_service import candidate_checks

        with Session(get_engine()) as session:
            mine = [c for c in candidate_checks(session) if c.source == self.SOURCE]
            assert len(mine) == 1
            assert mine[0].generation_id == self.G5
            assert [c.status for c in mine[0].checks] == ["warn"]

    def test_freshness_reports_the_published_check_time(self, two_generations) -> None:  # type: ignore[no-untyped-def]
        """ "Checked today" about a candidate would say the served data was
        checked today. It was checked two days ago."""
        from sqlalchemy.orm import Session

        from app.services.quality_service import freshness

        with Session(get_engine()) as session:
            entry = next(f for f in freshness(session) if f.source == self.SOURCE)
            assert entry.age_days == 2
            assert entry.warnings == 0

    def test_promotion_flips_the_candidate_rows_to_published(self, two_generations) -> None:  # type: ignore[no-untyped-def]
        from pipelines.load.promote import record_publication
        from sqlalchemy.orm import Session

        from app.services.quality_service import candidate_checks, latest_checks

        with get_engine().begin() as connection:
            record_publication(
                connection, source=self.SOURCE, generation_id=self.G5, rows_published=12
            )

        with Session(get_engine()) as session:
            mine = [c for c in latest_checks(session) if c.source == self.SOURCE]
            assert [c.generation_id for c in mine] == [self.G5]
            assert not [c for c in candidate_checks(session) if c.source == self.SOURCE]

    def test_rollback_makes_them_a_candidate_again(self, two_generations) -> None:  # type: ignore[no-untyped-def]
        from pipelines.load.promote import record_publication, retract_publication
        from sqlalchemy.orm import Session

        from app.services.quality_service import candidate_checks, latest_checks

        with get_engine().begin() as connection:
            record_publication(
                connection, source=self.SOURCE, generation_id=self.G5, rows_published=12
            )
        with get_engine().begin() as connection:
            assert retract_publication(connection) == (self.SOURCE, self.G5)

        with Session(get_engine()) as session:
            mine = [c for c in latest_checks(session) if c.source == self.SOURCE]
            assert [c.generation_id for c in mine] == [self.G4], "G4 is serving again"
            candidates = [c for c in candidate_checks(session) if c.source == self.SOURCE]
            assert [c.generation_id for c in candidates] == [self.G5]

    def test_rows_without_context_still_describe_the_served_data(self, two_generations) -> None:  # type: ignore[no-untyped-def]
        """Rows written before contexts existed. They were always about
        whatever was serving, and a page that dropped them would go blank for
        every source that has not been refreshed since."""
        from sqlalchemy.orm import Session

        from app.services.quality_service import latest_checks

        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.fact_data_quality "
                    "(source, entity, check_name, status, record_count, executed_at) "
                    "VALUES (:s, 'club', 'legacy_check', 'pass', 1, now() + interval '1 hour')"
                ),
                {"s": self.SOURCE},
            )
        with Session(get_engine()) as session:
            mine = [c for c in latest_checks(session) if c.source == self.SOURCE]
            assert [c.check_name for c in mine] == ["legacy_check"]
            assert mine[0].context is None


class TestPublishedRowsMeanWhatTheySay:
    """Section 11. `rows_published` is a volume; `player_seasons_published`
    is a player count. One column carried both and was read as the second."""

    def test_the_two_figures_are_recorded_separately(self) -> None:
        from pipelines.load.promote import player_seasons_for_source, rows_for_source

        with get_engine().connect() as connection:
            rows = rows_for_source(connection, SERVING, "footystats")
            seasons = player_seasons_for_source(connection, SERVING, "footystats")
        assert seasons <= rows
        if seasons:
            assert rows > seasons, "bridges and competitions are rows too; the volume is larger"

    def test_the_publication_row_carries_both(self) -> None:
        from pipelines.load.promote import record_publication

        source = "a_counted_provider"
        try:
            with get_engine().begin() as connection:
                record_publication(
                    connection,
                    source=source,
                    generation_id=None,
                    rows_published=1_000,
                    player_seasons_published=250,
                )
            with get_engine().connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT rows_published, player_seasons_published "
                        "FROM public.fact_source_publication WHERE source = :s"
                    ),
                    {"s": source},
                ).one()
            assert row == (1_000, 250)
        finally:
            with get_engine().begin() as connection:
                connection.execute(
                    text("DELETE FROM public.fact_source_publication WHERE source = :s"),
                    {"s": source},
                )


class TestProviderPurgeLeavesQualityHistoryAlone:
    """Section 4 and 18. Quality rows are validation history in `public`, not
    provider data in the candidate schema. The purge used to delete them."""

    SOURCE = "a_purged_provider"
    G4 = "29990204T000000Z"
    G5 = "29990205T000000Z"

    @pytest.fixture
    def published_history(self):  # type: ignore[no-untyped-def]
        with get_engine().begin() as connection:
            # G4 published, G5 still live: a candidate is only a candidate
            # while its generation is, so the generation rows exist here.
            for gid, status in ((self.G4, "PUBLISHED"), (self.G5, "COMPLETE")):
                connection.execute(
                    text(
                        "INSERT INTO public.fact_refresh_generation "
                        "(generation_id, source, status, created_at, updated_at, complete, "
                        " total_expected_players, completed_players, failed_players, "
                        " competitions_expected, competitions_complete) "
                        "VALUES (:g, :s, :st, now(), now(), true, 0, 0, 0, 0, 0)"
                    ),
                    {"g": gid, "s": self.SOURCE, "st": status},
                )
            connection.execute(
                text(
                    "INSERT INTO public.fact_data_quality "
                    "(source, entity, check_name, status, record_count, executed_at, "
                    " refresh_id, generation_id, context) "
                    "VALUES (:s, 'player', 'a_check', 'pass', 1, now() - interval '3 days', "
                    " :g, :g, 'PUBLISHED')"
                ),
                {"s": self.SOURCE, "g": self.G4},
            )
        yield
        with get_engine().begin() as connection:
            for table in ("fact_data_quality", "fact_refresh_generation"):
                connection.execute(
                    text(f"DELETE FROM public.{table} WHERE source = :s"),
                    {"s": self.SOURCE},
                )

    def _rows(self) -> list[tuple[str | None, str | None]]:
        with get_engine().connect() as connection:
            return [
                (r[0], r[1])
                for r in connection.execute(
                    text(
                        "SELECT refresh_id, context FROM public.fact_data_quality "
                        "WHERE source = :s ORDER BY executed_at"
                    ),
                    {"s": self.SOURCE},
                ).all()
            ]

    def test_purging_the_provider_keeps_its_published_checks(
        self,
        db_session: Session,
        published_history,  # type: ignore[no-untyped-def]
    ) -> None:
        from pipelines.load.load_providers import purge

        purge(db_session, self.SOURCE)
        db_session.flush()
        # Read through the same session: the purge is uncommitted and rolled
        # back by the fixture, which is exactly the isolation wanted here.
        rows = db_session.execute(
            text("SELECT refresh_id, context FROM fact_data_quality WHERE source = :s"),
            {"s": self.SOURCE},
        ).all()
        assert [(r[0], r[1]) for r in rows] == [(self.G4, "PUBLISHED")]

    def test_the_purge_no_longer_names_the_table_at_all(self) -> None:
        """Asserted on the code as well as the effect, so the line cannot
        quietly come back."""
        import inspect

        from pipelines.load import load_providers

        source = inspect.getsource(load_providers.purge)
        code = [line for line in source.splitlines() if not line.strip().startswith("#")]
        assert not any("delete(FactDataQuality)" in line for line in code)

    def test_a_failed_candidate_leaves_both_histories_intact(
        self,
        published_history,  # type: ignore[no-untyped-def]
    ) -> None:
        """G4 published, G5 checked and stuck. Both rows survive; production
        is still G4; G4's checks are still G4's."""
        from sqlalchemy.orm import Session as OrmSession

        from app.services.quality_service import candidate_checks, latest_checks

        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.fact_data_quality "
                    "(source, entity, check_name, status, record_count, executed_at, "
                    " refresh_id, generation_id, context) "
                    "VALUES (:s, 'player', 'a_check', 'warn', 1, now(), :g, :g, 'CANDIDATE')"
                ),
                {"s": self.SOURCE, "g": self.G5},
            )
        assert self._rows() == [(self.G4, "PUBLISHED"), (self.G5, "CANDIDATE")]

        with OrmSession(get_engine()) as session:
            published = [c for c in latest_checks(session) if c.source == self.SOURCE]
            assert [c.refresh_id for c in published] == [self.G4]
            candidates = [c for c in candidate_checks(session) if c.source == self.SOURCE]
            assert [c.refresh_id for c in candidates] == [self.G5]


class TestTransfermarktCandidatesArePromotedByRefresh:
    """Sections 7 to 10 and 20. No generation, and a candidate all the same.

    T1 is serving with refresh R1. T2 is loaded into staging as refresh R2
    and checked; the promotion fails; production and its published checks
    are still R1's, and R2 is a candidate. The retry succeeds and R2's rows
    become PUBLISHED - by source + refresh_id, never by generation, which
    does not exist here, and never by source alone, which would have flipped
    R1's old candidates too.
    """

    SOURCE = "a_market_provider"
    R1 = "a_market_provider-1001"
    R2 = "a_market_provider-1002"

    @pytest.fixture
    def r1_published(self):  # type: ignore[no-untyped-def]
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.fact_source_publication "
                    "(source, refresh_id, generation_id, published_at, rows_published) "
                    "VALUES (:s, :r, NULL, now() - interval '7 days', 100)"
                ),
                {"s": self.SOURCE, "r": self.R1},
            )
            connection.execute(
                text(
                    "INSERT INTO public.fact_data_quality "
                    "(source, entity, check_name, status, record_count, executed_at, "
                    " refresh_id, generation_id, context) "
                    "VALUES (:s, 'market_value', 'a_check', 'pass', 1, "
                    " now() - interval '7 days', :r, NULL, 'PUBLISHED')"
                ),
                {"s": self.SOURCE, "r": self.R1},
            )
        yield
        with get_engine().begin() as connection:
            for table in ("fact_data_quality", "fact_source_publication"):
                connection.execute(
                    text(f"DELETE FROM public.{table} WHERE source = :s"),
                    {"s": self.SOURCE},
                )

    def _stage_r2(self) -> None:
        """What the loader and the report write for a staging refresh."""
        from pipelines.quality.report import Check, persist
        from sqlalchemy.orm import Session as OrmSession

        with OrmSession(get_engine()) as session:
            persist(
                session,
                [Check("market_value", "a_check", "warn", 3, "a candidate warning")],
                source=self.SOURCE,
                refresh_id=self.R2,
                generation_id=None,
                candidate=True,
            )

    def test_a_staging_check_without_a_generation_is_still_a_candidate(
        self,
        r1_published,  # type: ignore[no-untyped-def]
    ) -> None:
        """The failure this whole section fixes: context was inferred from
        generation_id, and Transfermarkt has none."""
        from sqlalchemy.orm import Session as OrmSession

        from app.services.quality_service import candidate_checks, latest_checks

        self._stage_r2()

        with OrmSession(get_engine()) as session:
            published = [c for c in latest_checks(session) if c.source == self.SOURCE]
            assert [c.refresh_id for c in published] == [self.R1], "T1 is still serving"
            assert published[0].status == "pass"
            candidates = [c for c in candidate_checks(session) if c.source == self.SOURCE]
            assert [c.refresh_id for c in candidates] == [self.R2]
            assert candidates[0].generation_id is None

    def test_a_failed_promotion_changes_nothing(self, r1_published) -> None:  # type: ignore[no-untyped-def]
        from pipelines.load.promote import record_publication, swap
        from sqlalchemy.orm import Session as OrmSession

        from app.services.quality_service import provider_quality

        self._stage_r2()
        with get_engine().connect() as connection, connection.begin():
            swap(connection)
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=None,
                refresh_id=self.R2,
                rows_published=120,
            )
            connection.rollback()

        with OrmSession(get_engine()) as session:
            mine = next(p for p in provider_quality(session) if p.source == self.SOURCE)
        assert mine.published is not None and mine.published.refresh_id == self.R1
        assert mine.candidate is not None and mine.candidate.refresh_id == self.R2

    def test_the_retry_publishes_exactly_r2(self, r1_published) -> None:  # type: ignore[no-untyped-def]
        from pipelines.load.promote import record_publication
        from sqlalchemy.orm import Session as OrmSession

        from app.services.quality_service import provider_quality

        self._stage_r2()
        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=None,
                refresh_id=self.R2,
                rows_published=120,
            )

        with OrmSession(get_engine()) as session:
            mine = next(p for p in provider_quality(session) if p.source == self.SOURCE)
        assert mine.published is not None
        assert mine.published.refresh_id == self.R2
        assert [c.status for c in mine.published.checks] == ["warn"], "R2's own checks"
        assert mine.candidate is None, "nothing is waiting any more"

    def test_an_older_candidate_of_the_same_source_is_not_promoted_with_it(
        self,
        r1_published,  # type: ignore[no-untyped-def]
    ) -> None:
        """Flipping by source alone would have done this."""
        from pipelines.load.promote import record_publication
        from pipelines.quality.report import Check, persist
        from sqlalchemy.orm import Session as OrmSession

        stale = "a_market_provider-0999"
        with OrmSession(get_engine()) as session:
            persist(
                session,
                [Check("market_value", "a_check", "fail", 9, "an abandoned candidate")],
                source=self.SOURCE,
                refresh_id=stale,
                candidate=True,
            )
        self._stage_r2()
        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=None,
                refresh_id=self.R2,
                rows_published=120,
            )

        with get_engine().connect() as connection:
            contexts = dict(
                connection.execute(
                    text(
                        "SELECT refresh_id, context FROM public.fact_data_quality WHERE source = :s"
                    ),
                    {"s": self.SOURCE},
                ).all()
            )
        assert contexts[self.R2] == "PUBLISHED"
        assert contexts[stale] == "CANDIDATE", "the abandoned candidate was left where it was"


class TestFootyStatsCandidatesArePromotedByRefresh:
    """Section 19. For FootyStats refresh_id == generation_id, and the
    promotion flips by refresh_id exactly as it does for Transfermarkt."""

    SOURCE = "a_generation_provider"
    G5 = "29990305T000000Z"

    @pytest.fixture
    def g5_complete(self):  # type: ignore[no-untyped-def]
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.fact_refresh_generation "
                    "(generation_id, source, status, created_at, updated_at, complete, "
                    " total_expected_players, completed_players, failed_players, "
                    " competitions_expected, competitions_complete) "
                    "VALUES (:g, :s, 'VALIDATED', now(), now(), true, 0, 0, 0, 0, 0)"
                ),
                {"g": self.G5, "s": self.SOURCE},
            )
        yield
        with get_engine().begin() as connection:
            for table in (
                "fact_data_quality",
                "fact_source_publication",
                "fact_refresh_generation",
            ):
                connection.execute(
                    text(f"DELETE FROM public.{table} WHERE source = :s"),
                    {"s": self.SOURCE},
                )

    def test_candidate_rows_become_published_with_the_generation(
        self,
        g5_complete,  # type: ignore[no-untyped-def]
    ) -> None:
        from pipelines.load.promote import record_publication
        from pipelines.quality.report import Check, persist
        from sqlalchemy.orm import Session as OrmSession

        from app.services.quality_service import provider_quality

        with OrmSession(get_engine()) as session:
            persist(
                session,
                [Check("player", "a_check", "pass", 5, None)],
                source=self.SOURCE,
                refresh_id=self.G5,
                generation_id=self.G5,
                candidate=True,
            )
        with get_engine().connect() as connection:
            row = connection.execute(
                text(
                    "SELECT refresh_id, generation_id, context FROM public.fact_data_quality "
                    "WHERE source = :s"
                ),
                {"s": self.SOURCE},
            ).one()
        assert row == (self.G5, self.G5, "CANDIDATE")

        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=self.G5,
                refresh_id=self.G5,
                rows_published=50,
                player_seasons_published=10,
            )

        with OrmSession(get_engine()) as session:
            mine = next(p for p in provider_quality(session) if p.source == self.SOURCE)
        assert mine.published is not None
        assert (mine.published.refresh_id, mine.published.generation_id) == (self.G5, self.G5)
        assert mine.candidate is None, "G5 is no longer reported as unpublished"
        with get_engine().connect() as connection:
            status = connection.execute(
                text("SELECT status FROM public.fact_refresh_generation WHERE source = :s"),
                {"s": self.SOURCE},
            ).scalar()
        assert status == "PUBLISHED"


class TestAnObsoleteCandidateDoesNotReappear:
    """Sections 9 to 11, 19 and 20. History stays; the page shows only what
    is genuinely waiting."""

    SOURCE = "a_lifecycle_provider"

    @pytest.fixture
    def clean(self):  # type: ignore[no-untyped-def]
        yield
        with get_engine().begin() as connection:
            for table in (
                "fact_data_quality",
                "fact_source_publication",
                "fact_refresh_generation",
            ):
                connection.execute(
                    text(f"DELETE FROM public.{table} WHERE source = :s"),
                    {"s": self.SOURCE},
                )

    def _candidate(self, refresh: str, when: str, generation_id: str | None = None) -> None:
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.fact_data_quality "
                    "(source, entity, check_name, status, record_count, executed_at, "
                    " refresh_id, generation_id, context) "
                    f"VALUES (:s, 'player', 'a_check', 'pass', 1, {when}, :r, :g, 'CANDIDATE')"
                ),
                {"s": self.SOURCE, "r": refresh, "g": generation_id},
            )

    def _publish(self, refresh: str, generation_id: str | None = None) -> None:
        from pipelines.load.promote import record_publication

        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=generation_id,
                refresh_id=refresh,
                rows_published=1,
            )

    def _quality(self):  # type: ignore[no-untyped-def]
        from sqlalchemy.orm import Session as OrmSession

        from app.services.quality_service import provider_quality

        with OrmSession(get_engine()) as session:
            return next(p for p in provider_quality(session) if p.source == self.SOURCE)

    def test_transfermarkt_r2_does_not_resurface_after_r3_publishes(self, clean) -> None:  # type: ignore[no-untyped-def]
        """Section 19."""
        self._candidate("R1", "now() - interval '3 days'")
        self._publish("R1")
        self._candidate("R2", "now() - interval '2 hours'")  # stuck at promotion
        self._candidate("R3", "now() - interval '1 hour'")
        self._publish("R3")

        mine = self._quality()
        assert mine.published is not None and mine.published.refresh_id == "R3"
        assert mine.candidate is None, "R2 is history, not the latest candidate"

        with get_engine().connect() as connection:
            contexts = dict(
                connection.execute(
                    text(
                        "SELECT refresh_id, context FROM public.fact_data_quality WHERE source = :s"
                    ),
                    {"s": self.SOURCE},
                ).all()
            )
        assert contexts["R2"] == "CANDIDATE", "kept, for audit"
        assert contexts["R3"] == "PUBLISHED"

        # A genuinely new candidate after R3 is shown.
        self._candidate("R4", "now() + interval '1 minute'")
        mine = self._quality()
        assert mine.published is not None and mine.published.refresh_id == "R3"
        assert mine.candidate is not None and mine.candidate.refresh_id == "R4"

    def test_an_abandoned_footystats_generation_is_not_a_candidate(self, clean) -> None:  # type: ignore[no-untyped-def]
        """Section 20."""
        g5, g6 = "29990405T000000Z", "29990406T000000Z"
        with get_engine().begin() as connection:
            for gid, status in ((g5, "FAILED"), (g6, "PUBLISHED")):
                connection.execute(
                    text(
                        "INSERT INTO public.fact_refresh_generation "
                        "(generation_id, source, status, created_at, updated_at, complete, "
                        " total_expected_players, completed_players, failed_players, "
                        " competitions_expected, competitions_complete) "
                        "VALUES (:g, :s, :st, now(), now(), true, 0, 0, 0, 0, 0)"
                    ),
                    {"g": gid, "s": self.SOURCE, "st": status},
                )
        self._candidate(g5, "now() - interval '2 hours'", g5)
        self._candidate(g6, "now() - interval '1 hour'", g6)
        self._publish(g6, g6)

        mine = self._quality()
        assert mine.published is not None and mine.published.generation_id == g6
        assert mine.candidate is None, "G5 is FAILED; its rows are history"

    def test_a_failed_generation_is_not_a_candidate_even_before_anything_publishes(
        self,
        clean,  # type: ignore[no-untyped-def]
    ) -> None:
        g5 = "29990505T000000Z"
        with get_engine().begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.fact_refresh_generation "
                    "(generation_id, source, status, created_at, updated_at, complete, "
                    " total_expected_players, completed_players, failed_players, "
                    " competitions_expected, competitions_complete) "
                    "VALUES (:g, :s, 'FAILED', now(), now(), false, 0, 0, 0, 0, 0)"
                ),
                {"g": g5, "s": self.SOURCE},
            )
        self._candidate(g5, "now()", g5)
        from sqlalchemy.orm import Session as OrmSession

        from app.services.quality_service import candidate_checks

        with OrmSession(get_engine()) as session:
            assert not [c for c in candidate_checks(session) if c.source == self.SOURCE]


class TestPublicationIsIdempotent:
    """Sections 12 to 14 and 21. The same source + refresh_id twice: one
    swap, one row, one publication time."""

    SOURCE = "an_idempotent_provider"

    @pytest.fixture
    def clean(self):  # type: ignore[no-untyped-def]
        yield
        with get_engine().begin() as connection:
            for table in ("fact_data_quality", "fact_source_publication"):
                connection.execute(
                    text(f"DELETE FROM public.{table} WHERE source = :s"),
                    {"s": self.SOURCE},
                )

    def test_a_second_promotion_of_the_same_refresh_is_a_no_op(
        self,
        clean,
        capsys: pytest.CaptureFixture,  # type: ignore[no-untyped-def]
    ) -> None:
        from pipelines.load.promote import already_published, record_publication

        with get_engine().begin() as connection:
            assert already_published(connection, self.SOURCE, "R2") is False
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=None,
                refresh_id="R2",
                rows_published=5,
            )
        with get_engine().connect() as connection:
            assert already_published(connection, self.SOURCE, "R2") is True
            first = connection.execute(
                text(
                    "SELECT published_at FROM public.fact_source_publication "
                    "WHERE source = :s AND refresh_id = 'R2'"
                ),
                {"s": self.SOURCE},
            ).scalar()

        # The check the CLI makes before swapping, and the constraint behind
        # it: a second row for the same refresh is refused by the database.
        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.IntegrityError), get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=None,
                refresh_id="R2",
                rows_published=5,
            )

        with get_engine().connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT count(*), max(published_at) FROM public.fact_source_publication "
                    "WHERE source = :s AND refresh_id = 'R2'"
                ),
                {"s": self.SOURCE},
            ).one()
        assert rows == (1, first), "one row, the original time"

    def test_the_cli_stops_before_the_swap(
        self,
        clean,
        capsys: pytest.CaptureFixture,  # type: ignore[no-untyped-def]
    ) -> None:
        """Driven through `main`, which is what the workflow runs.

        The refresh is recorded as published under a real source first, so
        the CLI finds it and stops: exit 0 - the thing the run exists to do
        has been done - and the row counts either side of the swap are
        unchanged. The row is removed again afterwards.
        """
        from pipelines.load.promote import SERVING, STAGING, _counts, main, record_publication

        refresh = "test-idempotent-R7"
        try:
            with get_engine().begin() as connection:
                record_publication(
                    connection,
                    source="transfermarkt",
                    generation_id=None,
                    refresh_id=refresh,
                    rows_published=1,
                )
            with get_engine().connect() as connection:
                before = (_counts(connection, SERVING), _counts(connection, STAGING))

            code = main(["--apply", "--source", "transfermarkt", "--refresh-id", refresh])

            assert code == 0
            assert "already published" in capsys.readouterr().out
            with get_engine().connect() as connection:
                after = (_counts(connection, SERVING), _counts(connection, STAGING))
                count = connection.execute(
                    text(
                        "SELECT count(*) FROM public.fact_source_publication "
                        "WHERE source = 'transfermarkt' AND refresh_id = :r"
                    ),
                    {"r": refresh},
                ).scalar()
            assert after == before, "no swap"
            assert count == 1, "no second row"
        finally:
            with get_engine().begin() as connection:
                connection.execute(
                    text(
                        "DELETE FROM public.fact_source_publication "
                        "WHERE source = 'transfermarkt' AND refresh_id = :r"
                    ),
                    {"r": refresh},
                )

    def test_rollback_releases_the_identity(self, clean) -> None:  # type: ignore[no-untyped-def]
        """Section 14. Published, rolled back, published again on purpose."""
        from pipelines.load.promote import (
            already_published,
            record_publication,
            retract_publication,
        )

        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=None,
                refresh_id="R9",
                rows_published=2,
            )
        with get_engine().begin() as connection:
            assert retract_publication(connection) == (self.SOURCE, None)
        with get_engine().connect() as connection:
            assert already_published(connection, self.SOURCE, "R9") is False, "rolled back"
        with get_engine().begin() as connection:
            record_publication(
                connection,
                source=self.SOURCE,
                generation_id=None,
                refresh_id="R9",
                rows_published=2,
            )
        with get_engine().connect() as connection:
            assert already_published(connection, self.SOURCE, "R9") is True
            count = connection.execute(
                text(
                    "SELECT count(*) FROM public.fact_source_publication "
                    "WHERE source = :s AND refresh_id = 'R9'"
                ),
                {"s": self.SOURCE},
            ).scalar()
        assert count == 1


class TestTheRefusalsHappenInTheRightOrder:
    """CI found this and a developer's machine could not.

    The row-count refusal used to run before both the `--source` guard and
    the idempotency check. Locally staging holds a copy of production, so
    `check` passed and the two later answers were reached; on a fresh CI
    database staging is empty, `check` refused first, and it answered for
    them both:

      - a promotion missing `--source` reported "staging holds no
        player-seasons" - true, and not what is wrong with the command;
      - a re-run of an already-published refresh returned 1 instead of the
        safe no-op it is. That is the case idempotency exists for, failing
        loudest exactly when staging is thin - which is when somebody is
        most likely to be re-running a job by hand.

    Staging is emptied here by stubbing the counts rather than by truncating
    a real schema: the point is the order of the checks, and a test that
    rebuilt staging to prove it would be a test that changed what the next
    promotion promotes.
    """

    @pytest.fixture
    def empty_staging(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pipelines.load import promote

        real = promote._counts

        def counts(connection, schema: str):  # type: ignore[no-untyped-def]
            if schema == promote.STAGING:
                return promote.SchemaCounts(players=0, player_seasons=0, competitions=0)
            return real(connection, schema)

        monkeypatch.setattr(promote, "_counts", counts)

    def test_a_missing_source_is_reported_as_a_missing_source(
        self, empty_staging: None, capsys: pytest.CaptureFixture
    ) -> None:
        from pipelines.load.promote import main

        assert main(["--apply"]) == 2
        assert "--source is required" in capsys.readouterr().err

    def test_an_already_published_refresh_is_still_a_no_op(
        self, empty_staging: None, capsys: pytest.CaptureFixture
    ) -> None:
        from pipelines.load.promote import main, record_publication

        refresh = "test-order-R1"
        try:
            with get_engine().begin() as connection:
                record_publication(
                    connection,
                    source="transfermarkt",
                    generation_id=None,
                    refresh_id=refresh,
                    rows_published=1,
                )

            assert main(["--apply", "--source", "transfermarkt", "--refresh-id", refresh]) == 0
            assert "already published" in capsys.readouterr().out
        finally:
            with get_engine().begin() as connection:
                connection.execute(
                    text(
                        "DELETE FROM public.fact_source_publication "
                        "WHERE source = 'transfermarkt' AND refresh_id = :r"
                    ),
                    {"r": refresh},
                )

    def test_an_unpublished_refresh_still_hits_the_row_count_refusal(
        self, empty_staging: None, capsys: pytest.CaptureFixture
    ) -> None:
        """The refusal did not go away; it moved behind the two answers that
        were being swallowed."""
        from pipelines.load.promote import main

        assert main(["--apply", "--source", "transfermarkt", "--refresh-id", "test-order-R2"]) == 1
        assert "nothing to promote" in capsys.readouterr().err
