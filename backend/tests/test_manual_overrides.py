"""A pair a person checked by hand, from the CSV to the bridge row.

WHAT WAS BROKEN, IN THREE PLACES AT ONCE

`data/manual/player_mapping.csv` exists and documents itself: "A mapping listed
here always wins over whatever the resolver decides, and is recorded in
bridge_player_source with manual_override = true." None of that happened.

1. The reader lived in `pipelines.identity_resolution.run`, which produces a
   report and never touches the database. The pipeline runs `resolve`, which
   never loaded the file.
2. `resolve`'s merge loop accepted `MatchStatus.MATCHED` only. A MANUAL result
   - the one status that means a person decided - was counted into the report
   and then skipped by the same condition.
3. Nothing anywhere set `manual_override = True`. It was read in three places
   and written in none, which is why the data-quality page has always shown
   zero confirmed by hand.

So a person could read the instructions in the file, verify a pair, commit it,
and have nothing happen - with nothing saying so. Each break alone would have
been enough; each also hid the next.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from pipelines.identity_resolution.matcher import (
    Identity,
    IdentityResolver,
    MatchStatus,
    load_manual_overrides,
)
from pipelines.load.load_providers import _normalize
from sqlalchemy.orm import Session

from app.models import (
    BridgePlayerSource,
    DimCompetition,
    DimPlayer,
    DimSeason,
    FactPlayerSeasonStats,
)
from app.schemas.canonical import PositionGroup

HEADER = "source,source_player_id,target_player_id,note\n"


def write_csv(path: Path, body: str) -> Path:
    path.write_text(HEADER + body, encoding="utf-8")
    return path


PERFORMANCE = "mo_perf"
IDENTITY = "mo_ident"


def pair(session: Session, name: str, key: str):  # type: ignore[no-untyped-def]
    """One human being as two rows, with the bridge that will be repointed."""
    rows = []
    for label, position in ((PERFORMANCE, None), (IDENTITY, PositionGroup.CM)):
        row = DimPlayer(
            full_name=f"{name} {label}",
            normalized_name=_normalize(f"{name} {label}"),
            date_of_birth=dt.date(1999, 5, 5),
            nationality="Portugal",
            position_group=position,
        )
        session.add(row)
        session.flush()
        rows.append(row)

    performance, identity_row = rows
    bridge_row = BridgePlayerSource(
        player_id=performance.player_id,
        source=PERFORMANCE,
        source_player_id=f"p-{key}",
        match_method="source_native_id",
        match_confidence=1.0,
        manual_override=False,
    )
    session.add(bridge_row)
    session.add(
        BridgePlayerSource(
            player_id=identity_row.player_id,
            source=IDENTITY,
            source_player_id=f"t-{key}",
            match_method="source_native_id",
            match_confidence=1.0,
            manual_override=False,
        )
    )
    competition_id = f"{PERFORMANCE}:{key}"
    session.add(
        DimCompetition(
            competition_id=competition_id,
            name=f"League {key}",
            country="Portugal",
            tier=1,
            source=PERFORMANCE,
        )
    )
    if session.get(DimSeason, "2024") is None:
        session.add(DimSeason(season_id="2024", name="2024", start_year=2024, end_year=2025))
    session.flush()
    session.add(
        FactPlayerSeasonStats(
            player_id=performance.player_id,
            competition_id=competition_id,
            season_id="2024",
            appearances=10,
            minutes=900,
            source=PERFORMANCE,
        )
    )
    session.flush()
    return bridge_row, (performance, identity_row)


class TestReadingTheFile:
    def test_a_confirmed_pair_is_read(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "m.csv", "footystats,123,tm-456,checked on the club site\n")
        assert load_manual_overrides(path) == {("footystats", "123"): "tm-456"}

    def test_an_absent_file_is_not_an_error(self, tmp_path: Path) -> None:
        # The normal case: most installations never write one.
        assert load_manual_overrides(tmp_path / "nothing.csv") == {}

    def test_the_real_file_is_readable_and_its_shape_is_what_the_loader_expects(self) -> None:
        """The committed file is documentation that has to stay executable.

        It carries only comments today. If its header ever drifts from the
        loader, the next person to add a row gets silence - which is the
        failure this whole file is about.
        """
        from pipelines.identity_resolution.matcher import MANUAL_MAPPING

        assert MANUAL_MAPPING.exists(), MANUAL_MAPPING
        header = MANUAL_MAPPING.read_text(encoding="utf-8").splitlines()
        columns = next(line for line in header if line.startswith("source,"))
        assert columns == "source,source_player_id,target_player_id,note"
        assert load_manual_overrides() == {}

    @pytest.mark.parametrize(
        "body",
        [
            "# footystats,123,tm-456,a commented row\n",
            "footystats,,tm-456,no source id\n",
            "footystats,123,,no target\n",
            ",123,tm-456,no source\n",
            "\n",
        ],
        ids=["commented", "no-source-id", "no-target", "no-source", "blank"],
    )
    def test_an_incomplete_row_is_skipped_rather_than_half_applied(
        self, tmp_path: Path, body: str
    ) -> None:
        assert load_manual_overrides(write_csv(tmp_path / "m.csv", body)) == {}

    def test_whitespace_around_the_values_is_tolerated(self, tmp_path: Path) -> None:
        # Hand-edited file; a stray space must not silently drop a decision.
        path = write_csv(tmp_path / "m.csv", "  footystats , 123 , tm-456 ,typed by hand\n")
        assert load_manual_overrides(path) == {("footystats", "123"): "tm-456"}


def identity(source: str, source_id: str, name: str, *, dob: dt.date | None = None) -> Identity:
    return Identity(
        source=source,
        source_player_id=source_id,
        full_name=name,
        date_of_birth=dob or dt.date(1999, 5, 5),
    )


class TestTheResolverHonoursIt:
    def test_a_confirmed_pair_beats_what_the_resolver_would_have_said(self) -> None:
        """Different names, different birthdays: nothing would match these."""
        source = identity("footystats", "123", "Someone Entirely Different")
        target = identity("transfermarkt", "tm-456", "Nobody Alike", dob=dt.date(1980, 1, 1))

        resolver = IdentityResolver([target], manual_overrides={("footystats", "123"): "tm-456"})
        result = resolver.resolve(source)

        assert result.status is MatchStatus.MANUAL
        assert result.method == "manual_override"
        assert result.confidence == 1.0
        assert result.target is target

    def test_without_the_override_the_same_pair_is_refused(self) -> None:
        # The control. Otherwise the test above proves nothing about the file.
        source = identity("footystats", "123", "Someone Entirely Different")
        target = identity("transfermarkt", "tm-456", "Nobody Alike", dob=dt.date(1980, 1, 1))

        result = IdentityResolver([target]).resolve(source)
        assert result.status is MatchStatus.UNMATCHED

    def test_an_override_pointing_at_nothing_is_refused_and_named(self) -> None:
        """A person's typo must not become a silent no-op."""
        source = identity("footystats", "123", "Someone")
        resolver = IdentityResolver([], manual_overrides={("footystats", "123"): "tm-gone"})
        result = resolver.resolve(source)

        assert result.status is MatchStatus.UNMATCHED
        assert result.method == "manual_override_target_missing"
        assert "tm-gone" in " ".join(result.reasons)


