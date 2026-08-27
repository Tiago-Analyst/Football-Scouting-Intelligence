"""Authentication.

Most of these assert a *refusal* or an *absence*. That is where authentication
bugs live: a system that lets the right person in is easy, and one that reliably
keeps everyone else out — and leaks nothing while doing it — is not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.accounts import UserAccount, UserSession
from app.services.auth_service import (
    GENERIC_SIGNIN_ERROR,
    MIN_PASSWORD_LENGTH,
    SESSION_IDLE_TIMEOUT,
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidEmail,
    WeakPassword,
    authenticate,
    change_password,
    create_session,
    hash_password,
    hash_token,
    normalise_email,
    purge_expired_sessions,
    register_user,
    resolve_session,
    revoke_all_sessions,
    revoke_session,
    validate_password,
    verify_password,
)

pytestmark = pytest.mark.integration

PASSWORD = "correct-horse-battery"
EMAIL = "player.scout@example.test"


def make_user(session: Session, email: str = EMAIL, password: str = PASSWORD) -> UserAccount:
    return register_user(session, email=email, password=password, display_name="Scout")


class TestPasswordHashing:
    def test_a_hash_does_not_contain_the_password(self) -> None:
        stored = hash_password(PASSWORD)
        assert PASSWORD not in stored

    def test_the_same_password_hashes_differently_each_time(self) -> None:
        """Per-hash salt. Identical hashes would reveal that two accounts share
        a password."""
        assert hash_password(PASSWORD) != hash_password(PASSWORD)

    def test_argon2id_is_used(self) -> None:
        assert hash_password(PASSWORD).startswith("$argon2id$")

    def test_the_right_password_verifies(self) -> None:
        assert verify_password(hash_password(PASSWORD), PASSWORD) is True

    def test_a_wrong_password_does_not(self) -> None:
        assert verify_password(hash_password(PASSWORD), "something else") is False

    def test_a_corrupt_hash_fails_rather_than_raising(self) -> None:
        """A damaged row must lock that account out, not crash the endpoint for
        everyone."""
        assert verify_password("not-a-hash", PASSWORD) is False


class TestPasswordPolicy:
    def test_a_short_password_is_rejected(self) -> None:
        with pytest.raises(WeakPassword):
            validate_password("a" * (MIN_PASSWORD_LENGTH - 1))

    def test_a_long_password_is_accepted(self) -> None:
        validate_password("a genuinely long passphrase with several words")

    def test_an_absurdly_long_password_is_rejected(self) -> None:
        """Argon2 hashes whatever it is given; an unbounded input is a denial-
        of-service vector."""
        with pytest.raises(WeakPassword):
            validate_password("a" * 100_000)

    def test_no_composition_rules_are_imposed(self) -> None:
        """Requiring symbols pushes people to predictable substitutions."""
        validate_password("all lowercase words no digits")


class TestEmailNormalisation:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [("  Scout@Example.test ", "scout@example.test"), ("A@B.CD", "a@b.cd")],
    )
    def test_email_is_trimmed_and_lowercased(self, given: str, expected: str) -> None:
        assert normalise_email(given) == expected

    def test_case_variants_cannot_register_twice(self, db_session: Session) -> None:
        make_user(db_session, email="Scout@Example.test")
        with pytest.raises(EmailAlreadyRegistered):
            make_user(db_session, email="scout@EXAMPLE.test")

    @pytest.mark.parametrize("bad", ["not-an-email", "@example.test", "a@b", "a b@c.test"])
    def test_malformed_emails_are_rejected(self, db_session: Session, bad: str) -> None:
        with pytest.raises(InvalidEmail):
            register_user(db_session, email=bad, password=PASSWORD)


class TestRegistration:
    def test_creates_an_account(self, db_session: Session) -> None:
        user = make_user(db_session)
        assert user.user_id is not None
        assert user.email == EMAIL
        assert user.is_active is True

    def test_the_password_is_never_stored_in_the_clear(self, db_session: Session) -> None:
        user = make_user(db_session)
        assert PASSWORD not in user.password_hash

    def test_a_duplicate_email_is_refused(self, db_session: Session) -> None:
        make_user(db_session)
        with pytest.raises(EmailAlreadyRegistered):
            make_user(db_session)

    def test_a_weak_password_is_refused(self, db_session: Session) -> None:
        with pytest.raises(WeakPassword):
            register_user(db_session, email=EMAIL, password="short")


class TestAuthentication:
    def test_correct_credentials_authenticate(self, db_session: Session) -> None:
        make_user(db_session)
        user = authenticate(db_session, email=EMAIL, password=PASSWORD)
        assert user.email == EMAIL

    def test_a_wrong_password_is_rejected(self, db_session: Session) -> None:
        make_user(db_session)
        with pytest.raises(InvalidCredentials):
            authenticate(db_session, email=EMAIL, password="wrong password here")

    def test_an_unknown_email_is_rejected(self, db_session: Session) -> None:
        with pytest.raises(InvalidCredentials):
            authenticate(db_session, email="nobody@example.test", password=PASSWORD)

    def test_both_failures_give_the_identical_message(self, db_session: Session) -> None:
        """ "No such user" and "wrong password" are the same answer to the person
        signing in and two different answers to an attacker."""
        make_user(db_session)
        with pytest.raises(InvalidCredentials) as wrong_password:
            authenticate(db_session, email=EMAIL, password="wrong password here")
        with pytest.raises(InvalidCredentials) as unknown_email:
            authenticate(db_session, email="nobody@example.test", password=PASSWORD)
        assert str(wrong_password.value) == str(unknown_email.value) == GENERIC_SIGNIN_ERROR

    def test_a_deactivated_account_cannot_sign_in(self, db_session: Session) -> None:
        user = make_user(db_session)
        user.is_active = False
        db_session.flush()
        with pytest.raises(InvalidCredentials):
            authenticate(db_session, email=EMAIL, password=PASSWORD)

    def test_signing_in_records_the_time(self, db_session: Session) -> None:
        make_user(db_session)
        user = authenticate(db_session, email=EMAIL, password=PASSWORD)
        assert user.last_login_at is not None

    def test_case_insensitive_sign_in(self, db_session: Session) -> None:
        make_user(db_session)
        assert authenticate(db_session, email=EMAIL.upper(), password=PASSWORD)


class TestSessions:
    def test_a_session_token_is_returned_once_and_never_stored(self, db_session: Session) -> None:
        """A read-only leak of the session table must not hand over live
        sessions."""
        user = make_user(db_session)
        issued = create_session(db_session, user)

        record = db_session.scalar(select(UserSession).where(UserSession.user_id == user.user_id))
        assert record is not None
        assert record.token_hash != issued.token
        assert record.token_hash == hash_token(issued.token)

    def test_a_valid_token_resolves_to_its_user(self, db_session: Session) -> None:
        user = make_user(db_session)
        issued = create_session(db_session, user)
        assert resolve_session(db_session, issued.token) is not None

    def test_tokens_are_unique(self, db_session: Session) -> None:
        user = make_user(db_session)
        first = create_session(db_session, user)
        second = create_session(db_session, user)
        assert first.token != second.token

    @pytest.mark.parametrize("token", [None, "", "not-a-real-token"])
    def test_absent_or_unknown_tokens_resolve_to_nobody(
        self, db_session: Session, token: str | None
    ) -> None:
        assert resolve_session(db_session, token) is None

    def test_an_expired_session_does_not_resolve(self, db_session: Session) -> None:
        user = make_user(db_session)
        issued = create_session(db_session, user)
        record = db_session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(issued.token))
        )
        assert record is not None
        # Both dates move: the schema enforces expires_at > created_at, so a
        # session cannot be given an expiry before it existed. Ageing the whole
        # row is also the honest simulation of an old session.
        record.created_at = datetime.now(UTC) - timedelta(days=30)
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db_session.flush()
        assert resolve_session(db_session, issued.token) is None

    def test_an_idle_session_does_not_resolve(self, db_session: Session) -> None:
        user = make_user(db_session)
        issued = create_session(db_session, user)
        record = db_session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(issued.token))
        )
        assert record is not None
        record.last_seen_at = datetime.now(UTC) - SESSION_IDLE_TIMEOUT - timedelta(hours=1)
        db_session.flush()
        assert resolve_session(db_session, issued.token) is None

    def test_signing_out_actually_ends_the_session(self, db_session: Session) -> None:
        """The reason for server-side sessions rather than a stateless token."""
        user = make_user(db_session)
        issued = create_session(db_session, user)
        assert revoke_session(db_session, issued.token) is True
        assert resolve_session(db_session, issued.token) is None

    def test_revoking_twice_is_harmless(self, db_session: Session) -> None:
        user = make_user(db_session)
        issued = create_session(db_session, user)
        revoke_session(db_session, issued.token)
        assert revoke_session(db_session, issued.token) is False

    def test_a_deactivated_account_invalidates_live_sessions(self, db_session: Session) -> None:
        user = make_user(db_session)
        issued = create_session(db_session, user)
        user.is_active = False
        db_session.flush()
        assert resolve_session(db_session, issued.token) is None

    def test_revoking_everywhere_ends_every_session(self, db_session: Session) -> None:
        user = make_user(db_session)
        tokens = [create_session(db_session, user).token for _ in range(3)]
        assert revoke_all_sessions(db_session, user.user_id) == 3
        assert all(resolve_session(db_session, token) is None for token in tokens)

    def test_purging_removes_only_long_expired_sessions(self, db_session: Session) -> None:
        user = make_user(db_session)
        live = create_session(db_session, user)
        stale = create_session(db_session, user)
        record = db_session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(stale.token))
        )
        assert record is not None
        record.created_at = datetime.now(UTC) - timedelta(days=400)
        record.expires_at = datetime.now(UTC) - timedelta(days=365)
        db_session.flush()

        purge_expired_sessions(db_session)
        assert resolve_session(db_session, live.token) is not None


class TestChangePassword:
    def test_the_current_password_must_be_correct(self, db_session: Session) -> None:
        user = make_user(db_session)
        with pytest.raises(InvalidCredentials):
            change_password(
                db_session, user, current_password="wrong one here", new_password="a new long one"
            )

    def test_the_new_password_works_afterwards(self, db_session: Session) -> None:
        user = make_user(db_session)
        change_password(
            db_session, user, current_password=PASSWORD, new_password="a brand new passphrase"
        )
        assert verify_password(user.password_hash, "a brand new passphrase")

    def test_the_old_password_stops_working(self, db_session: Session) -> None:
        user = make_user(db_session)
        change_password(
            db_session, user, current_password=PASSWORD, new_password="a brand new passphrase"
        )
        assert verify_password(user.password_hash, PASSWORD) is False

    def test_changing_a_password_ends_every_session(self, db_session: Session) -> None:
        """Someone changing their password usually believes a session is not
        theirs."""
        user = make_user(db_session)
        tokens = [create_session(db_session, user).token for _ in range(2)]
        change_password(
            db_session, user, current_password=PASSWORD, new_password="a brand new passphrase"
        )
        assert all(resolve_session(db_session, token) is None for token in tokens)

    def test_a_weak_new_password_is_refused(self, db_session: Session) -> None:
        user = make_user(db_session)
        with pytest.raises(WeakPassword):
            change_password(db_session, user, current_password=PASSWORD, new_password="short")


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@pytest.fixture
def api(client: TestClient) -> TestClient:
    return client


class TestAuthEndpoints:
    @staticmethod
    def _email() -> str:
        import secrets

        return f"user-{secrets.token_hex(6)}@example.test"

    def test_register_signs_the_user_in(self, api: TestClient) -> None:
        email = self._email()
        response = api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        assert response.status_code == 201
        assert response.json()["email"] == email
        assert api.get("/api/v1/auth/me").status_code == 200

    def test_the_session_cookie_is_httponly(self, api: TestClient) -> None:
        """Unreadable from JavaScript, so an XSS bug cannot steal a session."""
        response = api.post(
            "/api/v1/auth/register", json={"email": self._email(), "password": PASSWORD}
        )
        cookie = response.headers.get("set-cookie", "")
        assert "httponly" in cookie.lower()
        assert "samesite=lax" in cookie.lower()

    def test_a_response_never_contains_the_password_or_its_hash(self, api: TestClient) -> None:
        response = api.post(
            "/api/v1/auth/register", json={"email": self._email(), "password": PASSWORD}
        )
        assert PASSWORD not in response.text
        assert "argon2" not in response.text
        assert "password_hash" not in response.text

    def test_a_duplicate_registration_is_a_conflict(self, api: TestClient) -> None:
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        second = api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        assert second.status_code == 409

    def test_a_short_password_is_rejected_before_reaching_the_service(
        self, api: TestClient
    ) -> None:
        response = api.post(
            "/api/v1/auth/register", json={"email": self._email(), "password": "abc"}
        )
        assert response.status_code == 422

    def test_login_and_logout(self, api: TestClient) -> None:
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        api.post("/api/v1/auth/logout")
        assert api.get("/api/v1/auth/me").status_code == 401

        assert (
            api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code
            == 200
        )
        assert api.get("/api/v1/auth/me").status_code == 200

    def test_a_bad_login_is_a_401_with_a_generic_message(self, api: TestClient) -> None:
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        api.post("/api/v1/auth/logout")

        wrong = api.post("/api/v1/auth/login", json={"email": email, "password": "nope nope nope"})
        unknown = api.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.test", "password": "nope nope nope"},
        )
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]

    def test_me_requires_a_session(self, api: TestClient) -> None:
        assert api.get("/api/v1/auth/me").status_code == 401

    def test_logging_out_without_a_session_still_succeeds(self, api: TestClient) -> None:
        """Reporting an error would tell a caller which tokens are live."""
        assert api.post("/api/v1/auth/logout").status_code == 204

    def test_public_endpoints_remain_public(self, api: TestClient) -> None:
        """Section 19: browsing, search and profiles need no account."""
        for path in ("/api/v1/players?limit=1", "/api/v1/competitions", "/api/v1/roles"):
            assert api.get(path).status_code == 200
