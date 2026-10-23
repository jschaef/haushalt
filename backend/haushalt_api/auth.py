"""Passwords (scrypt) and HMAC-signed bearer tokens with server-side revocation.

Without HAUSHALT_SECRET a random secret is created once and kept in
DATA_DIR/secret, so tokens survive restarts.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete
from sqlalchemy.orm import Session

from . import config
from .db import RevokedToken, User, get_session
from .passwords import normalize

_bearer = HTTPBearer(auto_error=False)
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def _load_secret() -> str:
    if config.SECRET:
        return config.SECRET
    path = config.DATA_DIR / "secret"
    if path.exists():
        return path.read_text().strip()
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(32)
    path.write_text(value)
    path.chmod(0o600)
    return value


_SECRET = _load_secret()


def hash_password(password: str) -> str:
    # NFKC (NIST SP 800-63B): the same password typed on another keyboard matches
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(normalize(password).encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    # hashes from before the normalization were made from the raw text
    for candidate in dict.fromkeys((normalize(password), password)):
        computed = hashlib.scrypt(candidate.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
        if hmac.compare_digest(computed.hex(), digest):
            return True
    return False


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    jti: str
    expires_at: int
    version: int = 0


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: str) -> str:
    return hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_token(user: User, ttl: int | None = None) -> dict:
    expires_at = int(time.time()) + (config.TOKEN_TTL_SECONDS if ttl is None else ttl)
    claims = {"sub": user.id, "exp": expires_at, "jti": secrets.token_urlsafe(16), "ver": user.token_version}
    payload = _b64(json.dumps(claims, separators=(",", ":")).encode())
    return {"access_token": f"{payload}.{_sign(payload)}", "token_type": "bearer", "expires_at": expires_at}


def decode_token(token: str) -> TokenClaims:
    try:
        payload, signature = token.rsplit(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed token")
    if not hmac.compare_digest(_sign(payload), signature):
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        claims = json.loads(_unb64(payload))
        result = TokenClaims(int(claims["sub"]), str(claims["jti"]), int(claims["exp"]), int(claims.get("ver", 0)))
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Malformed token")
    if result.expires_at < time.time():
        raise HTTPException(status_code=401, detail="Token expired")
    return result


def revoke(session: Session, claims: TokenClaims) -> None:
    session.execute(delete(RevokedToken).where(RevokedToken.expires_at < int(time.time())))
    session.merge(RevokedToken(jti=claims.jti, expires_at=claims.expires_at))
    session.commit()


def current_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> TokenClaims:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = decode_token(credentials.credentials)
    if session.get(RevokedToken, claims.jti) is not None:
        raise HTTPException(status_code=401, detail="Token revoked")
    return claims


def session_user(
    claims: TokenClaims = Depends(current_claims),
    session: Session = Depends(get_session),
) -> User:
    """The logged-in account, also while it still has to replace a one-time
    password - only for the routes that do exactly that."""
    user = session.get(User, claims.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    # a password change, reset or disabling raised the version: old sessions end
    if user.disabled or claims.version != user.token_version:
        raise HTTPException(status_code=401, detail="Session ended")
    return user


def current_user(user: User = Depends(session_user)) -> User:
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="password_change_required")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only household admins may do this")
    return user
