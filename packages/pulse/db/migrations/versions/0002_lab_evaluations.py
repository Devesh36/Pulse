"""Persist laboratory evaluation reports independently of agent evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lab_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("at", sa.Float(), nullable=False),
        sa.Column("scenario", sa.String(80), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
    )
    op.create_index("ix_lab_evaluations_at", "lab_evaluations", ["at"])


def downgrade():
    op.drop_index("ix_lab_evaluations_at", table_name="lab_evaluations")
    op.drop_table("lab_evaluations")
