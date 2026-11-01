"""Add job retry fields

Revision ID: 80d3e98b793f
Revises: d6059e728bee
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "80d3e98b793f"
down_revision: Union[str, Sequence[str], None] = "d6059e728bee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "jobs",
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )

    op.add_column(
        "jobs",
        sa.Column(
            "next_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "next_retry_at")
    op.drop_column("jobs", "max_retries")
    op.drop_column("jobs", "retry_count")