class TestTheProductionPathIsWiredToIt:
    """`resolve` is what the pipeline runs; `run` is not.

    These read the module rather than executing a full resolution, because the
    defect was structural - a reader that existed in the wrong module, a status
    excluded by a condition, a column never written. Each is visible in the
    source and each was invisible in every passing test.
    """

    @staticmethod
    def source() -> str:
        return (
            Path(__file__).resolve().parents[2] / "pipelines" / "identity_resolution" / "resolve.py"
        ).read_text(encoding="utf-8")

    def test_it_loads_the_confirmations(self) -> None:
        body = self.source()
        assert "load_manual_overrides()" in body
        assert "manual_overrides=overrides" in body

    def test_it_applies_a_manual_decision_rather_than_only_counting_it(self) -> None:
        # `result.status is not MatchStatus.MATCHED` was the whole bug: MANUAL
        # fell through it, so the one status meaning "a person decided" was the
        # one never acted on.
        body = self.source()
        assert "MatchStatus.MANUAL}" in body or "MatchStatus.MANUAL," in body
        assert "result.status not in decided" in body

    def test_it_records_the_decision_on_the_bridge(self) -> None:
        body = self.source()
        assert "manual_override=bridges.c.manual" in body

    def test_the_guard_does_not_make_the_flag_permanent(self) -> None:
        """A person must be able to correct their own earlier decision.

        Skipping on the flag alone would freeze the row forever: the guard that
        exists to respect a person would be the reason their correction was
        ignored.
        """
        assert "bridge.manual_override and not confirmed" in self.source()

    def test_the_workflow_runs_this_module(self) -> None:
        # If the pipeline ever moves to `run`, the wiring above protects
        # nothing - and `run` still does not write to the database.
        workflow = (
            Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pipeline.yml"
        ).read_text(encoding="utf-8")
        assert "pipelines.identity_resolution.resolve --apply" in workflow
        assert "pipelines.identity_resolution.run --apply" not in workflow

    def test_the_loader_lives_where_the_production_path_can_import_it(self) -> None:
        """It used to live in `run`, which imports `app.providers` at module
        level - unreachable from `resolve`, which only puts `backend` on the
        path inside `main()`. That is most of why the file did nothing."""
        matcher = (
            Path(__file__).resolve().parents[2] / "pipelines" / "identity_resolution" / "matcher.py"
        ).read_text(encoding="utf-8")
        assert "def load_manual_overrides" in matcher

        run = (
            Path(__file__).resolve().parents[2] / "pipelines" / "identity_resolution" / "run.py"
        ).read_text(encoding="utf-8")
        assert "def load_manual_overrides" not in run, "two copies will drift"


