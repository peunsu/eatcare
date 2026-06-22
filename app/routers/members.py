"""회원 프로필 및 기저질환 관리."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Member, Disease, MemberDisease, Nutrient
from app.schemas import MemberOut, ProfileUpdate, DiseaseOut, MemberDiseaseIn, MemberDiseaseOut
from app.auth import get_current_member

router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("/me", response_model=MemberOut)
def get_me(me: Member = Depends(get_current_member)):
    return MemberOut(code=me.code, name=me.name, email=me.email,
                     birth_year=me.birth_year, gender=me.gender, role=me.role)


@router.put("/me", response_model=MemberOut)
def update_me(req: ProfileUpdate, me: Member = Depends(get_current_member), db: Session = Depends(get_db)):
    if req.name is not None:
        me.name = req.name
    if req.birth_year is not None:
        me.birth_year = req.birth_year
    if req.gender is not None:
        me.gender = req.gender
    db.commit()
    db.refresh(me)
    return MemberOut(code=me.code, name=me.name, email=me.email,
                     birth_year=me.birth_year, gender=me.gender, role=me.role)


@router.get("/diseases", response_model=list[DiseaseOut])
def list_diseases(db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    rows = db.query(Disease, Nutrient).join(Nutrient, Nutrient.code == Disease.nutrient_code).all()
    return [DiseaseOut(code=d.code, name=d.name, nutrient_name=n.name, unit=n.unit, daily_limit=d.daily_limit)
            for d, n in rows]


@router.get("/me/diseases", response_model=list[MemberDiseaseOut])
def my_diseases(db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    rows = db.query(MemberDisease, Disease).join(Disease, Disease.code == MemberDisease.disease_code).filter(
        MemberDisease.member_code == me.code).all()
    return [MemberDiseaseOut(disease_code=md.disease_code, name=d.name, registered_at=md.registered_at)
            for md, d in rows]


@router.post("/me/diseases", response_model=list[MemberDiseaseOut])
def add_disease(req: MemberDiseaseIn, db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    if not db.query(Disease).filter(Disease.code == req.disease_code).first():
        raise HTTPException(status_code=404, detail="존재하지 않는 질환입니다.")
    exists = db.query(MemberDisease).filter(
        MemberDisease.member_code == me.code, MemberDisease.disease_code == req.disease_code).first()
    if not exists:
        db.add(MemberDisease(member_code=me.code, disease_code=req.disease_code, registered_at=date.today()))
        db.commit()
    return my_diseases(db, me)


@router.delete("/me/diseases/{disease_code}")
def remove_disease(disease_code: int, db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    db.query(MemberDisease).filter(
        MemberDisease.member_code == me.code, MemberDisease.disease_code == disease_code).delete()
    db.commit()
    return {"ok": True}
