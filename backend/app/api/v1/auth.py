"""Authentication endpoints and the dependencies that protect routes.

The session token travels in an httpOnly cookie, so no JavaScript on the page
can read it — an XSS bug then cannot exfiltrate a session. `SameSite=Lax` stops
the cookie riding along with cross-site form posts, and `Secure` is set whenever
the deployment is not local http.

Public reading stays public (spec section 19): browsing, search, profiles and
similarity need no account. Only the things that belong to a person — shortlists,
notes, saved searches — require one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, SettingsDep
from app.core.config import Settings
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
    create_session,
    register_user,
    resolve_session,
    revoke_all_sessions,
    revoke_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SESSION_COOKIE = "fri_session"


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
        )
    return user


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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (WeakPassword, InvalidEmail) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AuthError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    issued = create_session(db, user)
    db.commit()
    set_session_cookie(response, issued.token, settings)
    return to_user(user)


@router.post("/login", response_model=UserOut)
def login(
    request: LoginRequest, response: Response, db: SessionDep, settings: SettingsDep
) -> UserOut:
    """Sign in. Every failure gives the same answer."""
    try:
        user = authenticate(db, email=request.email, password=request.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    issued = create_session(db, user)
    db.commit()
    set_session_cookie(response, issued.token, settings)
    return to_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
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
    clear_session_cookie(response, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """The signed-in user."""
    return to_user(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(
    request: ChangePasswordRequest,
    response: Response,
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except WeakPassword as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    db.commit()
    clear_session_cookie(response, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-everywhere", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(
    response: Response, user: CurrentUser, db: SessionDep, settings: SettingsDep
) -> Response:
    """End every session for this account, on every device."""
    revoke_all_sessions(db, user.user_id)
    db.commit()
    clear_session_cookie(response, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
