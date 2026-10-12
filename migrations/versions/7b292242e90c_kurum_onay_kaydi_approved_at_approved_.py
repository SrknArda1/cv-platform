"""kurum onay kaydi: approved_at, approved_by_id

Kurum hesabi onaylandiginda ogrencilerin kisisel verisine erisim kazanir.
Bu kararin kim tarafindan ve ne zaman verildigi kayda gecsin diye user
tablosuna iki kolon eklenir.

Not: Alembic yabanci anahtar kisitini isimsiz uretmisti; downgrade() o
haliyle calismaz (isimsiz kisit dusurulemez). Kisita acik bir ad verildi.

Revision ID: 7b292242e90c
Revises:
Create Date: 2026-10-12 22:27:11.180880

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b292242e90c'
down_revision = None
branch_labels = None
depends_on = None

FK_ADI = "fk_user_approved_by_id"


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('approved_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(FK_ADI, 'user', ['approved_by_id'], ['id'])


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint(FK_ADI, type_='foreignkey')
        batch_op.drop_column('approved_by_id')
        batch_op.drop_column('approved_at')
