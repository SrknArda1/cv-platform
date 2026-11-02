"""baslangic semasi: Flask-Migrate oncesi tablolar

Flask-Migrate projeye sonradan eklendi. Ilk gocten (7b292242e90c) once
tablolar db.create_all() ile kurulmustu, bu yuzden zincir bos bir
veritabaninda 'user' tablosunu bulamayip patliyordu. Bu dosya zincirin
basina o gunku semayi (bd5889b^:models.py) koyar; boylece bos
veritabaninda "flask db upgrade" sifirdan calisir.

Mevcut veritabanlari (canli dahil) bu adimi zaten gecmis sayilir: Alembic
alembic_version'daki surumun atalarini yeniden calistirmaz. Bu dosya
yalnizca bos veritabaninda calisir.

UYARI: downgrade() TUM tablolari siler. Gercek verisi olan bir
veritabaninda "flask db downgrade base" asla calistirilmamali.

Revision ID: 3fbf04b1f979
Revises:
Create Date: 2026-10-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3fbf04b1f979'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('departments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('full_name', sa.String(length=255), nullable=True),
    sa.Column('department', sa.String(length=120), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('transcript_filename', sa.String(length=255), nullable=True),
    sa.Column('photo_filename', sa.String(length=255), nullable=True),
    sa.Column('skills', sa.Text(), nullable=True),
    sa.Column('company_name', sa.String(length=255), nullable=True),
    sa.Column('contact_person', sa.String(length=255), nullable=True),
    sa.Column('is_approved', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_email'), ['email'], unique=True)

    op.create_table('education',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('degree_type', sa.String(length=50), nullable=True),
    sa.Column('school', sa.String(length=255), nullable=False),
    sa.Column('department', sa.String(length=255), nullable=True),
    sa.Column('gpa', sa.String(length=10), nullable=True),
    sa.Column('start_year', sa.String(length=10), nullable=True),
    sa.Column('end_year', sa.String(length=10), nullable=True),
    sa.ForeignKeyConstraint(['student_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('experience',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('company', sa.String(length=255), nullable=False),
    sa.Column('position', sa.String(length=255), nullable=True),
    sa.Column('start_date', sa.String(length=30), nullable=True),
    sa.Column('end_date', sa.String(length=30), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['student_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('certificate',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('institution', sa.String(length=255), nullable=True),
    sa.Column('date', sa.String(length=30), nullable=True),
    sa.ForeignKeyConstraint(['student_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('project',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('tech_stack', sa.String(length=255), nullable=True),
    sa.Column('link', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['student_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('project')
    op.drop_table('certificate')
    op.drop_table('experience')
    op.drop_table('education')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_email'))

    op.drop_table('user')
    op.drop_table('departments')
