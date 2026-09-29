"""Add unique business job keys and worker lease tokens.

Revision ID: c041f713d2a0
Revises: 9a61f76ac225
"""

from alembic import op
import sqlalchemy as sa


revision = "c041f713d2a0"
down_revision = "9a61f76ac225"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("operation_key", sa.String(length=180), nullable=True))
        batch.add_column(sa.Column("lease_token", sa.String(length=36), nullable=True))
        batch.create_unique_constraint("uq_job_operation", ["workspace_id", "operation_key"])


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("uq_job_operation", type_="unique")
        batch.drop_column("lease_token")
        batch.drop_column("operation_key")
