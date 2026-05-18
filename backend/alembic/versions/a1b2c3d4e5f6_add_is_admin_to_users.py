"""add is_admin to users

Revision ID: a1b2c3d4e5f6
Revises: 5234a359aa34
Create Date: 2026-05-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5234a359aa34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False))
    # Set the founding user as admin
    op.execute("UPDATE users SET is_admin = true WHERE email = 'ryanmilrad34@gmail.com'")


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
