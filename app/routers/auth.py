from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Member
from app.schemas import SignupRequest, TokenOut
from app.auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut)
def signup(req: SignupRequest, db: Session = Depends(get_db)):
    email = req.email.strip()
    if db.query(Member).filter(Member.email == email).first():
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")
    member = Member(
        name=req.name.strip(), email=email, password=hash_password(req.password.strip()),
        birth_year=req.birth_year, gender=req.gender,
        joined_at=date.today(), role="USER", status="ACTIVE",
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return TokenOut(access_token=create_access_token(member), role=member.role)


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip()
    member = db.query(Member).filter(Member.email == email).first()
    if not member or not verify_password(form.password.strip(), member.password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    if member.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")
    return TokenOut(access_token=create_access_token(member), role=member.role)
