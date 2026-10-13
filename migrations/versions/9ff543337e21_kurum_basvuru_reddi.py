"""kurum basvuru reddi

Kurum hesabinin ucuncu bir durumu olmasi icin: bekliyor / onayli /
reddedildi. Hesabi silmek yerine isaretlemek, kuruma net bir cevap verir
ve kararin kaydini birakir.

Not: Alembic yabanci anahtar kisitini yine isimsiz uretti; downgrade() o
haliyle calismazdi. Kisita acik ad verildi.

Revision ID: 9ff543337e21
Revises: dbf6aa800dc1
Create Date: 2026-10-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9ff543337e21'
down_revision = 'dbf6aa800dc1'
branch_labels = None
depends_on = None

FK_ADI = "fk_user_rejected_by_id"


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rejected_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('rejected_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rejection_reason', sa.String(length=500), nullable=True))
        batch_op.create_foreign_key(FK_ADI, 'user', ['rejected_by_id'], ['id'])


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint(FK_ADI, type_='foreignkey')
        batch_op.drop_column('rejection_reason')
        batch_op.drop_column('rejected_by_id')
        batch_op.drop_column('rejected_at')
