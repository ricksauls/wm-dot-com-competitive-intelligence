from pydantic import BaseModel, HttpUrl
from typing import Optional, List
from datetime import date, datetime
from app.models import BrandType


# --- BRANDS ---

class BrandBase(BaseModel):
    name: str
    type: BrandType
    tracked: bool = True

class BrandCreate(BrandBase):
    pass

class BrandUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[BrandType] = None
    tracked: Optional[bool] = None

class BrandOut(BrandBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- PRODUCTS ---

class ProductBase(BaseModel):
    name: str
    brand_id: int
    walmart_item_id: str
    walmart_url: str
    active: bool = True

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    brand_id: Optional[int] = None
    walmart_item_id: Optional[str] = None
    walmart_url: Optional[str] = None
    active: Optional[bool] = None

class ProductOut(ProductBase):
    id: int
    created_at: datetime
    brand: BrandOut

    class Config:
        from_attributes = True


# --- KEYWORDS ---

class KeywordBase(BaseModel):
    keyword: str
    active: bool = True

class KeywordCreate(KeywordBase):
    pass

class KeywordUpdate(BaseModel):
    keyword: Optional[str] = None
    active: Optional[bool] = None

class KeywordOut(KeywordBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- TRACKING GROUPS ---

class TrackingGroupBase(BaseModel):
    name: str
    description: Optional[str] = None
    active: bool = True

class TrackingGroupCreate(TrackingGroupBase):
    brand_ids:   List[int] = []
    product_ids: List[int] = []
    keyword_ids: List[int] = []

class TrackingGroupUpdate(BaseModel):
    name:        Optional[str] = None
    description: Optional[str] = None
    active:      Optional[bool] = None
    brand_ids:   Optional[List[int]] = None
    product_ids: Optional[List[int]] = None
    keyword_ids: Optional[List[int]] = None

class TrackingGroupOut(TrackingGroupBase):
    id:         int
    created_at: datetime
    brands:     List[BrandOut]   = []
    products:   List[ProductOut] = []
    keywords:   List[KeywordOut] = []

    class Config:
        from_attributes = True
