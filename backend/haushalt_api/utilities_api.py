"""HTTP API for utility meters, readings, tariffs and annual bills."""

import hashlib
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import config, utilities
from .auth import current_user
from .db import Category, Meter, MeterReading, RecurringCost, Tariff, UtilityBill, get_session
from .extraction import UTILITY_KINDS, ExtractionError, get_extractor, sniff
from .receipts import SUFFIX
from .stats import Period

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])
KIND_PATTERN = "^(" + "|".join(UTILITY_KINDS) + ")$"


class MeterIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern=KIND_PATTERN)
    unit: str = Field(min_length=1, max_length=16)
    meter_number: str = Field(default="", max_length=64)
    category_id: int | None = None


class MeterOut(MeterIn):
    id: int
    last_reading: dict | None
    has_device_token: bool = False
    source_url: str = ""
    source_path: str = ""
    last_ingest_at: datetime | None = None
    last_ingest_error: str = ""


class ReadingIn(BaseModel):
    read_on: date
    value: float = Field(ge=0)
    source: str = Field(default="manual", pattern="^(manual|photo|bill|device)$")


class ReadingOut(ReadingIn):
    id: int


class TariffIn(BaseModel):
    valid_from: date
    unit_price_ct: float = Field(ge=0, le=10_000)
    base_fee_monthly_cents: int = Field(default=0, ge=0)


class TariffOut(TariffIn):
    id: int


class BillPatch(BaseModel):
    meter_id: int | None = None


def _meter(session: Session, meter_id: int) -> Meter:
    meter = session.get(Meter, meter_id, options=[selectinload(Meter.readings), selectinload(Meter.tariffs)])
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    return meter


def _meter_out(meter: Meter) -> MeterOut:
    last = meter.readings[-1] if meter.readings else None
    return MeterOut(
        id=meter.id,
        name=meter.name,
        kind=meter.kind,
        unit=meter.unit,
        meter_number=meter.meter_number,
        category_id=meter.category_id,
        last_reading={"read_on": last.read_on.isoformat(), "value": last.value} if last else None,
        has_device_token=bool(meter.ingest_token_hash),
        source_url=meter.source_url,
        source_path=meter.source_path,
        last_ingest_at=meter.last_ingest_at,
        last_ingest_error=meter.last_ingest_error,
    )


def _check_category(session: Session, category_id: int | None) -> None:
    if category_id is not None and session.get(Category, category_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown category {category_id}")


async def _read_upload(upload: UploadFile) -> tuple[bytes, str]:
    data = await upload.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")
    media_type = sniff(data)
    if media_type is None:
        raise HTTPException(status_code=415, detail="Unsupported file type")
    return data, media_type


# --- meters ------------------------------------------------------------------


@router.get("/meters", response_model=list[MeterOut])
def list_meters(session: Session = Depends(get_session)):
    meters = session.scalars(select(Meter).options(selectinload(Meter.readings)).order_by(Meter.name))
    return [_meter_out(m) for m in meters]


@router.post("/meters", response_model=MeterOut, status_code=201)
def create_meter(body: MeterIn, session: Session = Depends(get_session)):
    _check_category(session, body.category_id)
    meter = Meter(**body.model_dump())
    session.add(meter)
    session.commit()
    return _meter_out(_meter(session, meter.id))


@router.put("/meters/{meter_id}", response_model=MeterOut)
def update_meter(meter_id: int, body: MeterIn, session: Session = Depends(get_session)):
    meter = _meter(session, meter_id)
    _check_category(session, body.category_id)
    for field, value in body.model_dump().items():
        setattr(meter, field, value)
    session.commit()
    return _meter_out(meter)


@router.delete("/meters/{meter_id}", status_code=204)
def delete_meter(meter_id: int, session: Session = Depends(get_session)):
    session.delete(_meter(session, meter_id))
    session.commit()


@router.get("/meters/{meter_id}/summary")
def meter_summary(meter_id: int, start: date | None = None, end: date | None = None, session: Session = Depends(get_session)):
    meter = _meter(session, meter_id)
    period = utilities.billing_period(session, meter)
    if start or end:
        period = Period(start or period.start, end or period.end)
        if period.end < period.start:
            raise HTTPException(status_code=422, detail="end before start")
    return utilities.meter_summary(session, meter, period)


# --- readings ----------------------------------------------------------------


@router.get("/meters/{meter_id}/readings", response_model=list[ReadingOut])
def list_readings(meter_id: int, session: Session = Depends(get_session)):
    return [ReadingOut.model_validate(r, from_attributes=True) for r in _meter(session, meter_id).readings]


@router.post("/meters/{meter_id}/readings", response_model=ReadingOut, status_code=201)
def add_reading(meter_id: int, body: ReadingIn, session: Session = Depends(get_session)):
    """Meters only count up: a value below an earlier or above a later
    reading is refused (typos, or a replaced meter - then add a new meter)."""
    meter = _meter(session, meter_id)
    for other in meter.readings:
        if (other.read_on < body.read_on and other.value > body.value) or (
            other.read_on > body.read_on and other.value < body.value
        ):
            raise HTTPException(status_code=422, detail=f"Value does not fit the reading of {other.read_on}")
    reading = MeterReading(meter_id=meter.id, **body.model_dump())
    session.add(reading)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="There is already a reading for this day")
    return ReadingOut.model_validate(reading, from_attributes=True)


