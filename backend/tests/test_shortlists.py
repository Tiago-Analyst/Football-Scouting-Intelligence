"""Shortlists.

The interesting assertions are about what one account *cannot* see or do to
another's data, and about what the CSV export deliberately does not contain.
A shortlist that works for its owner is the easy half.
"""

from __future__ import annotations

import csv
import io
import secrets
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.shortlists import EXPORT_COLUMNS, MIXED_COMPETITION_CAVEAT, MIXED_POSITION_CAVEAT
from app.core.errors import NotFoundError
from app.models.accounts import UserAccount
from app.models.shortlists import Shortlist, ShortlistEntry
from app.services.auth_service import register_user
from app.services.shortlist_service import (
    MAX_COMPARE,
    MAX_ENTRIES_PER_SHORTLIST,
    MAX_NOTE_LENGTH,
    MAX_SHORTLISTS_PER_USER,
    DuplicateShortlistName,
    InvalidShortlist,
    ShortlistLimitReached,
    add_entry,
    create_shortlist,
    delete_shortlist,
    get_shortlist,
    list_entries,
    list_shortlists,
    remove_entry,
    set_note,
    update_shortlist,
)

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"


def make_user(session: Session, label: str = "a") -> UserAccount:
    return register_user(
        session,
        email=f"shortlist-{label}-{secrets.token_hex(4)}@example.test",
        password=PASSWORD,
        display_name=f"Scout {label}",
    )


# ---------------------------------------------------------------------------
# Creating and naming
# ---------------------------------------------------------------------------


class TestCreatingShortlists:
    def test_a_shortlist_is_created_and_owned(self, db_session: Session) -> None:
        user = make_user(db_session)
        shortlist = create_shortlist(db_session, user_id=user.user_id, name="Left backs")
        assert shortlist.shortlist_id is not None
        assert shortlist.user_id == user.user_id

    def test_the_name_is_trimmed(self, db_session: Session) -> None:
        user = make_user(db_session)
        shortlist = create_shortlist(db_session, user_id=user.user_id, name="  Wingers  ")
        assert shortlist.name == "Wingers"

    def test_a_blank_name_is_refused(self, db_session: Session) -> None:
        user = make_user(db_session)
        with pytest.raises(InvalidShortlist):
            create_shortlist(db_session, user_id=user.user_id, name="   ")

    def test_the_same_name_twice_is_refused(self, db_session: Session) -> None:
        user = make_user(db_session)
        create_shortlist(db_session, user_id=user.user_id, name="Targets")
        with pytest.raises(DuplicateShortlistName):
            create_shortlist(db_session, user_id=user.user_id, name="Targets")

    def test_two_people_may_use_the_same_name(self, db_session: Session) -> None:
        """Names are unique per owner. A global constraint would leak that
        someone else already uses the name."""
        first = make_user(db_session, "one")
        second = make_user(db_session, "two")
        create_shortlist(db_session, user_id=first.user_id, name="Targets")
        create_shortlist(db_session, user_id=second.user_id, name="Targets")

    def test_the_shortlist_limit_is_enforced(self, db_session: Session) -> None:
        user = make_user(db_session)
        for index in range(MAX_SHORTLISTS_PER_USER):
            create_shortlist(db_session, user_id=user.user_id, name=f"List {index}")
        with pytest.raises(ShortlistLimitReached):
            create_shortlist(db_session, user_id=user.user_id, name="One too many")


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


