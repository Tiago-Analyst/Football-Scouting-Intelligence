"""Record what a quality check found, not only its English sentence.

Revision ID: 0015_quality_detail_message
Revises: 0014_shortlist_assessment
Create Date: 2026-10-30

WHY
===

`fact_data_quality.detail` holds a finished English sentence, composed when
the check ran and then stored: "12.2% of player-seasons report more detailed
recorded minutes than minutes played."

Everywhere else in this API, prose the reader sees is accompanied by a code and
its values, so the interface writes the sentence in its own language - see
`Message` in `app.schemas.api`. The quality checks were the exception, and not
by design: they are the one place where the prose is PERSISTED rather than
composed per request, so the pattern needed a column and never got one. The
public data-quality page therefore printed seventeen English sentences into a
Portuguese page.

This column is that code and those values: `{"code": "minutes_coverage",
"values": {"share": 0.999}}`.

WHY NOT DERIVE IT FROM `detail`
===============================

Because the only way to recover the numbers from a stored sentence is to parse
the English, and a parser against prose is a translation that breaks silently
when the prose improves. The values have to be recorded where they are
measured.

WHY NULLABLE, AND NOT BACK-FILLED
=================================

Every row written before this column existed has none, and inventing values
for them would mean reading them back out of the sentence - the thing above
says not to do. Those rows keep `detail`, and the interface falls back to it.

A source's checks become translatable at its next load. That is a real
limitation and it is visible rather than papered over: the page shows English
for a check until the load that recorded it is superseded.

WHY `JSON` AND NOT `JSONB`
==========================

It is read whole, with the row, and never queried into. JSONB's indexing would
buy nothing and its stricter normalisation is not wanted here.

ROLLBACK
========

Dropping the column loses the codes and nothing else. `detail` is untouched by
this migration and is still correct on every row, so the page falls back to
English exactly as it did before.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0015_quality_detail_message"
down_revision: str | None = "0014_shortlist_assessment"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "fact_data_quality",
        sa.Column("detail_message", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fact_data_quality", "detail_message")
