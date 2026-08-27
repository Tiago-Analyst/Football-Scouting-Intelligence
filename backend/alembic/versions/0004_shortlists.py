"""shortlists

Adds the first user-owned data in the system: named lists of players, with the
note their owner wrote about each one. Both tables cascade — entries with their
list, lists with the account — so deleting a user leaves nothing behind.

Also renames one check constraint. `aerial_duels_won_within_aerial_duels`
produces a 64-character identifier once prefixed with its table name, one over
the PostgreSQL limit; SQLAlchemy truncated and hashed it while autogenerate kept
comparing against the full name, so every future migration reported a phantom
rename. The constraint itself is unchanged.

Revision ID: 0004_shortlists
Revises: 0003_accounts
Create Date: 2026-08-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_shortlists"
down_revision: str | None = "0003_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: What SQLAlchemy actually wrote, after truncating and hashing the tail.
TRUNCATED_CHECK = "ck_fact_player_season_stats_aerial_duels_won_within_aer_c6d9"
RENAMED_CHECK = "ck_fact_player_season_stats_aerial_duels_won_within_total"


def upgrade() -> None:
    op.create_table(
        "shortlist",
        sa.Column("shortlist_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(name)) > 0", name=op.f("ck_shortlist_shortlist_name_not_blank")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_account.user_id"],
            name=op.f("fk_shortlist_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("shortlist_id", name=op.f("pk_shortlist")),
        sa.UniqueConstraint("user_id", "name", name="uq_shortlist_user_name"),
    )
    op.create_index("ix_shortlist_user", "shortlist", ["user_id"], unique=False)

    op.create_table(
        "shortlist_entry",
        sa.Column("entry_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shortlist_id", sa.BigInteger(), nullable=False),
        sa.Column("player_key", sa.String(length=128), nullable=False),
        sa.Column("player_name", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(player_key)) > 0",
            name=op.f("ck_shortlist_entry_shortlist_entry_key_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["shortlist_id"],
            ["shortlist.shortlist_id"],
            name=op.f("fk_shortlist_entry_shortlist_id_shortlist"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id", name=op.f("pk_shortlist_entry")),
        sa.UniqueConstraint("shortlist_id", "player_key", name="uq_shortlist_entry_player"),
    )
    op.create_index("ix_shortlist_entry_list", "shortlist_entry", ["shortlist_id"], unique=False)

    # A rename, not a redefinition: the predicate is untouched, so no row is
    # revalidated and the operation takes a lock only briefly.
    op.execute(
        f"ALTER TABLE fact_player_season_stats "
        f"RENAME CONSTRAINT {TRUNCATED_CHECK} TO {RENAMED_CHECK}"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE fact_player_season_stats "
        f"RENAME CONSTRAINT {RENAMED_CHECK} TO {TRUNCATED_CHECK}"
    )
    op.drop_index("ix_shortlist_entry_list", table_name="shortlist_entry")
    op.drop_table("shortlist_entry")
    op.drop_index("ix_shortlist_user", table_name="shortlist")
    op.drop_table("shortlist")
