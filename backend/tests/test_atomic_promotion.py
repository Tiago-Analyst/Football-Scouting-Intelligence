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

# ruff: noqa: S608 - every interpolated name here is a module constant
# naming a schema, never a value from outside this file.
import pytest
from sqlalchemy import text

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

    def test_promotion_of_the_same_empty_staging_is_refused(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """The contrast that makes the test above meaningful."""
        from pipelines.load.promote import main

        assert main(["--apply"]) == 1
        assert "untouched" in capsys.readouterr().err.lower()

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
        """
        with get_engine().connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalar()
        assert version == "0009_analytics_schema", (
            f"the database is at {version}; migrations are not being committed"
        )

    def test_the_version_table_is_operational(self) -> None:
        """It records which migrations ran, not what the data is."""
        with get_engine().connect() as connection:
            assert "alembic_version" in tables_in(connection, "public")
            assert "alembic_version" not in tables_in(connection, SERVING)
