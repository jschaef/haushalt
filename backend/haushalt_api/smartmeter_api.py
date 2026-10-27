"""HTTP API for automatic meter readings (see smartmeter.py)."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from . import smartmeter, tenancy
from .auth import current_user
from .db import Meter, get_session

router = APIRouter(prefix="/api/v1/meters", dependencies=[Depends(current_user)])
# no user login here: devices authenticate with their meter's device token
ingest_router = APIRouter(prefix="/api/v1/ingest")


class SourceIn(BaseModel):
    source_url: str = Field(default="", max_length=512)
    source_path: str = Field(default="", max_length=128)


class ReadingPush(BaseModel):
    value: float = Field(ge=0)
    # device time; the day of the reading. Default: today
    read_at: datetime | None = None


def _meter(session: Session, meter_id: int) -> Meter:
    meter = session.get(Meter, meter_id, options=[selectinload(Meter.readings)])
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    return meter


@router.get("/sources/presets")
def presets():
    return smartmeter.PRESETS


@router.post("/{meter_id}/device-token")
def create_device_token(meter_id: int, session: Session = Depends(get_session)):
    """A new token for pushing readings; shown once, replaces an older one."""
    meter = _meter(session, meter_id)
    token, digest = smartmeter.new_device_token()
    meter.ingest_token_hash = digest
    session.commit()
    return {"token": token}


@router.delete("/{meter_id}/device-token", status_code=204)
def revoke_device_token(meter_id: int, session: Session = Depends(get_session)):
    meter = _meter(session, meter_id)
    meter.ingest_token_hash = ""
    session.commit()


@router.put("/{meter_id}/source")
def set_source(meter_id: int, body: SourceIn, session: Session = Depends(get_session)):
    """Device URL and JSON path to poll; an empty URL switches polling off."""
    meter = _meter(session, meter_id)
    url = body.source_url.strip()
    if url:
        if not body.source_path.strip():
            raise HTTPException(status_code=422, detail="JSON path required")
        try:
            url = smartmeter.check_url(url)
        except smartmeter.SourceError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    meter.source_url, meter.source_path = url, body.source_path.strip() if url else ""
    meter.last_ingest_error = ""
    session.commit()
    return {"source_url": meter.source_url, "source_path": meter.source_path}


@router.post("/{meter_id}/poll")
def poll_now(meter_id: int, session: Session = Depends(get_session)):
    meter = _meter(session, meter_id)
    if not meter.source_url:
        raise HTTPException(status_code=422, detail="No device URL set")
    try:
        reading = smartmeter.poll_meter(session, meter)
    except smartmeter.SourceError as exc:
        session.commit()  # keep last_ingest_error
        raise HTTPException(status_code=422, detail=str(exc))
    session.commit()
    return {"read_on": reading.read_on.isoformat(), "value": reading.value}


@ingest_router.post("/reading", status_code=201)
def ingest_reading(
    body: ReadingPush,
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
):
    scheme, _, token = authorization.partition(" ")
    meter = smartmeter.meter_for_token(session, token.strip()) if scheme.lower() == "bearer" else None
    if meter is None:
        raise HTTPException(status_code=401, detail="Unknown device token")
    # the token names the meter and with it the household
    tenancy.bind(session, meter.household_id)
    meter = _meter(session, meter.id)
    day = body.read_at.date() if body.read_at else date.today()
    try:
        reading = smartmeter.record_value(session, meter, body.value, day)
    except smartmeter.SourceError as exc:
        meter.last_ingest_error = str(exc)[:256]
        session.commit()
        raise HTTPException(status_code=422, detail=str(exc))
    session.commit()
    return {"meter_id": meter.id, "read_on": reading.read_on.isoformat(), "value": reading.value}
