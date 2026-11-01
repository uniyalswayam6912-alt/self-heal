"""add source service to jobs"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6059e728bee"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("source_service", sa.String(100), nullable=True),
    )

    op.execute(
        "UPDATE jobs SET source_service = 'legacy' "
        "WHERE source_service IS NULL"
    )

    op.alter_column(
        "jobs",
        "source_service",
        nullable=False,
    )

    op.create_index(
        "ix_jobs_source_service",
        "jobs",
        ["source_service"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_source_service", table_name="jobs")
    op.drop_column("jobs", "source_service")