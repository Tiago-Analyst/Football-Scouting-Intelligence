"""What the owner decided about a saved player.

Revision ID: 0014_shortlist_assessment
Revises: 0013_publication_identity
Create Date: 2026-10-01

WHY
===

A shortlist could hold a player and a note, which is enough to remember
someone and not enough to run a process. A desk tracking forty players needs
to know which four are priorities, which eleven were ruled out and why, and
which were last looked at in March - and none of that survives in a single
free-text box that has to be read in full to be searched.

So an entry gains a status from a fixed vocabulary, the argument split into
what is good and what is not, and the date the owner last recorded a
judgement.

WHY A FIXED VOCABULARY
======================

Five words a desk uses the same way beat thirty that each person uses
differently, and a closed set is what makes "show me the priorities" a
question the list can answer rather than a search. The check constraint is
the database saying the same thing the service says: a status the UI cannot
render would make a row unreadable, and the only way to find out would be to
read it.

WHY THE EXISTING ROWS BECOME LONGLIST
=====================================

Every entry needs a status, and "saved but not yet assessed" is exactly what
a longlist is - so the backfill states what was already true rather than
inventing a judgement nobody made. `last_reviewed_at` stays null for the same
reason: saving a player is not reviewing them, and defaulting it to the date
they were added would put a claim in the column.

WHY THIS CHANGES NO SCORE
=========================

Nothing here is read by the analytics. A player marked Rejected ranks exactly
where the numbers put them. The shortlist records judgement, the analytics
record what the provider supplied, and keeping them apart is what makes
either one readable.

ROLLBACK
========

Dropping the columns loses the assessments and nothing else. No analytical
table references them, and the entries themselves survive with their notes.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0014_shortlist_assessment"
down_revision: str | None = "0013_publication_identity"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "shortlist_entry",
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="longlist",
        ),
    )
    op.add_column("shortlist_entry", sa.Column("pros", sa.Text(), nullable=True))
    op.add_column("shortlist_entry", sa.Column("concerns", sa.Text(), nullable=True))
    op.add_column(
        "shortlist_entry",
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "shortlist_entry_status_known",
        "shortlist_entry",
        "status IN ('longlist', 'monitor', 'scout', 'priority', 'rejected')",
    )
    op.create_index(
        "ix_shortlist_entry_status",
        "shortlist_entry",
        ["shortlist_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_shortlist_entry_status", table_name="shortlist_entry")
    op.drop_constraint("shortlist_entry_status_known", "shortlist_entry", type_="check")
    op.drop_column("shortlist_entry", "last_reviewed_at")
    op.drop_column("shortlist_entry", "concerns")
    op.drop_column("shortlist_entry", "pros")
    op.drop_column("shortlist_entry", "status")
