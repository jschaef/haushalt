"""Personal API tokens: scripts on the host upload receipts and bank
statements and read what their member reads (auth.API_TOKEN_WRITES). Each
member manages their own tokens, only in the browser; a token is shown
once and valid until it is revoked or the account's sessions end."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import browser_member, new_api_token
from .db import ApiToken, User, get_session

router = APIRouter(prefix="/api/v1/api-tokens")


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class TokenOut(BaseModel):
    id: int
    name: str
    hint: str
    created_at: datetime
    last_used_at: datetime | None


class NewToken(TokenOut):
    token: str


def _out(record: ApiToken) -> dict:
    return TokenOut.model_validate(record, from_attributes=True).model_dump()


@router.get("", response_model=list[TokenOut])
def list_tokens(user: User = Depends(browser_member), session: Session = Depends(get_session)):
    query = select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
    return [_out(t) for t in session.scalars(query)]


@router.post("", response_model=NewToken, status_code=201)
def create_token(body: TokenIn, user: User = Depends(browser_member), session: Session = Depends(get_session)):
    name = " ".join(body.name.split())
    if not name:
        raise HTTPException(status_code=422, detail="Token name required")
    token, digest = new_api_token()
    record = ApiToken(user_id=user.id, name=name, token_hash=digest, hint=token[-4:], version=user.token_version)
    session.add(record)
    session.commit()
    return {**_out(record), "token": token}


@router.delete("/{token_id}", status_code=204)
def revoke_token(token_id: int, user: User = Depends(browser_member), session: Session = Depends(get_session)):
    record = session.get(ApiToken, token_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Unknown API token")
    session.delete(record)
    session.commit()
