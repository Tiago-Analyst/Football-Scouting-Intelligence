"""Authentication: password hashing, sessions, sign-in and sign-out.

No cryptography is written here. Argon2id comes from `argon2-cffi`, the
reference implementation, and randomness comes from `secrets` (spec section 19:
do not build custom password cryptography).

Several behaviours below look like small details and are the whole point:

- **Sign-in verifies a hash even when the email is unknown.** Otherwise the
  response is measurably faster for an address that does not exist, and the
  login form becomes a way to enumerate who has an account.
- **Every sign-in failure returns the same message.** "No such user" and "wrong
  password" are the same answer to the person signing in and two different
  answers to an attacker.
- **The session token is returned exactly once.** Only its hash is stored, so it
  cannot be recovered afterwards - by us or by anyone reading the table.
- **Guesses are rate-limited per address.** Everything above makes one guess
  expensive and uninformative; none of it limits how many arrive. See
  `login_retry_after`.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.accounts import LoginAttempt, UserAccount, UserSession

log = get_logger(__name__)

#: Argon2id with the library's defaults, which track current guidance. Kept
#: explicit so a future change is a visible decision rather than a silent
#: dependency upgrade.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

#: A dummy hash to verify against when the email is unknown, so the work done
#: is the same either way and the timing does not leak account existence.
_DUMMY_HASH = _hasher.hash("timing-equalisation-placeholder")

SESSION_TOKEN_BYTES = 32
SESSION_LIFETIME = timedelta(days=14)
#: A session older than this without activity is treated as abandoned.
SESSION_IDLE_TIMEOUT = timedelta(days=7)

#: NIST guidance: length is what matters. No composition rules, which push
#: people towards predictable substitutions without adding real entropy.
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 512

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

GENERIC_SIGNIN_ERROR = "Email or password is incorrect."

#: Failed sign-ins older than this are not counted and may be deleted.
FAILED_LOGIN_WINDOW = timedelta(minutes=15)

#: Failures allowed in that window before any wait is imposed. A person
#: mistyping a password they do know should never meet this.
FREE_LOGIN_ATTEMPTS = 5

#: The wait imposed before the next attempt, by how far past the free ones the
#: caller is: the 6th failure buys 5 seconds, the 7th fifteen, then a minute,
#: then two - and two is the ceiling.
#:
#: WHY THERE IS A CEILING, AND WHY IT IS LOW
#:
#: Anyone can submit a wrong password for somebody else's address, so a
#: throttle keyed on the address is also a way to make that person wait. A
#: lockout would make it a way to deny them their account entirely, which
#: trades a brute-force risk for a denial-of-service one. Two minutes keeps
#: the owner's worst case short while still cutting an attacker from thousands
#: of guesses an hour to about thirty.
LOGIN_BACKOFF_SECONDS = (5, 15, 60, 120)


class AuthError(Exception):
    """Authentication or registration could not proceed.

    Carries a CODE as well as the sentence. The sentence is English and the
    form that shows it may be rendering in another language, so the interface
    needs to be able to say this itself rather than print what arrived. The
    sentence stays for any caller already reading it, and `values` carries the
    numbers a translated sentence would need.
    """

    code = "auth_failed"

    def __init__(self, message: str, *, values: dict[str, int] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.values = values or {}


class EmailAlreadyRegistered(AuthError):
    code = "auth_email_taken"


class InvalidCredentials(AuthError):
    code = "auth_invalid_credentials"

    def __init__(self) -> None:
        super().__init__(GENERIC_SIGNIN_ERROR)


class WeakPassword(AuthError):
    code = "auth_password_length"


class PasswordTooShort(WeakPassword):
    code = "auth_password_too_short"


class PasswordTooLong(WeakPassword):
    code = "auth_password_too_long"


class InvalidEmail(AuthError):
    code = "auth_email_invalid"


@dataclass(frozen=True)
class IssuedSession:
    """A newly created session.

    `token` is present only here. It is never stored and cannot be recovered.
    """

    token: str
    expires_at: datetime
    user: UserAccount


def normalise_email(email: str) -> str:
    """Trim and lowercase, so one person cannot register twice by changing case."""
    return email.strip().lower()


def validate_email(email: str) -> str:
    normalised = normalise_email(email)
    if not _EMAIL_PATTERN.match(normalised) or len(normalised) > 320:
        raise InvalidEmail("Enter a valid email address.")
    return normalised


def validate_password(password: str) -> None:
    """Length only.

    Composition rules ("one uppercase, one symbol") measurably reduce password
    quality by steering people to predictable patterns. The upper bound exists
    because Argon2 hashes whatever it is given, and an unbounded input is a
    denial-of-service vector.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordTooShort(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            values={"length": MIN_PASSWORD_LENGTH},
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordTooLong(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters.",
            values={"length": MAX_PASSWORD_LENGTH},
        )


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    """SHA-256 of a session token.

    Appropriate precisely because the token is high-entropy random: there is no
    guessable secret for a slow hash to protect.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def register_user(
    session: Session, *, email: str, password: str, display_name: str | None = None
) -> UserAccount:
    """Create an account. Raises rather than returning a partial result."""
    normalised = validate_email(email)
    validate_password(password)

    existing = session.scalar(select(UserAccount).where(UserAccount.email == normalised))
    if existing is not None:
        raise EmailAlreadyRegistered("An account with that email already exists.")

    user = UserAccount(
        email=normalised,
        password_hash=hash_password(password),
        display_name=(display_name or "").strip() or None,
    )
    session.add(user)
    session.flush()
    log.info("user_registered", user_id=user.user_id)
    return user


def authenticate(session: Session, *, email: str, password: str) -> UserAccount:
    """Verify credentials, or raise `InvalidCredentials`.

    The same exception and message for every failure mode, and the same amount
    of work done in each: an unknown email still costs one Argon2 verification.
    """
    normalised = normalise_email(email)
    user = session.scalar(select(UserAccount).where(UserAccount.email == normalised))

    if user is None:
        # Deliberate: equalise timing so the form cannot enumerate accounts.
        verify_password(_DUMMY_HASH, password)
        raise InvalidCredentials

    if not verify_password(user.password_hash, password):
        raise InvalidCredentials

    if not user.is_active:
        raise InvalidCredentials

    # Argon2 parameters change over time; rehash transparently on sign-in so
    # stored hashes keep up without asking anyone to reset a password.
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        log.info("password_rehashed", user_id=user.user_id)

    user.last_login_at = datetime.now(UTC)
    session.flush()
    return user


def hash_email(email: str) -> str:
    """SHA-256 of a normalised address, for the throttle's bookkeeping.

    The attempt table needs equality and nothing else, and storing addresses
    would accumulate a list of real ones - see `LoginAttempt`.
    """
    return hashlib.sha256(normalise_email(email).encode("utf-8")).hexdigest()


def login_retry_after(session: Session, email: str) -> int:
    """Seconds the caller must wait before this address may be tried again.

    Zero means go ahead. A positive number is a wait, not a lockout: it always
    expires, and every success clears the count behind it.

    Counted per address and not per account, so an address nobody has
    registered is throttled exactly like one that exists. Slowing down only
    real accounts would turn this into the account oracle that
    `GENERIC_SIGNIN_ERROR` and the dummy-hash verification exist to prevent.

    WHAT THIS DOES NOT COVER

    One password tried against many addresses. Each address keeps its own
    count, so spraying never meets this at all; the only brake on that is the
    process-wide limiter, which cannot tell callers apart. Stopping it needs a
    per-caller count, and the caller's address is not visible to this service -
    see `app.core.middleware.RateLimitMiddleware`.
    """
    since = datetime.now(UTC) - FAILED_LOGIN_WINDOW
    key = hash_email(email)

    recent = session.scalars(
        select(LoginAttempt)
        .where(LoginAttempt.email_hash == key, LoginAttempt.occurred_at > since)
        .order_by(LoginAttempt.occurred_at.desc())
    ).all()

    if len(recent) <= FREE_LOGIN_ATTEMPTS:
        return 0

    step = min(len(recent) - FREE_LOGIN_ATTEMPTS - 1, len(LOGIN_BACKOFF_SECONDS) - 1)
    required = timedelta(seconds=LOGIN_BACKOFF_SECONDS[step])
    waited = datetime.now(UTC) - recent[0].occurred_at
    if waited >= required:
        return 0
    # Rounded up, so a reported wait of 1 second is never a wait of 0.4 that
    # the next attempt still refuses.
    return max(1, -(-int((required - waited).total_seconds() * 1000) // 1000))


def record_failed_login(session: Session, email: str) -> None:
    """Count one failed attempt against an address."""
    session.add(LoginAttempt(email_hash=hash_email(email), occurred_at=datetime.now(UTC)))
    session.flush()


def clear_failed_logins(session: Session, email: str) -> int:
    """Forget an address's failures. Called on every successful sign-in.

    So the wait can only ever be reached by consecutive failures, and somebody
    who mistypes a password six times and then gets it right starts from zero.
    """
    records = session.scalars(
        select(LoginAttempt).where(LoginAttempt.email_hash == hash_email(email))
    ).all()
    for record in records:
        session.delete(record)
    session.flush()
    return len(records)


def purge_login_attempts(session: Session) -> int:
    """Delete failures too old to count. Nothing reads them after the window.

    Not load-bearing, and nothing calls it yet - exactly as nothing calls
    `purge_expired_sessions`. `login_retry_after` reads only the last window,
    so an unpurged row is ignored rather than wrong; the rows accumulate until
    something runs this, and that something does not exist.
    """
    cutoff = datetime.now(UTC) - FAILED_LOGIN_WINDOW
    records = session.scalars(select(LoginAttempt).where(LoginAttempt.occurred_at <= cutoff)).all()
    for record in records:
        session.delete(record)
    session.flush()
    return len(records)


def change_password(
    session: Session, user: UserAccount, *, current_password: str, new_password: str
) -> None:
    """Change a password, verifying the current one first."""
    if not verify_password(user.password_hash, current_password):
        raise InvalidCredentials
    validate_password(new_password)
    user.password_hash = hash_password(new_password)
    # Every other session is ended: a password change is the action someone
    # takes when they think a session is not theirs.
    revoke_all_sessions(session, user.user_id)
    session.flush()
    log.info("password_changed", user_id=user.user_id)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def create_session(session: Session, user: UserAccount) -> IssuedSession:
    """Issue a session and return its token once."""
    token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
    now = datetime.now(UTC)
    expires_at = now + SESSION_LIFETIME

    session.add(
        UserSession(
            user_id=user.user_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
    )
    session.flush()
    log.info("session_created", user_id=user.user_id)
    return IssuedSession(token=token, expires_at=expires_at, user=user)


def resolve_session(session: Session, token: str | None) -> UserAccount | None:
    """Return the signed-in user for a token, or None.

    None covers every failure identically - absent, unknown, expired, idle,
    revoked, or belonging to a deactivated account - because the caller's
    response should not differ between them.
    """
    if not token:
        return None

    record = session.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if record is None or record.revoked_at is not None:
        return None

    now = datetime.now(UTC)
    if record.expires_at <= now:
        return None
    if now - record.last_seen_at > SESSION_IDLE_TIMEOUT:
        return None

    user = session.get(UserAccount, record.user_id)
    if user is None or not user.is_active:
        return None

    # Sliding activity, written at most once a minute: updating on every request
    # would turn each authenticated read into a write.
    if now - record.last_seen_at > timedelta(minutes=1):
        record.last_seen_at = now
        session.flush()

    return user


def revoke_session(session: Session, token: str) -> bool:
    """End one session. Returns whether anything was ended."""
    record = session.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = datetime.now(UTC)
    session.flush()
    log.info("session_revoked", user_id=record.user_id)
    return True


def revoke_all_sessions(session: Session, user_id: int) -> int:
    """End every live session for a user. Returns how many."""
    now = datetime.now(UTC)
    records = session.scalars(
        select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    ).all()
    for record in records:
        record.revoked_at = now
    session.flush()
    return len(records)


def purge_expired_sessions(session: Session) -> int:
    """Delete sessions that expired long enough ago to be of no interest."""
    cutoff = datetime.now(UTC) - SESSION_LIFETIME
    records = session.scalars(select(UserSession).where(UserSession.expires_at < cutoff)).all()
    for record in records:
        session.delete(record)
    session.flush()
    return len(records)
