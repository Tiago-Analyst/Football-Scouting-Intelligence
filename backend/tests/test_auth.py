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

from app.models.accounts import LoginAttempt, UserAccount, UserSession
from app.services.auth_service import (
    FAILED_LOGIN_WINDOW,
    FREE_LOGIN_ATTEMPTS,
    GENERIC_SIGNIN_ERROR,
    LOGIN_BACKOFF_SECONDS,
    MIN_PASSWORD_LENGTH,
    SESSION_IDLE_TIMEOUT,
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidEmail,
    WeakPassword,
    authenticate,
    change_password,
    clear_failed_logins,
    create_session,
    delete_account,
    hash_email,
    hash_password,
    hash_token,
    login_retry_after,
    normalise_email,
    purge_expired_sessions,
    purge_login_attempts,
    record_failed_login,
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


class TestErasingAnAccount:
    """The most irreversible operation here, and the one that must not slip.

    Everything else in this file can be undone by signing in again. This
    cannot be undone at all, which changes what the tests have to prove: not
    only that it works, but that it cannot be made to work on somebody else,
    and that it refuses when it should rather than erasing on a technicality.
    """

    @staticmethod
    def _email() -> str:
        import secrets

        return f"erase-{secrets.token_hex(6)}@example.test"

    def test_it_takes_the_account_and_everything_in_it(self, db_session: Session) -> None:
        from app.models.shortlists import Shortlist

        user = make_user(db_session, email=self._email())
        user_id = user.user_id
        db_session.add(Shortlist(user_id=user_id, name="gone with it"))
        create_session(db_session, user)
        db_session.flush()

        delete_account(db_session, user, password=PASSWORD)

        assert db_session.get(UserAccount, user_id) is None
        assert db_session.scalars(select(Shortlist).where(Shortlist.user_id == user_id)).all() == []
        assert (
            db_session.scalars(select(UserSession).where(UserSession.user_id == user_id)).all()
            == []
        )

    def test_a_wrong_password_erases_nothing(self, db_session: Session) -> None:
        """The refusal has to leave the account exactly where it was.

        An erasure that half-happens is worse than one that does not happen.
        """
        user = make_user(db_session, email=self._email())
        user_id = user.user_id

        with pytest.raises(InvalidCredentials):
            delete_account(db_session, user, password="not the right password")

        assert db_session.get(UserAccount, user_id) is not None

    def test_it_forgets_the_throttle_count_for_that_address(self, db_session: Session) -> None:
        """The count names an address and has no foreign key to cascade through.

        Left behind, it would start a fresh registration at the same address
        inside the wait earned by whoever held it before.
        """
        email = self._email()
        user = make_user(db_session, email=email)
        for _ in range(FREE_LOGIN_ATTEMPTS + 2):
            record_failed_login(db_session, email)
        assert login_retry_after(db_session, email) > 0

        delete_account(db_session, user, password=PASSWORD)

        assert login_retry_after(db_session, email) == 0

    def test_it_reaches_no_other_account(self, db_session: Session) -> None:
        """The property the whole design rests on.

        The endpoint takes no id, no email and no argument naming an account -
        the caller IS the account - so this asserts what that buys: a deletion
        leaves every other account, and everything in it, untouched.
        """
        from app.models.shortlists import Shortlist

        mine = make_user(db_session, email=self._email())
        theirs = make_user(db_session, email=self._email())
        theirs_id = theirs.user_id
        db_session.add(Shortlist(user_id=theirs_id, name="not yours to erase"))
        create_session(db_session, theirs)
        db_session.flush()

        delete_account(db_session, mine, password=PASSWORD)

        assert db_session.get(UserAccount, theirs_id) is not None
        assert (
            len(db_session.scalars(select(Shortlist).where(Shortlist.user_id == theirs_id)).all())
            == 1
        )
        assert (
            len(
                db_session.scalars(
                    select(UserSession).where(UserSession.user_id == theirs_id)
                ).all()
            )
            == 1
        )


class TestTheGuessThrottle:
    """How many guesses arrive, which nothing else here limited.

    Argon2, one generic message and a dummy-hash verification make a single
    guess expensive and uninformative. None of them is a limit. The only limit
    the service had was `RateLimitMiddleware`, which keys on the peer of the
    TCP connection - the frontend's platform in production - and is therefore
    one bucket for every visitor rather than a per-caller brake.
    """

    @staticmethod
    def _email() -> str:
        import secrets

        return f"throttle-{secrets.token_hex(6)}@example.test"

    def _fail(self, session: Session, email: str, times: int) -> None:
        for _ in range(times):
            record_failed_login(session, email)

    def _attempts(self, session: Session, email: str) -> list[LoginAttempt]:
        return list(
            session.scalars(
                select(LoginAttempt).where(LoginAttempt.email_hash == hash_email(email))
            ).all()
        )

    def test_an_address_with_no_history_is_not_throttled(self, db_session: Session) -> None:
        assert login_retry_after(db_session, self._email()) == 0

    def test_the_free_attempts_are_free(self, db_session: Session) -> None:
        """A person mistyping a password they do know must not meet this."""
        email = self._email()
        self._fail(db_session, email, FREE_LOGIN_ATTEMPTS)
        assert login_retry_after(db_session, email) == 0

    def test_one_more_than_free_buys_a_wait(self, db_session: Session) -> None:
        email = self._email()
        self._fail(db_session, email, FREE_LOGIN_ATTEMPTS + 1)
        wait = login_retry_after(db_session, email)
        assert 0 < wait <= LOGIN_BACKOFF_SECONDS[0]

    def test_the_wait_grows_with_the_failures(self, db_session: Session) -> None:
        email = self._email()
        self._fail(db_session, email, FREE_LOGIN_ATTEMPTS + 1)
        first = login_retry_after(db_session, email)
        self._fail(db_session, email, 1)
        assert login_retry_after(db_session, email) > first

    def test_the_wait_is_capped(self, db_session: Session) -> None:
        """A wait that grows without bound is a lockout, and a lockout on an
        address anybody may submit is a way to deny somebody their own
        account."""
        email = self._email()
        self._fail(db_session, email, FREE_LOGIN_ATTEMPTS + 50)
        assert login_retry_after(db_session, email) <= LOGIN_BACKOFF_SECONDS[-1]

    def test_a_wait_expires_on_its_own(self, db_session: Session) -> None:
        """The difference between a throttle and a lockout, asserted."""
        email = self._email()
        self._fail(db_session, email, FREE_LOGIN_ATTEMPTS + 2)
        assert login_retry_after(db_session, email) > 0

        for attempt in self._attempts(db_session, email):
            attempt.occurred_at -= timedelta(seconds=LOGIN_BACKOFF_SECONDS[-1] + 1)
        db_session.flush()

        assert login_retry_after(db_session, email) == 0

    def test_failures_outside_the_window_are_not_counted(self, db_session: Session) -> None:
        email = self._email()
        self._fail(db_session, email, FREE_LOGIN_ATTEMPTS + 10)
        for attempt in self._attempts(db_session, email):
            attempt.occurred_at -= FAILED_LOGIN_WINDOW + timedelta(seconds=1)
        db_session.flush()
        assert login_retry_after(db_session, email) == 0

    def test_an_unregistered_address_is_throttled_identically(self, db_session: Session) -> None:
        """Otherwise the throttle is the account oracle that the generic
        message and the dummy-hash verification exist to prevent: being slowed
        down would tell an attacker the address is real."""
        registered = self._email()
        make_user(db_session, email=registered)
        stranger = self._email()

        self._fail(db_session, registered, FREE_LOGIN_ATTEMPTS + 1)
        self._fail(db_session, stranger, FREE_LOGIN_ATTEMPTS + 1)

        assert login_retry_after(db_session, stranger) == login_retry_after(db_session, registered)

    def test_a_success_clears_the_count(self, db_session: Session) -> None:
        email = self._email()
        self._fail(db_session, email, FREE_LOGIN_ATTEMPTS + 3)
        assert login_retry_after(db_session, email) > 0
        assert clear_failed_logins(db_session, email) == FREE_LOGIN_ATTEMPTS + 3
        assert login_retry_after(db_session, email) == 0

    def test_the_address_itself_is_never_stored(self, db_session: Session) -> None:
        """The table would otherwise accumulate real email addresses, most of
        them belonging to people with no account here."""
        email = self._email()
        self._fail(db_session, email, 1)
        rows = self._attempts(db_session, email)
        assert len(rows) == 1
        assert email not in rows[0].email_hash
        assert email.split("@")[0] not in rows[0].email_hash

    def test_the_count_is_not_held_in_the_process(self, db_session: Session) -> None:
        """In-process state resets on deploy and multiplies by worker, which is
        the limitation the existing rate limiter carries. A count an attacker
        can clear by waiting for a deploy is not a count."""
        email = self._email()
        self._fail(db_session, email, FREE_LOGIN_ATTEMPTS + 1)
        db_session.expire_all()
        assert login_retry_after(db_session, email) > 0

    def test_old_failures_are_purged(self, db_session: Session) -> None:
        email = self._email()
        self._fail(db_session, email, 3)
        for attempt in self._attempts(db_session, email):
            attempt.occurred_at -= FAILED_LOGIN_WINDOW + timedelta(minutes=1)
        db_session.flush()

        assert purge_login_attempts(db_session) >= 3
        assert self._attempts(db_session, email) == []


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

    def test_repeated_wrong_passwords_are_eventually_refused_with_a_wait(
        self, api: TestClient
    ) -> None:
        """The guess limit, from outside.

        Everything else about this endpoint makes one guess costly and
        uninformative. This is the part that makes the thousandth guess
        impossible, and it has to be visible from the wire: a refusal with no
        `Retry-After` leaves an ordinary client with nothing to wait for.
        """
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        api.post("/api/v1/auth/logout")

        wrong = {"email": email, "password": "not the right password"}
        for _ in range(FREE_LOGIN_ATTEMPTS + 1):
            assert api.post("/api/v1/auth/login", json=wrong).status_code == 401

        refused = api.post("/api/v1/auth/login", json=wrong)
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "auth_too_many_attempts"
        assert int(refused.headers["retry-after"]) > 0
        assert refused.json()["error"]["details"]["retry_after"] > 0

    def test_a_throttled_attempt_is_refused_without_checking_the_password(
        self, api: TestClient
    ) -> None:
        """The correct password is refused too, and that is the design.

        A throttle that still verifies is not rationing anything: Argon2 is
        deliberately expensive, and the hashes would go on being computed at
        whatever rate the guesses arrive. The cost is that somebody else's
        failed attempts can make the owner wait, which is why the wait is
        capped at two minutes and cleared by any success.
        """
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        api.post("/api/v1/auth/logout")

        wrong = {"email": email, "password": "not the right password"}
        for _ in range(FREE_LOGIN_ATTEMPTS + 1):
            api.post("/api/v1/auth/login", json=wrong)

        right = api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert right.status_code == 429
        assert api.get("/api/v1/auth/me").status_code == 401

    def test_the_wait_says_nothing_about_whether_the_address_exists(self, api: TestClient) -> None:
        """A registered address and a stranger are refused identically.

        The 429 differs from the 401 - it must, or the caller cannot know to
        come back - and it tells an attacker only that this address has been
        tried lately, which they know, having tried it.
        """
        wrong = "not the right password"
        registered = self._email()
        api.post("/api/v1/auth/register", json={"email": registered, "password": PASSWORD})
        api.post("/api/v1/auth/logout")
        stranger = self._email()

        for email in (registered, stranger):
            for _ in range(FREE_LOGIN_ATTEMPTS + 1):
                api.post("/api/v1/auth/login", json={"email": email, "password": wrong})

        first = api.post("/api/v1/auth/login", json={"email": registered, "password": wrong})
        second = api.post("/api/v1/auth/login", json={"email": stranger, "password": wrong})
        assert first.status_code == second.status_code == 429
        assert first.json()["error"]["code"] == second.json()["error"]["code"]
        assert first.json()["error"]["message"] == second.json()["error"]["message"]

    def test_a_refused_attempt_does_not_deepen_the_wait(self, api: TestClient) -> None:
        """Hammering a throttled address must not hold its owner out.

        A refusal is not recorded as a failure, so the count stops growing the
        moment the wait begins. Were it otherwise, anybody could keep somebody
        else's address at the two-minute ceiling indefinitely by submitting
        wrong passwords in a loop - which would turn a brute-force defence
        into the denial of service the ceiling exists to avoid.
        """
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        api.post("/api/v1/auth/logout")

        wrong = {"email": email, "password": "not the right password"}
        for _ in range(FREE_LOGIN_ATTEMPTS + 1):
            api.post("/api/v1/auth/login", json=wrong)

        first = api.post("/api/v1/auth/login", json=wrong)
        assert first.status_code == 429
        for _ in range(10):
            api.post("/api/v1/auth/login", json=wrong)
        last = api.post("/api/v1/auth/login", json=wrong)

        assert last.status_code == 429
        assert (
            last.json()["error"]["details"]["retry_after"]
            <= first.json()["error"]["details"]["retry_after"]
        )

    def test_signing_in_resets_the_count(self, api: TestClient) -> None:
        """Only consecutive failures accumulate, so a forgetful morning does
        not become a wait in the afternoon."""
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
        api.post("/api/v1/auth/logout")

        wrong = {"email": email, "password": "not the right password"}
        for _ in range(FREE_LOGIN_ATTEMPTS):
            assert api.post("/api/v1/auth/login", json=wrong).status_code == 401

        assert (
            api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code
            == 200
        )
        api.post("/api/v1/auth/logout")

        # The count is back to zero, so the same number of failures is free
        # again rather than landing on a wait.
        for _ in range(FREE_LOGIN_ATTEMPTS):
            assert api.post("/api/v1/auth/login", json=wrong).status_code == 401

    def test_deleting_the_account_needs_the_password(self, api: TestClient) -> None:
        """A session is enough to change this account's data, and deliberately
        not enough to erase it: a stolen cookie is recoverable and this is
        not."""
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})

        refused = api.request(
            "DELETE", "/api/v1/auth/me", json={"password": "not the right password"}
        )
        assert refused.status_code == 401
        assert refused.json()["error"]["message"] == GENERIC_SIGNIN_ERROR
        # Still signed in, still there.
        assert api.get("/api/v1/auth/me").status_code == 200

    def test_deleting_the_account_ends_it_everywhere(self, api: TestClient) -> None:
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})

        gone = api.request("DELETE", "/api/v1/auth/me", json={"password": PASSWORD})
        assert gone.status_code == 204
        # The cookie is cleared rather than left to be presented and refused.
        assert "fri_session=" in gone.headers.get("set-cookie", "")

        assert api.get("/api/v1/auth/me").status_code == 401
        # And the credentials no longer open anything.
        again = api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert again.status_code == 401

    def test_erasure_requires_a_session(self, api: TestClient) -> None:
        api.post("/api/v1/auth/logout")
        response = api.request("DELETE", "/api/v1/auth/me", json={"password": PASSWORD})
        assert response.status_code == 401

    def test_erasure_is_not_reachable_by_anything_that_prefetches(self, api: TestClient) -> None:
        """A link, a crawler or a prefetch must not be able to destroy an
        account. DELETE is the only verb that answers."""
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})

        assert api.post("/api/v1/auth/me", json={"password": PASSWORD}).status_code == 405
        # GET /me is the profile read, which must still work and erase nothing.
        assert api.get("/api/v1/auth/me").status_code == 200

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("POST", "/api/v1/auth/logout", None),
            ("POST", "/api/v1/auth/logout-everywhere", None),
            (
                "POST",
                "/api/v1/auth/change-password",
                {"current_password": PASSWORD, "new_password": "a-new-long-password"},
            ),
            ("DELETE", "/api/v1/auth/me", {"password": PASSWORD}),
        ],
    )
    def test_every_endpoint_that_ends_a_session_clears_the_cookie(
        self, api: TestClient, method: str, path: str, body: dict | None
    ) -> None:
        """All four said they cleared it and three of them did not.

        Each called `clear_session_cookie` against the INJECTED response and
        then returned a new `Response(204)`. FastAPI merges the injected
        response's headers only when the handler returns a model, so the
        `Set-Cookie` was dropped - and nothing noticed, because each of these
        also revokes the session server-side and the frontend clears its own
        copy on its own origin. The browser simply kept a cookie that was
        already dead.

        Parametrised rather than written four times, so the next endpoint that
        ends a session is one line here and cannot quietly skip the header.
        """
        email = self._email()
        api.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})

        response = api.request(method, path, json=body)
        assert response.status_code == 204, response.text

        set_cookie = response.headers.get("set-cookie", "")
        assert "fri_session=" in set_cookie, f"{path} did not clear the session cookie"
        # Cleared, not reissued: an expiry in the past is what removes it.
        assert "Max-Age=0" in set_cookie or "expires=" in set_cookie.lower()

    def test_me_requires_a_session(self, api: TestClient) -> None:
        assert api.get("/api/v1/auth/me").status_code == 401

    def test_logging_out_without_a_session_still_succeeds(self, api: TestClient) -> None:
        """Reporting an error would tell a caller which tokens are live."""
        assert api.post("/api/v1/auth/logout").status_code == 204

    def test_public_endpoints_remain_public(self, api: TestClient) -> None:
        """Section 19: browsing, search and profiles need no account."""
        for path in ("/api/v1/players?limit=1", "/api/v1/competitions", "/api/v1/roles"):
            assert api.get(path).status_code == 200
