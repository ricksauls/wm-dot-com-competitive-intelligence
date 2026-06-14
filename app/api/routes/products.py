from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import Product, Brand
from app.schemas import ProductCreate, ProductUpdate, ProductOut
from typing import List

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=List[ProductOut])
def list_products(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return (
        db.query(Product)
        .options(joinedload(Product.brand))
        .order_by(Product.name)
        .all()
    )


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not db.query(Brand).get(payload.brand_id):
        raise HTTPException(status_code=400, detail="Brand not found")
    if db.query(Product).filter(Product.walmart_item_id == payload.walmart_item_id).first():
        raise HTTPException(status_code=400, detail="Item ID already exists")
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return db.query(Product).options(joinedload(Product.brand)).get(product.id)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if payload.brand_id and not db.query(Brand).get(payload.brand_id):
        raise HTTPException(status_code=400, detail="Brand not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return db.query(Product).options(joinedload(Product.brand)).get(product.id)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    product = db.query(Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
