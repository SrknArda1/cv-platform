"""transkript dogrulama alanlari

Koordinatorun yuklenen transkripti acip "dogrulandi" isaretleyebilmesi icin
uc kolon eklenir. Kurum tarafinda "VAR" yerine "DOGRULANDI" gosterilmesini
saglar.

Otomatik uretilen dosyada iki duzeltme yapildi:

1. transcript_verified NOT NULL olarak tanimli ve tabloda zaten kayit var.
   server_default olmadan migrasyon "NOT NULL constraint failed" ile
   patlardi; mevcut satirlara 0 (false) yazilmasi icin server_default
   eklendi.

2. Yabanci anahtar kisiti isimsiz uretilmisti; downgrade() isimsiz kisiti
   dusuremedigi icin calismazdi. Kisita acik ad verildi.

Revision ID: dbf6aa800dc1
Revises: 7b292242e90c
Create Date: 2026-10-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dbf6aa800dc1'
down_revision = '7b292242e90c'
branch_labels = None
depends_on = None

FK_ADI = "fk_user_transcript_verified_by_id"


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'transcript_verified', sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ))
        batch_op.add_column(sa.Column('transcript_verified_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('transcript_verified_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(FK_ADI, 'user', ['transcript_verified_by_id'], ['id'])


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint(FK_ADI, type_='foreignkey')
        batch_op.drop_column('transcript_verified_by_id')
        batch_op.drop_column('transcript_verified_at')
        batch_op.drop_column('transcript_verified')
