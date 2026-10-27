"""The operator's routes (Jochen, 2026-10-27): households and their first
admin. The operator belongs to no household and sees none of their data;
inside a household its admins manage the members."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import tenancy
from .auth import hash_password, operator_user
from .db import Household, User, create_household, get_session
from .passwords import one_time_password

router = APIRouter(prefix="/api/v1/operator", dependencies=[Depends(operator_user)])


class AdminOut(BaseModel):
    id: int
    username: str
    display_name: str
    disabled: bool


class HouseholdOut(BaseModel):
    id: int
    name: str
    disabled: bool
    created_at: datetime
    members: int
    admins: list[AdminOut]


class NewHousehold(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    admin_username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._@-]+$")
    admin_display_name: str = Field(default="", max_length=128)


class HouseholdPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    disabled: bool | None = None


def _clean(name: str) -> str:
    return " ".join(name.split())


def _out(session: Session, household: Household) -> HouseholdOut:
    members = session.scalars(tenancy.everywhere(select(User).where(User.household_id == household.id))).all()
    return HouseholdOut(
        id=household.id,
        name=household.name,
        disabled=household.disabled,
        created_at=household.created_at,
        members=len(members),
        admins=[
            AdminOut(id=u.id, username=u.username, display_name=u.display_name, disabled=u.disabled)
            for u in sorted(members, key=lambda u: u.username) if u.is_admin
        ],
    )


def _household(session: Session, household_id: int) -> Household:
    household = session.get(Household, household_id)
    if household is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return household


@router.get("/households", response_model=list[HouseholdOut])
def list_households(session: Session = Depends(get_session)):
    return [_out(session, h) for h in session.scalars(select(Household).order_by(func.lower(Household.name)))]


@router.post("/households", status_code=201)
def add_household(body: NewHousehold, session: Session = Depends(get_session)):
    """A household with the default categories and merchants and its first
    admin, who gets a one-time password to pass on."""
    if session.scalar(tenancy.everywhere(select(User.id).where(User.username == body.admin_username))):
        raise HTTPException(status_code=409, detail="Username already taken")
    household = create_household(session, _clean(body.name))
    password = one_time_password()
    admin = User(
        household_id=household.id,
        username=body.admin_username,
        display_name=body.admin_display_name.strip() or body.admin_username,
        password_hash=hash_password(password),
        is_admin=True,
        must_change_password=True,
    )
    session.add(admin)
    session.commit()
    tenancy.bind(session, None)
    return {"household": _out(session, household), "one_time_password": password}


@router.patch("/households/{household_id}", response_model=HouseholdOut)
def change_household(household_id: int, body: HouseholdPatch, session: Session = Depends(get_session)):
    """Disabling ends every session of its members at their next request."""
    household = _household(session, household_id)
    if body.name is not None:
        household.name = _clean(body.name)
    if body.disabled is not None:
        household.disabled = body.disabled
    session.commit()
    return _out(session, household)


@router.post("/users/{user_id}/reset-password")
def reset_admin_password(user_id: int, session: Session = Depends(get_session)):
    """Only a household admin's: the members are their admins' business."""
    user = session.get(User, user_id, execution_options=tenancy.EVERYWHERE)
    if user is None or not user.is_admin or user.household_id is None:
        raise HTTPException(status_code=404, detail="No household admin")
    password = one_time_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.disabled = False
    user.token_version += 1
    session.commit()
    return {"one_time_password": password}
