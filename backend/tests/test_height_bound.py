"""What counts as a possible height, in the one place that decides it.

WHAT BROKE

The nightly load failed twice, with the whole run lost each time:

    (psycopg.errors.CheckViolation) new row for relation "dim_player"
    violates check constraint "ck_dim_player_height_plausible"

FootyStats had reported a height of 100cm for one player. The bound was written
out by hand in four places, and two of them disagreed - `dim_player`'s check
constraint and the Transfermarkt reader allowed 140-220, while the canonical
schema and the FootyStats reader allowed 100-250. So 100 passed the reader that
read it, passed the schema that carried it, and was rejected by the database.

It did not fail alone. Players are inserted a thousand at a time, so one
impossible height rejected the batch, and the batch ending ended the load - no
players, no stats, nothing published, for one wrong number about one player.

WHAT IS ASSERTED

That the four places now answer to one bound, and that a reader meeting an
impossible height loses the height and keeps the player. The second is the
behaviour the first exists to make possible: dropping the record would discard
a real footballer because a provider mistyped their height.

These are deliberately not written against the figures 140 and 220. Pinning the
numbers here would mean a fifth copy, and a test that agrees with a constant by
restating it is the thing that let this through.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from app.models.dimensions import DimPlayer
from app.providers import transfermarkt
from app.providers.footystats import FootyStatsProvider
from app.schemas.canonical import MAX_HEIGHT_CM, MIN_HEIGHT_CM, PlayerIdentity

from .test_footystats_provider import build_settings


def provider() -> FootyStatsProvider:
    return FootyStatsProvider(build_settings(footystats_api_key="test-key"))


def row(height: object) -> dict[str, object]:
    """A roster row carrying one height and nothing else that matters."""
    return {"id": 1, "known_as": "A Player", "position": "Midfielder", "height": height}


class TestOneBoundEverywhere:
    def test_the_database_constraint_is_built_from_it(self) -> None:
        """Not written out beside it.

        Read off the mapped table rather than the source text, so the assertion
        is about the constraint the database will actually be given. Looked up
        by the name production quoted when it rejected the row.
        """
        constraints = {
            c.name: c.sqltext.text
            for c in inspect(DimPlayer).local_table.constraints
            if hasattr(c, "sqltext")
        }
        sql = constraints["ck_dim_player_height_plausible"]
        assert f"BETWEEN {MIN_HEIGHT_CM} AND {MAX_HEIGHT_CM}" in sql

    def test_the_transfermarkt_reader_uses_it(self) -> None:
        """It had its own pair of literals, which happened to be right.

        Being right by coincidence is what made the disagreement invisible:
        nothing compared the two copies, so nobody saw that a third and fourth
        said something else.
        """
        assert transfermarkt.MIN_HEIGHT_CM is MIN_HEIGHT_CM
        assert transfermarkt.MAX_HEIGHT_CM is MAX_HEIGHT_CM

    @pytest.mark.parametrize("delta", [-1, 0])
    def test_the_schema_refuses_what_the_database_would_refuse(self, delta: int) -> None:
        """The net beneath the readers, and it has to sit at the same height.

        A schema looser than the constraint is exactly the configuration that
        failed: the value travelled all the way to the insert before anything
        objected, by which time it was inside a batch of a thousand.
        """
        with pytest.raises(ValidationError):
            PlayerIdentity(
                source_player_id="1",
                full_name="A Player",
                raw_position="Midfielder",
                height_cm=MIN_HEIGHT_CM + delta - 1,
            )
        with pytest.raises(ValidationError):
            PlayerIdentity(
                source_player_id="1",
                full_name="A Player",
                raw_position="Midfielder",
                height_cm=MAX_HEIGHT_CM - delta + 1,
            )


class TestAnImpossibleHeightCostsTheHeightOnly:
    @pytest.mark.parametrize(
        "height",
        [100, MIN_HEIGHT_CM - 1, MAX_HEIGHT_CM + 1, 250],
    )
    def test_the_player_survives_without_it(self, height: int) -> None:
        """100 is the value that failed production, named explicitly.

        The others are the edges, which is where a comparison written with the
        wrong operator would still pass.
        """
        identity = provider()._identity(row(height), "footystats:17117")
        assert identity.height_cm is None
        assert identity.full_name == "A Player"
        assert identity.raw_position == "Midfielder"

    @pytest.mark.parametrize("height", [MIN_HEIGHT_CM, 181, MAX_HEIGHT_CM])
    def test_a_possible_height_is_kept_unchanged(self, height: int) -> None:
        """Including both edges, which are possible heights and not errors."""
        assert provider()._identity(row(height), "footystats:17117").height_cm == height

    def test_a_missing_height_stays_missing(self) -> None:
        """Absent is not impossible, and neither is zero-as-sentinel.

        The provider sends `0` and `None` for players it has no height for. A
        reader that treated the rejection as "set it to the minimum" would
        invent a 140cm footballer out of a null.
        """
        assert provider()._identity(row(None), "footystats:17117").height_cm is None
        assert provider()._identity(row(0), "footystats:17117").height_cm is None
