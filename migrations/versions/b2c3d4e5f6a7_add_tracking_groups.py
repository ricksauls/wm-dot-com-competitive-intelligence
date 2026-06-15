"""add tracking groups

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:

    # Main tracking groups table
    op.create_table(
        'tracking_groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Junction tables
    op.create_table(
        'group_brands',
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('tracking_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('brands.id', ondelete='CASCADE'), nullable=False),
        sa.PrimaryKeyConstraint('group_id', 'brand_id'),
    )
    op.create_index('ix_group_brands_group', 'group_brands', ['group_id'])
    op.create_index('ix_group_brands_brand', 'group_brands', ['brand_id'])

    op.create_table(
        'group_products',
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('tracking_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.PrimaryKeyConstraint('group_id', 'product_id'),
    )
    op.create_index('ix_group_products_group', 'group_products', ['group_id'])

    op.create_table(
        'group_keywords',
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('tracking_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('keyword_id', sa.Integer(), sa.ForeignKey('keywords.id', ondelete='CASCADE'), nullable=False),
        sa.PrimaryKeyConstraint('group_id', 'keyword_id'),
    )
    op.create_index('ix_group_keywords_group', 'group_keywords', ['group_id'])


def downgrade() -> None:
    op.drop_table('group_keywords')
    op.drop_table('group_products')
    op.drop_table('group_brands')
    op.drop_table('tracking_groups')