class TestOwnership:
    """The point of the whole feature: nobody sees anyone else's list."""

    def test_another_users_shortlist_is_not_found(self, db_session: Session) -> None:
        owner = make_user(db_session, "owner")
        intruder = make_user(db_session, "intruder")
        shortlist = create_shortlist(db_session, user_id=owner.user_id, name="Private")

        with pytest.raises(NotFoundError):
            get_shortlist(db_session, user_id=intruder.user_id, shortlist_id=shortlist.shortlist_id)

    def test_listing_shows_only_your_own(self, db_session: Session) -> None:
        owner = make_user(db_session, "owner")
        intruder = make_user(db_session, "intruder")
        create_shortlist(db_session, user_id=owner.user_id, name="Mine")

        assert list_shortlists(db_session, user_id=intruder.user_id) == []
        assert len(list_shortlists(db_session, user_id=owner.user_id)) == 1

    def test_another_user_cannot_rename_it(self, db_session: Session) -> None:
        owner = make_user(db_session, "owner")
        intruder = make_user(db_session, "intruder")
        shortlist = create_shortlist(db_session, user_id=owner.user_id, name="Private")

        with pytest.raises(NotFoundError):
            update_shortlist(
                db_session,
                user_id=intruder.user_id,
                shortlist_id=shortlist.shortlist_id,
                name="Hijacked",
            )
        assert shortlist.name == "Private"

    def test_another_user_cannot_delete_it(self, db_session: Session) -> None:
        owner = make_user(db_session, "owner")
        intruder = make_user(db_session, "intruder")
        shortlist = create_shortlist(db_session, user_id=owner.user_id, name="Private")

        with pytest.raises(NotFoundError):
            delete_shortlist(
                db_session, user_id=intruder.user_id, shortlist_id=shortlist.shortlist_id
            )
        assert (
            db_session.scalar(
                select(Shortlist).where(Shortlist.shortlist_id == shortlist.shortlist_id)
            )
            is not None
        )

    def test_another_user_cannot_add_to_it(self, db_session: Session) -> None:
        owner = make_user(db_session, "owner")
        intruder = make_user(db_session, "intruder")
        shortlist = create_shortlist(db_session, user_id=owner.user_id, name="Private")

        with pytest.raises(NotFoundError):
            add_entry(
                db_session,
                user_id=intruder.user_id,
                shortlist_id=shortlist.shortlist_id,
                player_key="whoever",
            )

    def test_deleting_the_account_removes_the_shortlists(self, db_session: Session) -> None:
        user = make_user(db_session)
        shortlist = create_shortlist(db_session, user_id=user.user_id, name="Targets")
        add_entry(
            db_session, user_id=user.user_id, shortlist_id=shortlist.shortlist_id, player_key="p1"
        )

        db_session.delete(user)
        db_session.flush()

        assert db_session.scalar(select(Shortlist).where(Shortlist.user_id == user.user_id)) is None
        assert (
            db_session.scalar(
                select(ShortlistEntry).where(ShortlistEntry.shortlist_id == shortlist.shortlist_id)
            )
            is None
        )


# ---------------------------------------------------------------------------
# Entries and notes
# ---------------------------------------------------------------------------


