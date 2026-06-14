from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import Keyword
from app.schemas import KeywordCreate, KeywordUpdate, KeywordOut
from typing import List

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


@router.get("/", response_model=List[KeywordOut])
def list_keywords(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Keyword).order_by(Keyword.keyword).all()


@router.post("/", response_model=KeywordOut, status_code=status.HTTP_201_CREATED)
def create_keyword(payload: KeywordCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if db.query(Keyword).filter(Keyword.keyword == payload.keyword).first():
        raise HTTPException(status_code=400, detail="Keyword already exists")
    kw = Keyword(**payload.model_dump())
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return kw


@router.put("/{keyword_id}", response_model=KeywordOut)
def update_keyword(keyword_id: int, payload: KeywordUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    kw = db.query(Keyword).get(keyword_id)
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(kw, field, value)
    db.commit()
    db.refresh(kw)
    return kw


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(keyword_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    kw = db.query(Keyword).get(keyword_id)
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")
    db.delete(kw)
    db.commit()
