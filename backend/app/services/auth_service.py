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
from app.models.accounts import UserAccount, UserSession

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


class AuthError(Exception):
    """Authentication or registration could not proceed."""


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    def __init__(self) -> None:
        super().__init__(GENERIC_SIGNIN_ERROR)


class WeakPassword(AuthError):
    pass


class InvalidEmail(AuthError):
    pass


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
        raise WeakPassword(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")


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
