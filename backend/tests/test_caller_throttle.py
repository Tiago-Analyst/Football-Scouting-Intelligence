"""One password tried against many accounts, from one visitor.

The per-address count cannot see it: every address gets a single failure. The
frontend therefore forwards the visitor's address with a shared secret, and the
backend keeps a second count per caller. Without the secret the header is
noise, because anyone can send one.
"""

from __future__ import annotations

import secrets

from fastapi.testclient import TestClient

from app.services.auth_service import FREE_CALLER_ATTEMPTS, hash_caller, hash_email
from tests.conftest import build_client, build_settings

TOKEN = "a-test-secret-that-is-long-enough"
PASSWORD = "correct horse battery staple"
WRONG = {"password": "not the right password"}


def caller(address: str, token: str = TOKEN) -> dict[str, str]:
    return {"X-Caller-Address": address, "X-Caller-Token": token}


def fresh_address() -> str:
    return f"203.0.113.{secrets.randbelow(250) + 1}-{secrets.token_hex(4)}"


def stranger() -> str:
    return f"nobody-{secrets.token_hex(6)}@example.test"


def sign_in(api: TestClient, email: str, headers: dict[str, str], password: str | None = None):
    body = {"email": email, "password": password or WRONG["password"]}
    return api.post("/api/v1/auth/login", json=body, headers=headers)


def spray(api: TestClient, headers: dict[str, str], times: int) -> list[int]:
    return [sign_in(api, stranger(), headers).status_code for _ in range(times)]


def test_one_caller_spraying_many_addresses_is_slowed_down() -> None:
    with build_client(build_settings(caller_token=TOKEN)) as api:
        mine = caller(fresh_address())
        # Every address is new, so no per-address count ever passes its free five.
        # The free attempts, and one more that is still answered and so counted.
        assert set(spray(api, mine, FREE_CALLER_ATTEMPTS + 1)) == {401}

        refused = sign_in(api, stranger(), mine)
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "auth_too_many_attempts"
        assert int(refused.headers["retry-after"]) > 0

        # Somebody else is not held up by it.
        assert sign_in(api, stranger(), caller(fresh_address())).status_code == 401


def test_without_the_secret_configured_the_header_changes_nothing() -> None:
    with build_client(build_settings()) as api:
        mine = caller(fresh_address())
        assert set(spray(api, mine, FREE_CALLER_ATTEMPTS + 3)) == {401}


def test_a_wrong_secret_is_ignored() -> None:
    with build_client(build_settings(caller_token=TOKEN)) as api:
        forged = caller(fresh_address(), token="guess")
        assert set(spray(api, forged, FREE_CALLER_ATTEMPTS + 3)) == {401}


def test_a_missing_or_absurd_address_is_ignored() -> None:
    with build_client(build_settings(caller_token=TOKEN)) as api:
        for headers in ({}, {"X-Caller-Token": TOKEN}, caller("9" * 200)):
            assert set(spray(api, headers, FREE_CALLER_ATTEMPTS + 2)) == {401}


def test_a_success_does_not_reset_the_callers_count() -> None:
    """Otherwise one account of its own lets an attacker interleave a success
    between guesses and never reach the wait."""
    with build_client(build_settings(caller_token=TOKEN)) as api:
        email = f"mine-{secrets.token_hex(6)}@example.test"
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        api.post("/api/v1/auth/logout")

        mine = caller(fresh_address())
        assert set(spray(api, mine, FREE_CALLER_ATTEMPTS)) == {401}
        assert sign_in(api, email, mine, PASSWORD).status_code == 200
        api.post("/api/v1/auth/logout")

        # Had the success cleared the count, this would be the 1st failure again.
        assert sign_in(api, stranger(), mine).status_code == 401
        assert sign_in(api, stranger(), mine).status_code == 429


def test_the_stored_key_is_keyed_and_never_an_emails_hash() -> None:
    address = "203.0.113.7"
    assert hash_caller(address, TOKEN) == hash_caller(address, TOKEN)
    assert hash_caller(address, TOKEN) != hash_caller(address, TOKEN + "x")
    assert hash_caller(address, TOKEN) != hash_email(address)
    assert len(hash_caller(address, TOKEN)) == 64
