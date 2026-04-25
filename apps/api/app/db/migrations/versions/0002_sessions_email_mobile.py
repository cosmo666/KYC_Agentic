"""sessions: add email + mobile (captured by the splash form before chat starts)

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column("sessions", sa.Column("mobile", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "mobile")
    op.drop_column("sessions", "email")
