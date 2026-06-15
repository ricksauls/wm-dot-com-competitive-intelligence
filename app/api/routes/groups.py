from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import TrackingGroup, Brand, Product, Keyword
from app.schemas import TrackingGroupCreate, TrackingGroupUpdate, TrackingGroupOut
from typing import List

router = APIRouter(prefix="/api/groups", tags=["groups"])


def _apply_members(group, payload, db):
    """Helper — set brands, products, keywords from ID lists."""
    if payload.brand_ids is not None:
        group.brands   = db.query(Brand).filter(Brand.id.in_(payload.brand_ids)).all()
    if payload.product_ids is not None:
        group.products = db.query(Product).filter(Product.id.in_(payload.product_ids)).all()
    if payload.keyword_ids is not None:
        group.keywords = db.query(Keyword).filter(Keyword.id.in_(payload.keyword_ids)).all()


@router.get("/", response_model=List[TrackingGroupOut])
def list_groups(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return (
        db.query(TrackingGroup)
        .options(
            joinedload(TrackingGroup.brands),
            joinedload(TrackingGroup.products),
            joinedload(TrackingGroup.keywords),
        )
        .order_by(TrackingGroup.name)
        .all()
    )


@router.post("/", response_model=TrackingGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(payload: TrackingGroupCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if db.query(TrackingGroup).filter(TrackingGroup.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Group name already exists")
    group = TrackingGroup(
        name=payload.name,
        description=payload.description,
        active=payload.active,
    )
    db.add(group)
    db.flush()
    _apply_members(group, payload, db)
    db.commit()
    db.refresh(group)
    return group


@router.put("/{group_id}", response_model=TrackingGroupOut)
def update_group(group_id: int, payload: TrackingGroupUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    group = db.query(TrackingGroup).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    for field, value in payload.model_dump(exclude_unset=True, exclude={"brand_ids","product_ids","keyword_ids"}).items():
        setattr(group, field, value)
    _apply_members(group, payload, db)
    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(group_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    group = db.query(TrackingGroup).get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    db.delete(group)
    db.commit()