@router.delete("/readings/{reading_id}", status_code=204)
def delete_reading(reading_id: int, session: Session = Depends(get_session)):
    reading = session.get(MeterReading, reading_id)
    if reading is None:
        raise HTTPException(status_code=404, detail="Reading not found")
    session.delete(reading)
    session.commit()


@router.post("/meters/read-photo")
async def read_meter_photo(file: UploadFile = File(...), session: Session = Depends(get_session)):
    """Reads a meter photo and proposes a reading; nothing is stored - the
    person checks the value and saves it. The photo is not kept."""
    data, media_type = await _read_upload(file)
    try:
        result = get_extractor().read_meter(data, media_type)
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not result["is_meter"]:
        raise HTTPException(status_code=422, detail="not_a_meter")
    meter = utilities.match_meter(session, result["kind"], result["meter_number"])
    return {**result, "meter_id": meter.id if meter else None, "read_on": date.today().isoformat()}


# --- tariffs -----------------------------------------------------------------


@router.get("/meters/{meter_id}/tariffs", response_model=list[TariffOut])
def list_tariffs(meter_id: int, session: Session = Depends(get_session)):
    return [TariffOut.model_validate(t, from_attributes=True) for t in _meter(session, meter_id).tariffs]


@router.post("/meters/{meter_id}/tariffs", response_model=TariffOut, status_code=201)
def add_tariff(meter_id: int, body: TariffIn, session: Session = Depends(get_session)):
    meter = _meter(session, meter_id)
    if any(t.valid_from == body.valid_from for t in meter.tariffs):
        raise HTTPException(status_code=409, detail="A tariff starts on this day already")
    tariff = Tariff(meter_id=meter.id, **body.model_dump())
    session.add(tariff)
    session.commit()
    return TariffOut.model_validate(tariff, from_attributes=True)


@router.delete("/tariffs/{tariff_id}", status_code=204)
def delete_tariff(tariff_id: int, session: Session = Depends(get_session)):
    tariff = session.get(Tariff, tariff_id)
    if tariff is None:
        raise HTTPException(status_code=404, detail="Tariff not found")
    session.delete(tariff)
    session.commit()


# --- annual bills ------------------------------------------------------------


def _bill_path(bill: UtilityBill):
    return config.DATA_DIR / "bills" / f"{bill.id}{SUFFIX.get(bill.media_type, '.bin')}"


def _bill_out(bill: UtilityBill) -> dict:
    fields = (
        "id meter_id kind provider meter_number period_start period_end consumption unit total_cents paid_cents "
        "balance_cents unit_price_ct base_fee_monthly_cents new_instalment_cents file_name media_type error"
    ).split()
    out = {name: getattr(bill, name) for name in fields}
    for name in ("period_start", "period_end"):
        out[name] = out[name].isoformat() if out[name] else None
    return out


