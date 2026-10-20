"""Reading every page of a roster, and not looping when there are none.

WHAT WAS BEING LOST

`/league-players` returns 200 rows a page and reports the rest in `pager`,
which `_roster` read `data` from and ignored. Measured against the API across
the 45 configured competitions, the product fetched 8,862 of 28,311 available
players - 31%. England's League Cup supplied 200 of 2,019; the Champions League
200 of 1,999; Spain's La Liga 200 of 587.

Verified against the real endpoint before any of this was written: season 17146
returns 200 + 200 + 122 = 522 rows over three pages, with no id appearing
twice and the union equal to the pager's `total_results`.

THE DANGEROUS HALF

The load path does not call the API. `pipelines.load.load_providers` replaces
`_get` with a `SnapshotReader`, which answers every `/league-players` call with
the whole roster and `{"data": [...]}` - no pager. So a loop that stopped on "a
page shorter than 200" would ask a snapshot of exactly 200 players for page 2,
get the same 200 back, and never stop. Termination is driven by `max_page`, and
an absent pager means one page.

`TestItCannotLoop` is the half of this file that matters.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.providers.footystats import (
    MAX_ROSTER_PAGES,
    FootyStatsProvider,
    _page_count,
)

from .test_footystats_provider import build_settings


def provider() -> FootyStatsProvider:
    return FootyStatsProvider(build_settings(footystats_api_key="test-key"))


class Transport:
    """Stands in for `_get`, recording what was asked for."""

    def __init__(self, pages: list[list[int]], *, pager: bool = True) -> None:
        self._pages = pages
        self._pager = pager
        self.calls: list[int] = []

    def __call__(self, path: str, **params: Any) -> Any:
        assert path == "/league-players"
        page = int(params.get("page", 1))
        self.calls.append(page)
        rows = self._pages[page - 1] if 1 <= page <= len(self._pages) else []
        body: dict[str, Any] = {"data": [{"id": i} for i in rows]}
        if self._pager:
            body["pager"] = {"current_page": page, "max_page": len(self._pages)}
        return body


def attach(transport: Transport) -> FootyStatsProvider:
    instance = provider()
    instance._get = transport  # type: ignore[method-assign]
    return instance


class TestEveryPageIsRead:
    def test_three_pages_become_one_roster(self) -> None:
        # The real shape of season 17146: 200 + 200 + 122.
        transport = Transport([list(range(200)), list(range(200, 400)), list(range(400, 522))])
        roster = attach(transport)._roster("17146")

        assert len(roster) == 522
        assert transport.calls == [1, 2, 3]
        assert [r["id"] for r in roster] == list(range(522))

    def test_a_single_page_asks_once(self) -> None:
        transport = Transport([[1, 2, 3]])
        assert len(attach(transport)._roster("1")) == 3
        assert transport.calls == [1]

    def test_the_roster_is_cached_across_calls(self) -> None:
        # One roster serves `get_players` and `get_competition_stats`, and the
        # rate limit makes a second fetch expensive.
        transport = Transport([list(range(200)), [200]])
        instance = attach(transport)
        instance._roster("1")
        instance._roster("1")
        assert transport.calls == [1, 2]

    def test_non_dict_rows_are_dropped_not_counted(self) -> None:
        instance = provider()
        instance._get = lambda path, **p: {  # type: ignore[method-assign]
            "data": [{"id": 1}, "a string", None, {"id": 2}],
            "pager": {"max_page": 1},
        }
        assert [r["id"] for r in instance._roster("1")] == [1, 2]

    def test_a_row_without_an_id_is_still_returned(self) -> None:
        """The caller filters on `id`; this must not decide that for it.

        `ingest_competition` builds `player_ids` from rows that have one, and
        `record_roster` keeps the records because the roster carries the club.
        Dropping them here would change what a generation expects.
        """
        instance = provider()
        instance._get = lambda path, **p: {  # type: ignore[method-assign]
            "data": [{"id": 1}, {"full_name": "No Id"}],
            "pager": {"max_page": 1},
        }
        assert len(instance._roster("1")) == 2

    def test_several_rows_without_an_id_do_not_collide_with_each_other(self) -> None:
        """Keyed on `str(row.get("id"))`, every one of them is "None".

        The first survives and the rest are dropped as duplicates - silently,
        and only for the rows whose data is already thinnest.
        """
        instance = provider()
        instance._get = lambda path, **p: {  # type: ignore[method-assign]
            "data": [{"full_name": "A"}, {"full_name": "B"}, {"full_name": "C"}],
            "pager": {"max_page": 1},
        }
        assert len(instance._roster("1")) == 3


class TestItCannotLoop:
    """The load path, which has no pager and must not be asked twice."""

    def test_a_body_with_no_pager_is_one_page(self) -> None:
        # Exactly the `SnapshotReader` reply, and exactly 200 rows - the length
        # that a "short page means the end" rule would treat as "there is more".
        transport = Transport([list(range(200))], pager=False)
        roster = attach(transport)._roster("1")

        assert len(roster) == 200
        assert transport.calls == [1], "a snapshot was asked for a second page"

    def test_a_server_that_ignores_page_does_not_triple_the_roster(self) -> None:
        """Nothing downstream can tell a tripled roster from a real one."""
        calls: list[int] = []

        def always_page_one(path: str, **params: Any) -> Any:
            calls.append(int(params.get("page", 1)))
            return {
                "data": [{"id": i} for i in range(200)],
                "pager": {"current_page": 1, "max_page": 5},
            }

        instance = provider()
        instance._get = always_page_one  # type: ignore[method-assign]
        roster = instance._roster("1")

        assert len(roster) == 200
        # It stops as soon as a promised page brings nothing new, rather than
        # spending the rate limiter's budget on all five.
        assert calls == [1, 2]

    @pytest.mark.parametrize(
        "pager",
        [
            None,
            {},
            "not a dict",
            {"max_page": None},
            {"max_page": "many"},
            {"max_page": 0},
            {"max_page": -3},
            {"current_page": 1},
        ],
        ids=["absent", "empty", "wrong-type", "null", "text", "zero", "negative", "no-max"],
    )
    def test_an_unusable_pager_means_one_page(self, pager: object) -> None:
        assert _page_count(pager) == 1

    def test_an_absurd_pager_is_capped(self) -> None:
        # Believing one would spend a whole run on a single competition.
        assert _page_count({"max_page": 10**9}) == MAX_ROSTER_PAGES
        assert _page_count({"max_page": 11}) == 11

    def test_a_string_page_count_the_api_could_return_is_honoured(self) -> None:
        # JSON numbers arrive as ints here, but this field has been a string in
        # other FootyStats responses and reading it as one page would silently
        # restore the old behaviour.
        assert _page_count({"max_page": "3"}) == 3

    def test_an_empty_first_page_ends_it(self) -> None:
        transport = Transport([[]])
        assert attach(transport)._roster("1") == []
        assert transport.calls == [1]

    def test_a_non_dict_body_ends_it(self) -> None:
        instance = provider()
        instance._get = lambda path, **p: ["not", "a", "dict"]  # type: ignore[method-assign]
        assert instance._roster("1") == []


class TestDuplicatesAcrossPages:
    def test_an_id_repeated_on_a_later_page_is_kept_once(self) -> None:
        # The real endpoint does not overlap - verified - but a roster that
        # changes between two page requests can repeat a player, and a doubled
        # player doubles every count derived from them.
        transport = Transport([[1, 2, 3], [3, 4, 5]])
        roster = attach(transport)._roster("1")
        assert [r["id"] for r in roster] == [1, 2, 3, 4, 5]
