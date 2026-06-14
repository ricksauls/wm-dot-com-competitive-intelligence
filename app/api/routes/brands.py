from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import Brand
from app.schemas import BrandCreate, BrandUpdate, BrandOut
from typing import List

router = APIRouter(prefix="/api/brands", tags=["brands"])


@router.get("/", response_model=List[BrandOut])
def list_brands(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Brand).order_by(Brand.name).all()


@router.post("/", response_model=BrandOut, status_code=status.HTTP_201_CREATED)
def create_brand(payload: BrandCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if db.query(Brand).filter(Brand.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Brand name already exists")
    brand = Brand(**payload.model_dump())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.put("/{brand_id}", response_model=BrandOut)
def update_brand(brand_id: int, payload: BrandUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    brand = db.query(Brand).get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)
    db.commit()
    db.refresh(brand)
    return brand


@router.delete("/{brand_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(brand_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    brand = db.query(Brand).get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    if brand.products:
        raise HTTPException(status_code=400, detail="Cannot delete brand with associated products")
    db.delete(brand)
    db.commit()
