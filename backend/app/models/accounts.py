"""User accounts and sessions.

Two decisions here are security-relevant enough to state plainly.

**The session table stores a hash of the token, never the token.** A read-only
leak of this table — a backup, a log, an errant query — would otherwise hand
someone every live session. The stored value cannot be replayed.

**Email is stored already normalised.** Uniqueness is enforced by the database,
and a case-insensitive collation would vary by deployment, so normalisation
happens before the value is written and the constraint is a plain unique index.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserAccount(Base):
    """A person who can sign in."""

    __tablename__ = "user_account"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    #: Lowercased and trimmed before storage. See `normalise_email`.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    #: Argon2id encoded hash. Carries its own salt and parameters, so the
    #: algorithm can be re-tuned later without a migration.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))

    #: Deactivation rather than deletion: a removed account would cascade away
    #: shortlists the user may want back.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("email", name="uq_user_account_email"),
        CheckConstraint("email = lower(email)", name="email_is_normalised"),
        CheckConstraint("length(email) >= 3", name="email_plausible"),
    )


class UserSession(Base):
    """One signed-in session.

    Opaque server-side sessions rather than JWTs, chosen deliberately: signing
    out has to actually end a session. A stateless token cannot be revoked
    without a denylist, and a denylist is a session table with extra steps.
    """

    __tablename__ = "user_session"

    session_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_account.user_id", ondelete="CASCADE"), nullable=False
    )

    #: SHA-256 of the session token. A fast hash is correct here and argon2
    #: would be wrong: the token is already 256 bits of randomness, so there is
    #: no low-entropy secret to slow an attacker down against, and argon2 on
    #: every authenticated request would cost far more than it protects.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: Set when the user signs out. Kept rather than deleted so "this session
    #: ended" stays distinguishable from "this session never existed".
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_user_session_token"),
        CheckConstraint("expires_at > created_at", name="session_expiry_after_creation"),
        Index("ix_user_session_user", "user_id"),
        Index("ix_user_session_expiry", "expires_at"),
    )
