"""Record when each source's data was actually loaded.

`fact_data_quality.executed_at` was the only per-source timestamp, and it
answers a different question: when a *check* ran. Checks run against data
nobody reloaded, and a load that rolled back leaves the previous run's checks
sitting there looking recent - so reading one as the other lets the site claim
"performance data updated today" about data a fortnight old.

Rows are written inside the load transaction, so a load that fails its checks
discards its own claim to have refreshed anything.

Revision ID: 0006_source_load
Revises: 0005_recorded_minutes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_source_load"
down_revision: str | None = "0005_recorded_minutes"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "fact_source_load",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("rows_loaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("pipeline_run", sa.String(length=128), nullable=True),
        sa.CheckConstraint("rows_loaded >= 0", name="source_load_rows_non_negative"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fact_source_load")),
    )
    op.create_index(
        "ix_source_load_source_time", "fact_source_load", ["source", "loaded_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_load_source_time", table_name="fact_source_load")
    op.drop_table("fact_source_load")