@router.get("/bills")
def list_bills(session: Session = Depends(get_session)):
    bills = session.scalars(select(UtilityBill).order_by(UtilityBill.period_end.desc().nulls_last(), UtilityBill.id.desc()))
    return [_bill_out(b) for b in bills]


@router.post("/bills", status_code=201)
async def upload_bill(file: UploadFile = File(...), session: Session = Depends(get_session)):
    data, media_type = await _read_upload(file)
    bill = UtilityBill(file_name=(file.filename or "")[:256], media_type=media_type)
    session.add(bill)
    session.flush()
    path = _bill_path(bill)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    try:
        result = get_extractor().read_bill(data, media_type)
    except ExtractionError as exc:
        bill.error = str(exc)[:512]
        session.commit()
        return _bill_out(bill)
    if not result.pop("is_bill"):
        bill.error = "not_a_bill"
    else:
        for name, value in result.items():
            setattr(bill, name, value)
        meter = utilities.match_meter(session, bill.kind, bill.meter_number)
        bill.meter_id = meter.id if meter else None
    session.commit()
    return _bill_out(bill)


@router.patch("/bills/{bill_id}")
def patch_bill(bill_id: int, body: BillPatch, session: Session = Depends(get_session)):
    bill = session.get(UtilityBill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    if body.meter_id is not None:
        _meter(session, body.meter_id)
    bill.meter_id = body.meter_id
    session.commit()
    return _bill_out(bill)


@router.post("/bills/{bill_id}/apply")
def apply_bill(bill_id: int, session: Session = Depends(get_session)):
    """Take over what the bill says for the future: its prices as a tariff
    from the start of the billed period (if none starts there) and the new
    instalment as the meter's recurring cost from today on."""
    bill = session.get(UtilityBill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.meter_id is None:
        raise HTTPException(status_code=422, detail="Assign the bill to a meter first")
    meter = _meter(session, bill.meter_id)
    applied = {"tariff": False, "instalment": False}
    if bill.unit_price_ct is not None and bill.period_start is not None:
        if not any(t.valid_from == bill.period_start for t in meter.tariffs):
            session.add(
                Tariff(
                    meter_id=meter.id,
                    valid_from=bill.period_start,
                    unit_price_ct=bill.unit_price_ct,
                    base_fee_monthly_cents=bill.base_fee_monthly_cents or 0,
                )
            )
            applied["tariff"] = True
    if bill.new_instalment_cents:
        today = date.today()
        running = session.scalars(
            select(RecurringCost).where(
                RecurringCost.meter_id == meter.id,
                (RecurringCost.end_on.is_(None)) | (RecurringCost.end_on >= today),
            )
        ).all()
        # the new instalment keeps the tags of the one it replaces
        tags = list(dict.fromkeys(tag for cost in running for tag in cost.tags))
        for cost in running:
            if cost.start_on < today:
                cost.end_on = today - timedelta(days=1)
            else:  # planned but not started yet: replaced by the bill's amount
                session.delete(cost)
        session.add(
            RecurringCost(
                name=f"{meter.name} – {bill.provider}".strip(" –") if bill.provider else meter.name,
                category_id=meter.category_id,
                amount_cents=bill.new_instalment_cents,
                interval_months=1,
                start_on=today,
                meter_id=meter.id,
                tags=tags,
            )
        )
        applied["instalment"] = True
    session.commit()
    return applied


@router.get("/bills/{bill_id}/file")
def bill_file(bill_id: int, session: Session = Depends(get_session)):
    bill = session.get(UtilityBill, bill_id)
    if bill is None or not _bill_path(bill).exists():
        raise HTTPException(status_code=404, detail="Bill not found")
    return FileResponse(
        _bill_path(bill),
        media_type=bill.media_type,
        headers={"x-content-type-options": "nosniff", "content-security-policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"},
    )


@router.delete("/bills/{bill_id}", status_code=204)
def delete_bill(bill_id: int, session: Session = Depends(get_session)):
    bill = session.get(UtilityBill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    _bill_path(bill).unlink(missing_ok=True)
    session.delete(bill)
    session.commit()
