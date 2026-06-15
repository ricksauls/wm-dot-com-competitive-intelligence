from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, func
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class BrandType(str, enum.Enum):
    mine = "mine"
    competitor = "competitor"


class PositionType(str, enum.Enum):
    organic = "organic"
    sponsored = "sponsored"


# --- CONFIG MODELS ---

class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    type = Column(Enum(BrandType, name="brand_type"), nullable=False)
    tracked = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())

    products = relationship("Product", back_populates="brand")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String(255), nullable=False)
    walmart_item_id = Column(String(50), nullable=False, unique=True)
    walmart_url = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())

    brand = relationship("Brand", back_populates="products")
    snapshots = relationship("ProductSnapshot", back_populates="product")
    content_snapshots = relationship("ContentSnapshot", back_populates="product")
    content_changes = relationship("ContentChange", back_populates="product")
    review_deltas = relationship("ReviewDelta", back_populates="product")


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(255), nullable=False, unique=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())

    search_results = relationship("SearchResult", back_populates="keyword")
    share_of_search = relationship("ShareOfSearch", back_populates="keyword")


# --- DAILY SCRAPED DATA ---

class SearchResult(Base):
    __tablename__ = "search_results"

    id = Column(Integer, primary_key=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id", ondelete="RESTRICT"), nullable=False)
    scraped_at = Column(Date, nullable=False)
    position = Column(Integer, nullable=False)
    position_type = Column(Enum(PositionType, name="position_type"), nullable=False)
    item_id = Column(String(50), nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="SET NULL"), nullable=True)
    is_new_sku = Column(Boolean, nullable=False, default=False)

    keyword = relationship("Keyword", back_populates="search_results")
    brand = relationship("Brand")


# --- WEEKLY SCRAPED DATA ---

class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    scraped_at = Column(Date, nullable=False)
    price = Column(Numeric(10, 2), nullable=True)
    review_count = Column(Integer, nullable=True)
    avg_rating = Column(Numeric(3, 2), nullable=True)

    product = relationship("Product", back_populates="snapshots")


class ContentSnapshot(Base):
    __tablename__ = "content_snapshots"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    scraped_at = Column(Date, nullable=False)
    title = Column(Text, nullable=True)
    bullets = Column(JSON, nullable=True)
    image_count = Column(Integer, nullable=True)
    images = Column(JSON, nullable=True)        # [{url, width, height}, ...]
    has_aplus = Column(Boolean, nullable=True)
    has_brand_story = Column(Boolean, nullable=True)
    has_comparison_chart = Column(Boolean, nullable=True)
    has_video = Column(Boolean, nullable=True)
    has_enhanced_content = Column(Boolean, nullable=True)

    product = relationship("Product", back_populates="content_snapshots")


class ContentChange(Base):
    __tablename__ = "content_changes"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    detected_at = Column(Date, nullable=False)
    field_changed = Column(String(100), nullable=False)
    previous_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)

    product = relationship("Product", back_populates="content_changes")


# --- ANALYSIS / ROLLUP TABLES ---

class ShareOfSearch(Base):
    __tablename__ = "share_of_search"

    id = Column(Integer, primary_key=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id", ondelete="RESTRICT"), nullable=False)
    date = Column(Date, nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="RESTRICT"), nullable=True)
    organic_count = Column(Integer, nullable=False, default=0)
    sponsored_count = Column(Integer, nullable=False, default=0)
    total_count = Column(Integer, nullable=False, default=0)

    keyword = relationship("Keyword", back_populates="share_of_search")
    brand = relationship("Brand")


class ReviewDelta(Base):
    __tablename__ = "review_delta"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    date = Column(Date, nullable=False)
    review_count = Column(Integer, nullable=True)
    review_count_delta = Column(Integer, nullable=True)
    avg_rating = Column(Numeric(3, 2), nullable=True)
    avg_rating_delta = Column(Numeric(3, 2), nullable=True)

    product = relationship("Product", back_populates="review_deltas")


# --- TRACKING GROUPS ---

# Junction tables (defined as Table objects for many-to-many)
from sqlalchemy import Table

group_brands = Table(
    'group_brands', Base.metadata,
    Column('group_id', Integer, ForeignKey('tracking_groups.id', ondelete='CASCADE'), primary_key=True),
    Column('brand_id', Integer, ForeignKey('brands.id', ondelete='CASCADE'), primary_key=True),
)

group_products = Table(
    'group_products', Base.metadata,
    Column('group_id', Integer, ForeignKey('tracking_groups.id', ondelete='CASCADE'), primary_key=True),
    Column('product_id', Integer, ForeignKey('products.id', ondelete='CASCADE'), primary_key=True),
)

group_keywords = Table(
    'group_keywords', Base.metadata,
    Column('group_id', Integer, ForeignKey('tracking_groups.id', ondelete='CASCADE'), primary_key=True),
    Column('keyword_id', Integer, ForeignKey('keywords.id', ondelete='CASCADE'), primary_key=True),
)


class TrackingGroup(Base):
    __tablename__ = "tracking_groups"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    active      = Column(Boolean, nullable=False, default=True)
    created_at  = Column(DateTime, server_default=func.now())

    brands   = relationship("Brand",   secondary=group_brands,   backref="groups")
    products = relationship("Product", secondary=group_products, backref="groups")
    keywords = relationship("Keyword", secondary=group_keywords, backref="groups")
