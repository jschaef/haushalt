"""Tags: for whom or what for, next to the category (bank bookings and
recurring costs). Every household member may manage them, like categories."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import Tag, get_session

router = APIRouter(prefix="/api/v1/tags", dependencies=[Depends(current_user)])


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    color: str = Field(default="#64748b", pattern=r"^#[0-9a-fA-F]{6}$")


class TagOut(BaseModel):
    id: int
    name: str
    color: str


def resolve_tags(session: Session, tag_ids: list[int]) -> list[Tag]:
    """The tags for a list of ids; unknown ids are an error, not ignored."""
    ids = list(dict.fromkeys(tag_ids))
    tags = list(session.scalars(select(Tag).where(Tag.id.in_(ids)))) if ids else []
    if len(tags) != len(ids):
        raise HTTPException(status_code=422, detail="Unknown tag")
    return sorted(tags, key=lambda t: t.name.lower())


def _clean_name(session: Session, name: str, own_id: int | None = None) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(status_code=422, detail="Tag name required")
    # one tag per name, whatever the case ("Urlaub" = "urlaub")
    other = session.scalar(select(Tag).where(func.lower(Tag.name) == name.lower()))
    if other is not None and other.id != own_id:
        raise HTTPException(status_code=409, detail="Tag exists")
    return name


def _tag(session: Session, tag_id: int) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


@router.get("", response_model=list[TagOut])
def list_tags(session: Session = Depends(get_session)):
    return [TagOut.model_validate(t, from_attributes=True) for t in session.scalars(select(Tag).order_by(func.lower(Tag.name)))]


@router.post("", response_model=TagOut, status_code=201)
def create_tag(body: TagIn, session: Session = Depends(get_session)):
    tag = Tag(name=_clean_name(session, body.name), color=body.color)
    session.add(tag)
    session.commit()
    return TagOut.model_validate(tag, from_attributes=True)


@router.put("/{tag_id}", response_model=TagOut)
def update_tag(tag_id: int, body: TagIn, session: Session = Depends(get_session)):
    tag = _tag(session, tag_id)
    tag.name, tag.color = _clean_name(session, body.name, tag.id), body.color
    session.commit()
    return TagOut.model_validate(tag, from_attributes=True)


@router.delete("/{tag_id}", status_code=204)
def delete_tag(tag_id: int, session: Session = Depends(get_session)):
    """Removes the tag everywhere (links and learned rules go with it)."""
    session.delete(_tag(session, tag_id))
    session.commit()