class TestEntries:
    @pytest.fixture
    def owned(self, db_session: Session) -> tuple[int, int]:
        user = make_user(db_session)
        shortlist = create_shortlist(db_session, user_id=user.user_id, name="Targets")
        return user.user_id, shortlist.shortlist_id

    def test_a_player_is_saved(self, db_session: Session, owned: tuple[int, int]) -> None:
        user_id, shortlist_id = owned
        entry = add_entry(
            db_session,
            user_id=user_id,
            shortlist_id=shortlist_id,
            player_key="p1",
            player_name="A Player",
        )
        assert entry.player_key == "p1"
        assert entry.player_name == "A Player"

    def test_saving_twice_does_not_duplicate(
        self, db_session: Session, owned: tuple[int, int]
    ) -> None:
        """The desired state is reached either way, so this is not an error."""
        user_id, shortlist_id = owned
        first = add_entry(db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1")
        second = add_entry(db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1")
        assert first.entry_id == second.entry_id
        assert len(list_entries(db_session, shortlist_id=shortlist_id)) == 1

    def test_saving_twice_keeps_the_first_note(
        self, db_session: Session, owned: tuple[int, int]
    ) -> None:
        """Re-saving must not silently erase what the owner wrote."""
        user_id, shortlist_id = owned
        add_entry(
            db_session,
            user_id=user_id,
            shortlist_id=shortlist_id,
            player_key="p1",
            note="Watch again in April",
        )
        again = add_entry(
            db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1", note=None
        )
        assert again.note == "Watch again in April"

    def test_a_note_can_be_written_replaced_and_cleared(
        self, db_session: Session, owned: tuple[int, int]
    ) -> None:
        user_id, shortlist_id = owned
        add_entry(db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1")

        written = set_note(
            db_session,
            user_id=user_id,
            shortlist_id=shortlist_id,
            player_key="p1",
            note="Left foot",
        )
        assert written.note == "Left foot"

        replaced = set_note(
            db_session,
            user_id=user_id,
            shortlist_id=shortlist_id,
            player_key="p1",
            note="Right foot",
        )
        assert replaced.note == "Right foot"

        cleared = set_note(
            db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1", note="  "
        )
        assert cleared.note is None

    def test_an_over_long_note_is_refused(
        self, db_session: Session, owned: tuple[int, int]
    ) -> None:
        user_id, shortlist_id = owned
        add_entry(db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1")
        with pytest.raises(InvalidShortlist):
            set_note(
                db_session,
                user_id=user_id,
                shortlist_id=shortlist_id,
                player_key="p1",
                note="x" * (MAX_NOTE_LENGTH + 1),
            )

    def test_a_note_on_an_unsaved_player_is_not_found(
        self, db_session: Session, owned: tuple[int, int]
    ) -> None:
        user_id, shortlist_id = owned
        with pytest.raises(NotFoundError):
            set_note(
                db_session,
                user_id=user_id,
                shortlist_id=shortlist_id,
                player_key="never-saved",
                note="x",
            )

    def test_removing_a_player(self, db_session: Session, owned: tuple[int, int]) -> None:
        user_id, shortlist_id = owned
        add_entry(db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1")

        assert (
            remove_entry(db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1")
            is True
        )
        assert list_entries(db_session, shortlist_id=shortlist_id) == []

    def test_removing_one_that_is_not_there_reports_nothing_removed(
        self, db_session: Session, owned: tuple[int, int]
    ) -> None:
        user_id, shortlist_id = owned
        assert (
            remove_entry(db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="ghost")
            is False
        )

    def test_the_entry_limit_is_enforced(self, db_session: Session, owned: tuple[int, int]) -> None:
        user_id, shortlist_id = owned
        for index in range(MAX_ENTRIES_PER_SHORTLIST):
            add_entry(
                db_session,
                user_id=user_id,
                shortlist_id=shortlist_id,
                player_key=f"p{index}",
            )
        with pytest.raises(ShortlistLimitReached):
            add_entry(
                db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="one-too-many"
            )

    def test_saving_a_player_updates_the_lists_timestamp(
        self, db_session: Session, owned: tuple[int, int]
    ) -> None:
        """So "most recently changed first" means what it says."""
        user_id, shortlist_id = owned
        before = get_shortlist(db_session, user_id=user_id, shortlist_id=shortlist_id).updated_at
        add_entry(db_session, user_id=user_id, shortlist_id=shortlist_id, player_key="p1")
        after = get_shortlist(db_session, user_id=user_id, shortlist_id=shortlist_id).updated_at
        assert after > before


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@pytest.fixture
def signed_in(client: TestClient) -> Iterator[TestClient]:
    """A client with an account, removed again afterwards.

    These tests go through the app's own session, which commits, so the account
    is real and has to be cleaned up. Deleting it cascades the shortlists away.
    """
    email = f"api-{secrets.token_hex(6)}@example.test"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    yield client

    from app.core.database import get_engine

    with Session(get_engine()) as cleanup:
        account = cleanup.scalar(select(UserAccount).where(UserAccount.email == email))
        if account is not None:
            cleanup.delete(account)
            cleanup.commit()


def a_player(client: TestClient) -> dict[str, object]:
    body = client.get("/api/v1/players", params={"limit": 1}).json()
    return body["items"][0]  # type: ignore[no-any-return]


def some_players(client: TestClient, count: int) -> list[dict[str, object]]:
    body = client.get("/api/v1/players", params={"limit": count}).json()
    return body["items"]  # type: ignore[no-any-return]


class TestShortlistEndpoints:
    def test_every_route_requires_an_account(self, client: TestClient) -> None:
        client.cookies.clear()
        assert client.get("/api/v1/shortlists").status_code == 401
        assert client.post("/api/v1/shortlists", json={"name": "x"}).status_code == 401
        assert client.get("/api/v1/shortlists/1").status_code == 401
        assert client.delete("/api/v1/shortlists/1").status_code == 401
        assert client.get("/api/v1/shortlists/1/export.csv").status_code == 401

    def test_create_then_read_back(self, signed_in: TestClient) -> None:
        created = signed_in.post(
            "/api/v1/shortlists", json={"name": "Left backs", "description": "Under 23"}
        )
        assert created.status_code == 201
        shortlist_id = created.json()["shortlist_id"]

        listed = signed_in.get("/api/v1/shortlists").json()
        assert [s["shortlist_id"] for s in listed] == [shortlist_id]
        assert listed[0]["entry_count"] == 0

    def test_a_duplicate_name_is_a_conflict(self, signed_in: TestClient) -> None:
        signed_in.post("/api/v1/shortlists", json={"name": "Targets"})
        again = signed_in.post("/api/v1/shortlists", json={"name": "Targets"})
        assert again.status_code == 409

    def test_saving_a_player_and_reading_the_list(self, signed_in: TestClient) -> None:
        player = a_player(signed_in)
        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": "Targets"}).json()[
            "shortlist_id"
        ]

        added = signed_in.post(
            f"/api/v1/shortlists/{shortlist_id}/entries",
            json={"player_id": player["player_id"], "note": "Seen twice"},
        )
        assert added.status_code == 201

        detail = signed_in.get(f"/api/v1/shortlists/{shortlist_id}").json()
        assert detail["entry_count"] == 1
        entry = detail["entries"][0]
        assert entry["player"]["name"] == player["name"]
        assert entry["note"] == "Seen twice"
        assert entry["unavailable_reason"] is None

    def test_saving_an_unknown_player_is_refused(self, signed_in: TestClient) -> None:
        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": "Targets"}).json()[
            "shortlist_id"
        ]
        response = signed_in.post(
            f"/api/v1/shortlists/{shortlist_id}/entries", json={"player_id": "not-a-player"}
        )
        assert response.status_code == 404

    def test_a_removed_player_is_gone(self, signed_in: TestClient) -> None:
        player = a_player(signed_in)
        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": "Targets"}).json()[
            "shortlist_id"
        ]
        signed_in.post(
            f"/api/v1/shortlists/{shortlist_id}/entries", json={"player_id": player["player_id"]}
        )

        removed = signed_in.delete(
            f"/api/v1/shortlists/{shortlist_id}/entries/{player['player_id']}"
        )
        assert removed.status_code == 204
        assert signed_in.get(f"/api/v1/shortlists/{shortlist_id}").json()["entries"] == []

    def test_another_account_gets_404_not_403(self, client: TestClient) -> None:
        """403 would confirm the shortlist exists. 404 says nothing."""
        first = f"owner-{secrets.token_hex(6)}@example.test"
        second = f"other-{secrets.token_hex(6)}@example.test"

        client.post("/api/v1/auth/register", json={"email": first, "password": PASSWORD})
        shortlist_id = client.post("/api/v1/shortlists", json={"name": "Private"}).json()[
            "shortlist_id"
        ]
        client.post("/api/v1/auth/logout")

        client.post("/api/v1/auth/register", json={"email": second, "password": PASSWORD})
        assert client.get(f"/api/v1/shortlists/{shortlist_id}").status_code == 404
        assert client.delete(f"/api/v1/shortlists/{shortlist_id}").status_code == 404
        assert client.get(f"/api/v1/shortlists/{shortlist_id}/export.csv").status_code == 404
        assert client.get("/api/v1/shortlists").json() == []

        from app.core.database import get_engine

        with Session(get_engine()) as cleanup:
            for email in (first, second):
                account = cleanup.scalar(select(UserAccount).where(UserAccount.email == email))
                if account is not None:
                    cleanup.delete(account)
            cleanup.commit()


class TestCompare:
    def test_at_most_five_players(self, signed_in: TestClient) -> None:
        players = some_players(signed_in, MAX_COMPARE + 1)
        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": "Compare"}).json()[
            "shortlist_id"
        ]
        for player in players:
            signed_in.post(
                f"/api/v1/shortlists/{shortlist_id}/entries",
                json={"player_id": player["player_id"]},
            )

        query = [("player", p["player_id"]) for p in players]
        response = signed_in.get(f"/api/v1/shortlists/{shortlist_id}/compare", params=query)
        assert response.status_code == 422

        response = signed_in.get(
            f"/api/v1/shortlists/{shortlist_id}/compare", params=query[:MAX_COMPARE]
        )
        assert response.status_code == 200
        assert len(response.json()["players"]) == MAX_COMPARE

    def test_a_player_not_on_the_list_cannot_be_compared(self, signed_in: TestClient) -> None:
        """Otherwise the endpoint is a way to assemble an arbitrary extract."""
        players = some_players(signed_in, 2)
        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": "Compare"}).json()[
            "shortlist_id"
        ]
        signed_in.post(
            f"/api/v1/shortlists/{shortlist_id}/entries",
            json={"player_id": players[0]["player_id"]},
        )

        response = signed_in.get(
            f"/api/v1/shortlists/{shortlist_id}/compare",
            params=[("player", players[1]["player_id"])],
        )
        assert response.status_code == 404

    def test_mixing_positions_carries_a_caveat(self, signed_in: TestClient) -> None:
        """Percentiles are computed within a position group, so the columns
        cannot simply be read across."""
        body = signed_in.get("/api/v1/players", params={"limit": 100}).json()
        by_position: dict[str, dict[str, object]] = {}
        for player in body["items"]:
            by_position.setdefault(player["position_group"], player)
        chosen = list(by_position.values())[:2]
        if len(chosen) < 2:
            pytest.skip("demo data has only one position group")

        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": "Mixed"}).json()[
            "shortlist_id"
        ]
        for player in chosen:
            signed_in.post(
                f"/api/v1/shortlists/{shortlist_id}/entries",
                json={"player_id": player["player_id"]},
            )

        response = signed_in.get(
            f"/api/v1/shortlists/{shortlist_id}/compare",
            params=[("player", p["player_id"]) for p in chosen],
        ).json()
        assert response["caveat"] is not None
        assert MIXED_POSITION_CAVEAT in response["caveat"]

    def test_one_position_and_competition_carries_no_caveat(self, signed_in: TestClient) -> None:
        body = signed_in.get("/api/v1/players", params={"limit": 100}).json()
        groups: dict[tuple[str, str], list[dict[str, object]]] = {}
        for player in body["items"]:
            groups.setdefault((player["position_group"], player["competition"]), []).append(player)
        pair = next((v for v in groups.values() if len(v) >= 2), None)
        assert pair is not None, "demo data should contain two comparable players"

        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": "Same"}).json()[
            "shortlist_id"
        ]
        for player in pair[:2]:
            signed_in.post(
                f"/api/v1/shortlists/{shortlist_id}/entries",
                json={"player_id": player["player_id"]},
            )

        response = signed_in.get(
            f"/api/v1/shortlists/{shortlist_id}/compare",
            params=[("player", p["player_id"]) for p in pair[:2]],
        ).json()
        assert response["caveat"] is None
        assert MIXED_COMPETITION_CAVEAT not in (response["caveat"] or "")


