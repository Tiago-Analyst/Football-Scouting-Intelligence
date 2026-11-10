"""Authentication endpoints and the dependencies that protect routes.

The session token travels in an httpOnly cookie, so no JavaScript on the page
can read it — an XSS bug then cannot exfiltrate a session. `SameSite=Lax` stops
the cookie riding along with cross-site form posts, and `Secure` is set whenever
the deployment is not local http.

Public reading stays public (spec section 19): browsing, search, profiles and
similarity need no account. Only the things that belong to a person — shortlists,
notes, saved searches — require one.

Sign-in is throttled per address, which is the one defence the rest of the
authentication code could not provide: hashing, a generic message and timing
equalisation all make a single guess costly and uninformative, and none of them
limit how many arrive. See `login_retry_after` for what it counts and what it
deliberately does not.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, SettingsDep
from app.core.config import Settings
from app.core.errors import AuthFailureError
from app.core.logging import get_logger
from app.models.accounts import UserAccount
from app.services.auth_service import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    SESSION_LIFETIME,
    AuthError,
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidEmail,
    WeakPassword,
    authenticate,
    change_password,
    clear_failed_logins,
    create_session,
    delete_account,
    login_retry_after,
    record_failed_login,
    register_user,
    resolve_session,
    revoke_all_sessions,
    revoke_session,
)

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SESSION_COOKIE = "fri_session"


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class DeleteAccountRequest(BaseModel):
    """Erasure asks for the password again, not for a confirmation checkbox.

    A session is enough to change this account's data and is deliberately not
    enough to erase it: a stolen cookie is recoverable and this is not.
    """

    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    """The signed-in user. Never carries the password hash."""

    user_id: int
    email: str
    display_name: str | None
    created_at: datetime
    last_login_at: datetime | None


def to_user(user: UserAccount) -> UserOut:
    return UserOut(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        # Unreadable from JavaScript: an XSS bug cannot steal the session.
        httponly=True,
        # Local development is plain http, where a Secure cookie would simply
        # never be sent. Anything deployed gets it.
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


def cleared_session_response(settings: Settings) -> Response:
    """A 204 that actually carries the `Set-Cookie` clearing the session.

    WHY THIS EXISTS RATHER THAN A CALL AT EACH SITE

    Four handlers wrote `clear_session_cookie(response, settings)` against the
    INJECTED `Response` and then returned a new `Response(status_code=204)`.
    FastAPI merges the injected response's headers only when the handler
    returns a model; return a Response object and it is used as it stands, so
    the `Set-Cookie` was dropped every time. Sign-out, change-password and
    sign-out-everywhere all did this, and nothing noticed, because each of them
    also revokes the session server-side - the browser kept a cookie that was
    already dead, and the frontend clears its own copy on its own origin.

    So the bug was invisible from the product and real in the API. Building the
    response first and setting the cookie on the thing actually returned is the
    shape that cannot come apart.
    """
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, settings)
    return response


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_optional_user(
    db: SessionDep,
    fri_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> UserAccount | None:
    """The signed-in user, or None. For routes that work either way."""
    return resolve_session(db, fri_session)


def get_current_user(
    user: Annotated[UserAccount | None, Depends(get_optional_user)],
) -> UserAccount:
    """The signed-in user, or 401. For routes that require an account."""
    if user is None:
        raise AuthFailureError(
            "Sign in to continue.",
            code="auth_required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return user


def _refused(exc: AuthError, status_code: int) -> AuthFailureError:
    """One of the service's refusals, as the envelope the interface reads.

    The code travels with the sentence so the form can say it in the reader's
    own language; `values` carries the numbers that sentence needs, such as
    the password length, rather than leaving them only inside the English.
    """
    return AuthFailureError(
        exc.message,
        code=exc.code,
        status_code=status_code,
        details=dict(exc.values) if exc.values else None,
    )


CurrentUser = Annotated[UserAccount, Depends(get_current_user)]
OptionalUser = Annotated[UserAccount | None, Depends(get_optional_user)]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    request: RegisterRequest, response: Response, db: SessionDep, settings: SettingsDep
) -> UserOut:
    """Create an account and sign in."""
    try:
        user = register_user(
            db,
            email=request.email,
            password=request.password,
            display_name=request.display_name,
        )
    except EmailAlreadyRegistered as exc:
        # Registration cannot avoid revealing that an address is taken - the
        # account has to be refused - so the message is at least honest. The
        # sign-in path, where enumeration actually matters, gives nothing away.
        raise _refused(exc, status.HTTP_409_CONFLICT) from exc
    except (WeakPassword, InvalidEmail) as exc:
        raise _refused(exc, 422) from exc
    except AuthError as exc:  # pragma: no cover - defensive
        raise _refused(exc, 400) from exc

    issued = create_session(db, user)
    db.commit()
    set_session_cookie(response, issued.token, settings)
    return to_user(user)


@router.post("/login", response_model=UserOut)
def login(
    request: LoginRequest, response: Response, db: SessionDep, settings: SettingsDep
) -> UserOut:
    """Sign in. Every failure gives the same answer, and they are counted.

    The order here is load-bearing. The wait is checked BEFORE the password is
    verified, because a throttle that still does the work it is meant to be
    rationing is not a throttle - Argon2 is deliberately expensive, and sixty
    refused guesses a minute would cost sixty hashes a minute all the same.

    A refusal for waiting and a refusal for a wrong password are different
    answers, and that is deliberate too: the wait has to be reported, or the
    caller cannot know to come back. It tells an attacker only that an address
    has been tried recently - which they know, having tried it - and never
    whether it exists, because an unregistered address is counted and refused
    exactly the same way.
    """
    retry_after = login_retry_after(db, request.email)
    if retry_after:
        # Not recorded as a failure. A refusal that counted itself would let
        # anybody hold somebody else's address at the ceiling indefinitely by
        # submitting wrong passwords in a loop, which is the denial of service
        # the ceiling exists to avoid. The wait is measured from the last real
        # failure and runs down whether or not anyone keeps knocking.
        log.warning("login_throttled", retry_after=retry_after, path="/api/v1/auth/login")
        raise AuthFailureError(
            "Too many sign-in attempts. Try again shortly.",
            code="auth_too_many_attempts",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )

    try:
        user = authenticate(db, email=request.email, password=request.password)
    except InvalidCredentials as exc:
        # Committed, because the request session is closed without one and the
        # count would otherwise be rolled back with the failure that caused it
        # - which is the whole of what this endpoint has to remember.
        record_failed_login(db, request.email)
        db.commit()
        raise _refused(exc, status.HTTP_401_UNAUTHORIZED) from exc

    # Only consecutive failures accumulate: somebody who mistypes six times and
    # then succeeds starts from zero, rather than meeting a wait tomorrow.
    clear_failed_logins(db, request.email)
    issued = create_session(db, user)
    db.commit()
    set_session_cookie(response, issued.token, settings)
    return to_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: SessionDep,
    settings: SettingsDep,
    fri_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Response:
    """Sign out.

    Always succeeds. Signing out of a session that has already ended is not an
    error, and reporting one would tell a caller which tokens are live.
    """
    if fri_session:
        revoke_session(db, fri_session)
        db.commit()
    return cleared_session_response(settings)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """The signed-in user."""
    return to_user(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(
    request: ChangePasswordRequest,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Change your password. Ends every session, including this one."""
    try:
        change_password(
            db,
            user,
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except InvalidCredentials as exc:
        raise _refused(exc, status.HTTP_401_UNAUTHORIZED) from exc
    except WeakPassword as exc:
        raise _refused(exc, 422) from exc

    db.commit()
    return cleared_session_response(settings)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_own_account(
    request: DeleteAccountRequest,
    user: CurrentUser,
    db: SessionDep,
    settings: SettingsDep,
) -> Response:
    """Erase this account and everything in it. There is no undo.

    DELETE on `/me`, because the resource being destroyed is the caller. No id
    is accepted anywhere: the account is whoever the session says it is, so
    there is no argument to substitute and no other account this can reach.

    Not reachable by anything that prefetches - a GET or a POST here is a 405.

    The password is required, and a wrong one answers exactly as a wrong
    password does at sign-in: `401` and the same sentence for every cause.
    """
    try:
        delete_account(db, user, password=request.password)
    except InvalidCredentials as exc:
        raise _refused(exc, status.HTTP_401_UNAUTHORIZED) from exc

    db.commit()
    # The session it was holding is gone with the row; this clears the cookie
    # that would otherwise be presented once more and refused.
    return cleared_session_response(settings)


@router.post("/logout-everywhere", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(user: CurrentUser, db: SessionDep, settings: SettingsDep) -> Response:
    """End every session for this account, on every device."""
    revoke_all_sessions(db, user.user_id)
    db.commit()
    return cleared_session_response(settings)
