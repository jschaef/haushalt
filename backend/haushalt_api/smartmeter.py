"""Automatic meter readings from devices on the local network.

Two ways in, both end in record_value():
- push: a device (or a script) POSTs the value with the meter's device
  token, see smartmeter_api.ingest_reading;
- pull: the API fetches source_url every POLL_MINUTES and reads the number
  at source_path in the JSON answer (e.g. "StatusSNS.SML.Total_in" for an
  IR reading head with Tasmota, "main.value" for AI-on-the-edge - presets
  are suggestions, the path depends on the device's configuration).

Readings stay one per day: later values of the same day replace the earlier
one, so the statistics and forecasts work unchanged.

Polling is a request made by the server, so it is limited (SSRF): http(s)
only, no redirects, 5 s, 64 KB, and only private, loopback or link-local
addresses unless HAUSHALT_POLL_ALLOW_PUBLIC is set; http requests go to the
checked IP itself (no DNS rebinding between check and request).
"""

import asyncio
import hashlib
import ipaddress
import json
import logging
import secrets
import socket
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import config, tenancy
from .db import Meter, MeterReading, SessionLocal

logger = logging.getLogger("haushalt_api")

TOKEN_PREFIX = "hhm_"
MAX_BYTES = 64 * 1024
TIMEOUT = 5.0

PRESETS = {
    # suggestions; the JSON path depends on the device's own configuration
    "tasmota": {"url": "http://<device>/cm?cmnd=Status%2010", "path": "StatusSNS.SML.Total_in"},
    "ai_on_the_edge": {"url": "http://<device>/json", "path": "main.value"},
}


class SourceError(ValueError):
    pass


# --- device tokens -----------------------------------------------------------


def new_device_token() -> tuple[str, str]:
    """(token shown once, hash stored)"""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def meter_for_token(session: Session, token: str) -> Meter | None:
    if not token.startswith(TOKEN_PREFIX):
        return None
    # the device knows no household: look in all of them
    return session.scalar(tenancy.everywhere(select(Meter).where(Meter.ingest_token_hash == hash_token(token))))


# --- recording -------------------------------------------------------------------


def record_value(session: Session, meter: Meter, value: float, day: date, source: str = "device") -> MeterReading:
    """Stores the day's reading (replacing an earlier one of that day).
    Meters count up: the value must not be below an earlier day's reading or
    above a later day's one."""
    if value < 0:
        raise SourceError("Negative meter value")
    for other in meter.readings:
        if other.read_on < day and other.value > value:
            raise SourceError(f"Value {value} is below the reading of {other.read_on} ({other.value})")
        if other.read_on > day and other.value < value:
            raise SourceError(f"Value {value} is above the reading of {other.read_on} ({other.value})")
    reading = next((r for r in meter.readings if r.read_on == day), None)
    if reading is None:
        reading = MeterReading(meter_id=meter.id, read_on=day, value=value, source=source)
        session.add(reading)
        meter.readings.append(reading)
    else:
        reading.value, reading.source = value, source
    meter.last_ingest_at = datetime.now(timezone.utc)
    meter.last_ingest_error = ""
    return reading


# --- polling -----------------------------------------------------------------------


def number_at(data, path: str) -> float:
    """'StatusSNS.SML.Total_in' / 'main.value' / 'items.0.value' -> float"""
    current = data
    for key in [k for k in path.split(".") if k]:
        if isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        elif isinstance(current, dict) and key in current:
            current = current[key]
        else:
            raise SourceError(f"Path '{path}' not found at '{key}'")
    if isinstance(current, bool) or current is None:
        raise SourceError(f"No number at '{path}'")
    try:
        return float(str(current).strip().replace(",", "."))
    except ValueError:
        raise SourceError(f"No number at '{path}': {str(current)[:40]!r}")


def _address_allowed(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if config.POLL_ALLOW_PUBLIC:
        return not (ip.is_multicast or ip.is_unspecified)
    return ip.is_private or ip.is_loopback or ip.is_link_local


def resolve_checked(url: str) -> tuple[str, str]:
    """(url, address) if the URL may be polled, else SourceError. The address
    is the checked IP the request must go to (see fetch_value)."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SourceError("Only http:// or https:// URLs with a host")
    if parts.username or parts.password:
        raise SourceError("No credentials in the URL")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror:
        raise SourceError(f"Host not found: {parts.hostname}")
    addresses = sorted({info[4][0] for info in infos})
    if not addresses or not all(_address_allowed(a) for a in addresses):
        raise SourceError("Only devices in the local network can be polled")
    return url, addresses[0]


def check_url(url: str) -> str:
    """Raises SourceError unless the URL may be polled; returns it stripped."""
    return resolve_checked(url)[0]


def pinned(url: str, address: str) -> tuple[str, dict]:
    """For http: the URL with the checked IP instead of the host name, plus
    the Host header - no second DNS lookup that could be rebound to another
    address. https keeps the name: the certificate check needs it, and a
    rebound address would fail that check."""
    parts = urlsplit(url)
    if parts.scheme != "http":
        return url, {}
    host = f"[{address}]" if ":" in address else address
    netloc = f"{host}:{parts.port}" if parts.port else host
    return parts._replace(netloc=netloc).geturl(), {"host": parts.netloc}


def fetch_value(url: str, path: str) -> float:
    target, host = pinned(*resolve_checked(url))
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as client:
            with client.stream("GET", target, headers={"accept": "application/json", **host}) as response:
                if response.status_code != 200:
                    raise SourceError(f"Device answered {response.status_code}")
                body = b""
                for chunk in response.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise SourceError("Answer too large")
    except httpx.HTTPError as exc:
        raise SourceError(f"Device not reachable: {type(exc).__name__}")
    try:
        data = json.loads(body)
    except ValueError:
        raise SourceError("Answer is not JSON")
    return number_at(data, path)


def poll_meter(session: Session, meter: Meter, today: date | None = None) -> MeterReading:
    try:
        value = fetch_value(meter.source_url, meter.source_path)
        return record_value(session, meter, value, today or date.today())
    except SourceError as exc:
        meter.last_ingest_error = str(exc)[:256]
        raise


def poll_all() -> int:
    """Polls every meter with a source; returns how many succeeded."""
    done = 0
    with SessionLocal() as session:
        sources = session.execute(
            tenancy.everywhere(select(Meter.id, Meter.household_id).where(Meter.source_url != ""))
        ).all()
        for meter_id, household_id in sources:
            # each meter in its household's view (its readings, new readings)
            tenancy.bind(session, household_id)
            meter = session.scalar(select(Meter).where(Meter.id == meter_id).options(selectinload(Meter.readings)))
            try:
                poll_meter(session, meter)
                done += 1
            except SourceError as exc:
                logger.warning("meter %s: %s", meter.id, exc)
            session.commit()
    return done


async def poll_forever() -> None:
    while True:
        await asyncio.sleep(config.POLL_MINUTES * 60)
        try:
            await asyncio.to_thread(poll_all)
        except Exception:  # keep the loop alive; the error is logged
            logger.exception("meter polling failed")