class TestExport:
    def _shortlist_with_a_player(self, api: TestClient, note: str | None = None) -> tuple[int, str]:
        player = a_player(api)
        shortlist_id = api.post("/api/v1/shortlists", json={"name": "Export me"}).json()[
            "shortlist_id"
        ]
        api.post(
            f"/api/v1/shortlists/{shortlist_id}/entries",
            json={"player_id": player["player_id"], "note": note},
        )
        return shortlist_id, str(player["name"])

    def test_the_csv_has_the_expected_columns(self, signed_in: TestClient) -> None:
        shortlist_id, name = self._shortlist_with_a_player(signed_in)
        response = signed_in.get(f"/api/v1/shortlists/{shortlist_id}/export.csv")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == EXPORT_COLUMNS
        assert rows[1][0] == name

    def test_the_csv_carries_no_underlying_statistics(self, signed_in: TestClient) -> None:
        """It records one person's selection, not an extract of the data."""
        assert not any(
            column.endswith("_per90") or column.startswith("percentile")
            for column in EXPORT_COLUMNS
        )

    def test_a_note_containing_a_comma_and_quotes_does_not_shift_the_columns(
        self, signed_in: TestClient
    ) -> None:
        awkward = 'Quick, strong; said "worth a look"\nand two-footed'
        shortlist_id, _ = self._shortlist_with_a_player(signed_in, note=awkward)

        response = signed_in.get(f"/api/v1/shortlists/{shortlist_id}/export.csv")
        rows = list(csv.reader(io.StringIO(response.text)))
        assert len(rows) == 2
        assert len(rows[1]) == len(EXPORT_COLUMNS)
        assert rows[1][EXPORT_COLUMNS.index("note")] == awkward

    def test_the_filename_cannot_inject_a_header(self, signed_in: TestClient) -> None:
        """The shortlist name is user-controlled text going into a response
        header."""
        hostile = 'evil"; x=y'
        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": hostile}).json()[
            "shortlist_id"
        ]
        response = signed_in.get(f"/api/v1/shortlists/{shortlist_id}/export.csv")

        disposition = response.headers["content-disposition"]
        # Quote, semicolon and equals each became a dash, and the run collapsed.
        assert disposition == 'attachment; filename="evil---x-y.csv"'
        # The only quotes left are the two the header itself needs, so the name
        # cannot close the filename and append a directive of its own.
        assert disposition.count('"') == 2
        assert ";" not in disposition[len("attachment; ") :]

    def test_an_empty_shortlist_exports_a_header_only(self, signed_in: TestClient) -> None:
        shortlist_id = signed_in.post("/api/v1/shortlists", json={"name": "Empty"}).json()[
            "shortlist_id"
        ]
        response = signed_in.get(f"/api/v1/shortlists/{shortlist_id}/export.csv")
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows == [EXPORT_COLUMNS]


class TestUnresolvablePlayers:
    def test_a_saved_player_who_left_the_data_is_shown_not_dropped(
        self, db_session: Session
    ) -> None:
        """Silently deleting someone's saved player is worse than a gap."""
        from app.api.v1.shortlists import to_entry
        from app.services.analytics_service import get_analytics_view

        user = make_user(db_session)
        shortlist = create_shortlist(db_session, user_id=user.user_id, name="Targets")
        entry = add_entry(
            db_session,
            user_id=user.user_id,
            shortlist_id=shortlist.shortlist_id,
            player_key="a-key-that-no-longer-resolves",
            player_name="Someone Who Left",
        )

        out = to_entry(entry, get_analytics_view())
        assert out.player is None
        assert out.saved_as == "Someone Who Left"
        assert out.unavailable_reason is not None
