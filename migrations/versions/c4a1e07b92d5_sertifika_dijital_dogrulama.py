"""sertifika dijital dogrulama: credential_id ve credential_url

Revision ID: c4a1e07b92d5
Revises: 8fec39c31e99
Create Date: 2026-10-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a1e07b92d5'
down_revision = '8fec39c31e99'
branch_labels = None
depends_on = None


def upgrade():
    # Ikisi de nullable: mevcut sertifika kayitlari oldugu gibi kalir,
    # ogrenci diledigi zaman doldurur.
    with op.batch_alter_table('certificate', schema=None) as batch_op:
        batch_op.add_column(sa.Column('credential_id', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('credential_url', sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table('certificate', schema=None) as batch_op:
        batch_op.drop_column('credential_url')
        batch_op.drop_column('credential_id')
