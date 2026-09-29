"""Add single-use connected installation bootstrap marker.

Revision ID: 9a61f76ac225
Revises: 46cca3d1ba97
"""

from alembic import op
import sqlalchemy as sa


revision = "9a61f76ac225"
down_revision = "46cca3d1ba97"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installation_bootstrap",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("installation_bootstrap")
