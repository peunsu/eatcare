"""식품 검색 및 식단기록 관리. 기록 변경 시 해당 날짜 요약/위험도/알림 재계산."""
from datetime import datetime, timedelta, date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Member, Food, DietRecord, FoodNutrient, Nutrient
from app.schemas import FoodOut, DietRecordIn, DietRecordOut
from app.auth import get_current_member
from app.services.nutrition import recompute_daily_summary

router = APIRouter(prefix="/api/diet", tags=["diet"])


@router.get("/category-summary")
def category_summary(days: int | None = Query(None, ge=1, le=3650),
                     db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    """본인이 섭취한 식품을 대분류별 기록 수로 집계(상위 8). days 지정 시 최근 N일만. 반환: [{category, count}]."""
    where = "dr.회원코드 = :m"
    params = {"m": me.code}
    if days:
        where += " AND dr.기록일시 >= :start"
        params["start"] = datetime.now() - timedelta(days=days - 1)
    rows = db.execute(text(
        f"""
        SELECT COALESCE(f.대분류, '미분류') AS category, COUNT(*) AS cnt
        FROM DIET_RECORD dr JOIN FOOD f ON f.식품코드 = dr.식품코드
        WHERE {where}
        GROUP BY category ORDER BY cnt DESC LIMIT 8
        """
    ), params).fetchall()
    return [{"category": r.category, "count": int(r.cnt)} for r in rows]


@router.get("/foods", response_model=list[FoodOut])
def search_foods(q: str = Query("", description="식품명 검색어"), limit: int = 20,
                 db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    # 공백을 무시하고 매칭(저장값의 공백 제거 후 비교). 순서·붙여쓰기 달라도 매칭. 짧은 이름 우선.
    query = db.query(Food)
    for tok in (q or "").split():
        query = query.filter(Food.search_name.like(f"%{tok}%"))
    foods = query.order_by(func.char_length(Food.name), Food.name).limit(min(limit, 100)).all()
    return [FoodOut(code=f.code, name=f.name, base_amount=f.base_amount, base_unit=f.base_unit) for f in foods]


def _to_out(db, r: DietRecord) -> DietRecordOut:
    return _to_out_batch(db, [r])[0]


def _to_out_batch(db, records: list[DietRecord]) -> list[DietRecordOut]:
    """여러 기록을 식품/영양소 일괄 조회로 변환(N+1 제거). 기록당 2쿼리 → 전체 2쿼리."""
    if not records:
        return []
    codes = list({r.food_code for r in records})
    foods = {f.code: f for f in db.query(Food).filter(Food.code.in_(codes)).all()}
    fn_map: dict[str, list] = {}
    for fc, nm, un, amt in (
        db.query(FoodNutrient.food_code, Nutrient.name, Nutrient.unit, FoodNutrient.amount)
        .join(Nutrient, Nutrient.code == FoodNutrient.nutrient_code)
        .filter(FoodNutrient.food_code.in_(codes)).all()
    ):
        fn_map.setdefault(fc, []).append((nm, un, amt))
    out = []
    for r in records:
        food = foods.get(r.food_code)
        base = (food.base_amount if food and food.base_amount else 100) or 100
        nutrients = [{"name": nm, "unit": un, "amount": round(amt * r.amount / base, 1)}
                     for nm, un, amt in fn_map.get(r.food_code, [])]
        out.append(DietRecordOut(code=r.code, food_code=r.food_code,
                                 food_name=food.name if food else r.food_code,
                                 category=food.category if food else None,
                                 amount=r.amount, recorded_at=r.recorded_at, nutrients=nutrients))
    return out


@router.post("/records", response_model=DietRecordOut)
def add_record(req: DietRecordIn, db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    if not db.query(Food).filter(Food.code == req.food_code).first():
        raise HTTPException(status_code=404, detail="존재하지 않는 식품입니다.")
    when = req.recorded_at or datetime.now()
    rec = DietRecord(member_code=me.code, food_code=req.food_code, amount=req.amount, recorded_at=when)
    db.add(rec)
    db.commit()
    db.refresh(rec)
    # 위험도/요약만 즉시 갱신, 알림은 자정 배치에서만 발송
    recompute_daily_summary(db, me.code, when.date(), emit_notifications=False)
    return _to_out(db, rec)


@router.get("/records", response_model=list[DietRecordOut])
def list_records(date: date_type | None = None, db: Session = Depends(get_db),
                 me: Member = Depends(get_current_member)):
    q = db.query(DietRecord).filter(DietRecord.member_code == me.code)
    if date:
        from sqlalchemy import func
        q = q.filter(func.date(DietRecord.recorded_at) == date)
    recs = q.order_by(DietRecord.recorded_at.desc()).limit(200).all()
    return _to_out_batch(db, recs)


@router.delete("/records/{code}")
def delete_record(code: int, db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    rec = db.query(DietRecord).filter(DietRecord.code == code, DietRecord.member_code == me.code).first()
    if not rec:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    when = rec.recorded_at.date()
    db.delete(rec)
    db.commit()
    # 위험도/요약만 즉시 갱신, 알림은 자정 배치에서만 발송
    recompute_daily_summary(db, me.code, when, emit_notifications=False)
    return {"ok": True}
