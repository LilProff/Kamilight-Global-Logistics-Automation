from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.models import Segment
from app.routers.contacts import filtered_count
from app.schemas import SegmentIn, SegmentOut

router = APIRouter(prefix="/api/segments", tags=["segments"], dependencies=[Depends(current_user)])


def _out(db: Session, seg: Segment) -> SegmentOut:
    out = SegmentOut.model_validate(seg)
    out.count = filtered_count(db, seg.filters or {})
    return out


def _unique_name(db: Session, name: str, exclude_id: int | None = None) -> None:
    clash = db.scalar(select(Segment).where(Segment.name == name.strip(), Segment.id != (exclude_id or 0)))
    if clash:
        raise HTTPException(409, f"A segment called '{name}' already exists.")


@router.get("", response_model=list[SegmentOut])
def list_segments(db: Session = Depends(get_db)):
    return [_out(db, s) for s in db.scalars(select(Segment).order_by(Segment.name))]


@router.post("", response_model=SegmentOut, status_code=201)
def create(body: SegmentIn, db: Session = Depends(get_db)):
    _unique_name(db, body.name)
    seg = Segment(name=body.name.strip(), description=body.description, filters=body.filters)
    db.add(seg)
    db.commit()
    return _out(db, seg)


@router.put("/{segment_id}", response_model=SegmentOut)
def update(segment_id: int, body: SegmentIn, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment not found")
    _unique_name(db, body.name, exclude_id=seg.id)
    seg.name, seg.description, seg.filters = body.name.strip(), body.description, body.filters
    db.commit()
    return _out(db, seg)


@router.delete("/{segment_id}", status_code=204)
def delete(segment_id: int, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if seg is None:
        raise HTTPException(404, "Segment not found")
    db.delete(seg)
    db.commit()
