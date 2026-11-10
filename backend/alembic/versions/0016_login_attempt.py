"""Count failed sign-ins, so guesses can be rationed.

Revision ID: 0016_login_attempt
Revises: 0015_quality_detail_message
Create Date: 2026-11-10

WHY
===

Everything already in place makes ONE password guess expensive and
uninformative: Argon2id, a single generic failure message, and a dummy-hash
verification so an unknown address takes as long as a known one. Nothing
limited how MANY guesses arrived.

The rate limiter in `app.core.middleware` cannot do it. It keys on the peer of
the TCP connection, uvicorn runs without `--proxy-headers`, and the browser
never reaches this service directly - so in production the key is the
frontend's platform and the limit is one bucket shared by every visitor. It is
an abuse brake on callers who find the API, not a per-caller one, and it says
so about itself.

So the count lives here, keyed on the address attempted.

WHY A TABLE AND NOT A COUNTER IN MEMORY
=======================================

In-process state resets on every deploy and multiplies by the number of
workers, which is the limitation the existing limiter carries. A throttle that
forgets its count whenever the service restarts is a throttle an attacker can
clear by waiting for a deploy.

WHY THE ADDRESS IS HASHED
=========================

The throttle needs equality and nothing else. Storing the addresses would
accumulate a list of real email addresses - most of them belonging to people
with no account here, because a failed sign-in is often a typo or somebody
else's address - and the table would become something worth stealing. SHA-256
is right for the same reason it is right for session tokens: no low-entropy
secret to protect, and the value is never displayed.

WHY A ROW PER ATTEMPT RATHER THAN A COUNT PER ADDRESS
=====================================================

Because the wait depends on WHEN the last failure was, not only on how many
there have been, and a single counter cannot answer that without also storing
the timestamp - at which point the only thing it saves is the rows, which the
window purges anyway.

WHY THERE IS NO FOREIGN KEY
===========================

Most of these rows name no account. A constraint would force the opposite
behaviour - recording only real accounts - and that would make the throttle an
account oracle: being slowed down would tell an attacker the address exists.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0016_login_attempt"
down_revision: str | None = "0015_quality_detail_message"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "login_attempt",
        sa.Column("attempt_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    # The throttle's only query: this address, since a moment. Both columns,
    # in this order, so the window is an index range rather than a filter over
    # every failure ever recorded.
    op.create_index(
        "ix_login_attempt_email_time",
        "login_attempt",
        ["email_hash", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempt_email_time", table_name="login_attempt")
    op.drop_table("login_attempt")
