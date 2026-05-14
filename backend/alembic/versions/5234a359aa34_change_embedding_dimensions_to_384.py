"""change_embedding_dimensions_to_384

Revision ID: 5234a359aa34
Revises: 6c207f0a3626
Create Date: 2026-05-13 16:49:08.454503

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa


revision: str = '5234a359aa34'
down_revision: Union[str, Sequence[str], None] = '6c207f0a3626'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunk_embedding_hnsw")
    op.alter_column('chunks', 'embedding',
               existing_type=pgvector.sqlalchemy.Vector(1536),
               type_=pgvector.sqlalchemy.Vector(384),
               existing_nullable=True)
    op.create_index('idx_chunk_embedding_hnsw', 'chunks', ['embedding'], unique=False, postgresql_ops={'embedding': 'vector_cosine_ops'}, postgresql_with={'m': '16', 'ef_construction': '64'}, postgresql_using='hnsw')


def downgrade() -> None:
    op.drop_index('idx_chunk_embedding_hnsw', table_name='chunks', postgresql_ops={'embedding': 'vector_cosine_ops'}, postgresql_with={'m': '16', 'ef_construction': '64'}, postgresql_using='hnsw')
    op.alter_column('chunks', 'embedding',
               existing_type=pgvector.sqlalchemy.Vector(384),
               type_=pgvector.sqlalchemy.Vector(1536),
               existing_nullable=True)
    op.create_index('idx_chunk_embedding_hnsw', 'chunks', ['embedding'], unique=False, postgresql_ops={'embedding': 'vector_cosine_ops'}, postgresql_with={'m': '16', 'ef_construction': '64'}, postgresql_using='hnsw')
