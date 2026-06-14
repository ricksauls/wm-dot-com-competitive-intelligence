"""initial schema

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2026-06-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        'brands',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('type', sa.Enum('mine', 'competitor', name='brand_type'), nullable=False),
        sa.Column('tracked', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('brands.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('walmart_item_id', sa.String(50), nullable=False, unique=True),
        sa.Column('walmart_url', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_products_brand_id', 'products', ['brand_id'])

    op.create_table(
        'keywords',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('keyword', sa.String(255), nullable=False, unique=True),
        sa.Column('active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        'search_results',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('keyword_id', sa.Integer(), sa.ForeignKey('keywords.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('scraped_at', sa.Date(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('position_type', sa.Enum('organic', 'sponsored', name='position_type'), nullable=False),
        sa.Column('item_id', sa.String(50), nullable=False),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('brands.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_new_sku', sa.Boolean(), nullable=False, default=False),
    )
    op.create_index('ix_search_results_keyword_date', 'search_results', ['keyword_id', 'scraped_at'])
    op.create_index('ix_search_results_date', 'search_results', ['scraped_at'])

    op.create_table(
        'product_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('scraped_at', sa.Date(), nullable=False),
        sa.Column('price', sa.Numeric(10, 2), nullable=True),
        sa.Column('review_count', sa.Integer(), nullable=True),
        sa.Column('avg_rating', sa.Numeric(3, 2), nullable=True),
    )
    op.create_index('ix_product_snapshots_product_date', 'product_snapshots', ['product_id', 'scraped_at'])

    op.create_table(
        'content_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('scraped_at', sa.Date(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('bullets', JSON, nullable=True),
        sa.Column('image_count', sa.Integer(), nullable=True),
        sa.Column('images', JSON, nullable=True),
        sa.Column('has_aplus', sa.Boolean(), nullable=True),
        sa.Column('has_brand_story', sa.Boolean(), nullable=True),
        sa.Column('has_comparison_chart', sa.Boolean(), nullable=True),
        sa.Column('has_video', sa.Boolean(), nullable=True),
        sa.Column('has_enhanced_content', sa.Boolean(), nullable=True),
    )
    op.create_index('ix_content_snapshots_product_date', 'content_snapshots', ['product_id', 'scraped_at'])

    op.create_table(
        'content_changes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('detected_at', sa.Date(), nullable=False),
        sa.Column('field_changed', sa.String(100), nullable=False),
        sa.Column('previous_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
    )
    op.create_index('ix_content_changes_product_date', 'content_changes', ['product_id', 'detected_at'])

    op.create_table(
        'share_of_search',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('keyword_id', sa.Integer(), sa.ForeignKey('keywords.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('brands.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('organic_count', sa.Integer(), nullable=False, default=0),
        sa.Column('sponsored_count', sa.Integer(), nullable=False, default=0),
        sa.Column('total_count', sa.Integer(), nullable=False, default=0),
    )
    op.create_index('ix_share_of_search_keyword_date', 'share_of_search', ['keyword_id', 'date'])

    op.create_table(
        'review_delta',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('review_count', sa.Integer(), nullable=True),
        sa.Column('review_count_delta', sa.Integer(), nullable=True),
        sa.Column('avg_rating', sa.Numeric(3, 2), nullable=True),
        sa.Column('avg_rating_delta', sa.Numeric(3, 2), nullable=True),
    )
    op.create_index('ix_review_delta_product_date', 'review_delta', ['product_id', 'date'])


def downgrade() -> None:
    op.drop_table('review_delta')
    op.drop_table('share_of_search')
    op.drop_table('content_changes')
    op.drop_table('content_snapshots')
    op.drop_table('product_snapshots')
    op.drop_table('search_results')
    op.drop_table('keywords')
    op.drop_table('products')
    op.drop_table('brands')
    op.execute("DROP TYPE IF EXISTS brand_type")
    op.execute("DROP TYPE IF EXISTS position_type")