@pytest.mark.integration
class TestTheFlagReachesTheDatabase:
    """The end of the chain, against a real PostgreSQL.

    Everything above this point is either the loader or the source. This is the
    part that was missing entirely: `manual_override` was read in three places
    and written in none.
    """

    def test_a_confirmed_merge_sets_the_flag_and_an_automatic_one_does_not(
        self, db_session: Session
    ) -> None:
        from pipelines.identity_resolution.resolve import PlannedMerge, merge_all

        confirmed_bridge, confirmed = pair(db_session, "Confirmed", "c")
        automatic_bridge, automatic = pair(db_session, "Automatic", "a")

        outcome = merge_all(
            db_session,
            [
                PlannedMerge(
                    performance_player_id=confirmed[0].player_id,
                    identity_player_id=confirmed[1].player_id,
                    bridge_id=confirmed_bridge.id,
                    method="manual_override",
                    confidence=1.0,
                    manual=True,
                ),
                PlannedMerge(
                    performance_player_id=automatic[0].player_id,
                    identity_player_id=automatic[1].player_id,
                    bridge_id=automatic_bridge.id,
                    method="exact_name+dob",
                    confidence=0.95,
                ),
            ],
        )

        assert len(outcome.merged) == 2
        db_session.refresh(confirmed_bridge)
        db_session.refresh(automatic_bridge)

        assert confirmed_bridge.manual_override is True
        assert confirmed_bridge.match_method == "manual_override"
        # And the automatic one is untouched, per row rather than per batch.
        assert automatic_bridge.manual_override is False
        assert automatic_bridge.match_method == "exact_name+dob"

    def test_the_default_leaves_the_flag_alone_for_every_existing_caller(
        self, db_session: Session
    ) -> None:
        """`merge_player` and every planned merge without `manual` must keep
        writing False, or a routine refresh would start marking its own
        guesses as human-confirmed and become unrepeatable."""
        from pipelines.identity_resolution.resolve import merge_player

        bridge_row, (performance, identity_row) = pair(db_session, "Default", "d")

        assert merge_player(
            db_session,
            performance.player_id,
            identity_row.player_id,
            bridge_id=bridge_row.id,
            method="exact_name+dob",
            confidence=0.95,
        )
        db_session.refresh(bridge_row)
        assert bridge_row.manual_override is False
