"""The download has to leave the tables where everything downstream looks.

It fetched a 230 MB archive and stopped. Nothing in the repository unzipped
it, so `data/raw/transfermarkt/tables/` was populated only on a machine where
somebody had done it by hand - and a CI runner is never that machine. The
scheduled refresh downloaded the archive successfully and then reported the
tables missing, suggesting the download that had just succeeded.

The archive carries twelve tables; the product reads five. The other seven are
match events it does not model.
"""

from __future__ import annotations

import gzip
import zipfile
from pathlib import Path

import pytest
from pipelines.transfermarkt.download import TABLES, extract


def archive(path: Path, names: list[str]) -> Path:
    """A stand-in for the real snapshot: the same names, trivial contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as bundle:
        for name in names:
            bundle.writestr(name, gzip.compress(f"column\n{name}\n".encode()))
    return path


REAL_LAYOUT = [
    "appearances.csv.gz",
    "club_games.csv.gz",
    "clubs.csv.gz",
    "competitions.csv.gz",
    "countries.csv.gz",
    "game_events.csv.gz",
    "game_lineups.csv.gz",
    "games.csv.gz",
    "national_teams.csv.gz",
    "player_valuations.csv.gz",
    "players.csv.gz",
    "transfers.csv.gz",
]


def test_the_five_tables_land_where_the_loader_reads_them(tmp_path: Path) -> None:
    source = archive(tmp_path / "snapshot.zip", REAL_LAYOUT)
    tables = tmp_path / "tables"

    extract(source, tables)

    for table in TABLES:
        assert (tables / f"{table}.csv.gz").exists(), f"{table} was not extracted"


def test_the_seven_it_does_not_model_are_left_in_the_archive(tmp_path: Path) -> None:
    # 230 MB on disk against the 60 MB actually read, and every one of them a
    # file somebody later has to explain the absence of a loader for.
    source = archive(tmp_path / "snapshot.zip", REAL_LAYOUT)
    tables = tmp_path / "tables"

    extract(source, tables)

    extracted = {path.name for path in tables.iterdir()}
    assert extracted == {f"{table}.csv.gz" for table in TABLES}
    assert "games.csv.gz" not in extracted


def test_a_changed_layout_is_refused_rather_than_half_extracted(tmp_path: Path) -> None:
    # Four of five would load, and the product would serve a dataset missing
    # its valuations while every check passed on what was there.
    source = archive(tmp_path / "snapshot.zip", [n for n in REAL_LAYOUT if "valuations" not in n])

    with pytest.raises(SystemExit) as refused:
        extract(source, tmp_path / "tables")

    assert "player_valuations" in str(refused.value)
    assert not (tmp_path / "tables").exists() or not list((tmp_path / "tables").iterdir())


def test_a_member_cannot_write_outside_the_tables_directory(tmp_path: Path) -> None:
    # A zip may name a member `../../anywhere`. Names are matched on their last
    # component and each file is written explicitly, so the archive chooses
    # which table it supplies and never where it lands.
    source = archive(
        tmp_path / "snapshot.zip",
        ["../../escaped/players.csv.gz", *[n for n in REAL_LAYOUT if n != "players.csv.gz"]],
    )
    tables = tmp_path / "tables"

    extract(source, tables)

    assert (tables / "players.csv.gz").exists()
    assert not (tmp_path.parent / "escaped").exists()


def test_extraction_does_not_redo_work_it_has_already_done(tmp_path: Path) -> None:
    source = archive(tmp_path / "snapshot.zip", REAL_LAYOUT)
    tables = tmp_path / "tables"
    extract(source, tables)

    marker = tables / "players.csv.gz"
    marker.write_bytes(b"left alone")
    extract(source, tables)
    assert marker.read_bytes() == b"left alone"

    extract(source, tables, force=True)
    assert marker.read_bytes() != b"left alone"
