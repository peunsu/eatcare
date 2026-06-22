"""식품 정보 검색 (로그인 필요). 식품의 영양성분을 조회한다."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Food, FoodNutrient, Nutrient, Disease, Member
from app.auth import get_current_member

router = APIRouter(prefix="/api/foods", tags=["foods"])


@router.get("/search")
def search_foods(q: str = Query("", description="식품명 검색어"), limit: int = 20,
                 db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    """식품명 검색: 공백을 무시하고 매칭(저장값의 공백 제거 후 비교). 짧은 이름 우선.
    예) DB '바나나 우유' ↔ 검색 '바나나우유'/'바나나 우유'/'우유 바나나' 모두 매칭."""
    query = db.query(Food)
    for tok in (q or "").split():
        query = query.filter(Food.search_name.like(f"%{tok}%"))
    foods = query.order_by(func.char_length(Food.name), Food.name).limit(min(limit, 50)).all()
    return [{"code": f.code, "name": f.name, "category": f.category,
             "base_amount": f.base_amount, "base_unit": f.base_unit} for f in foods]


@router.get("/{code}/distribution")
def food_distribution(code: str, db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    """같은 대분류 식품들의 100g당 영양소 함량 분포 + 이 식품의 값/상위 백분위. 영양소별 반환."""
    from sqlalchemy import text
    f = db.query(Food).filter(Food.code == code).first()
    if not f:
        raise HTTPException(status_code=404, detail="식품을 찾을 수 없습니다.")
    base = f.base_amount or 100
    cat = f.category
    rows = (
        db.query(Nutrient.code, Nutrient.name, Nutrient.unit, FoodNutrient.amount)
        .join(FoodNutrient, FoodNutrient.nutrient_code == Nutrient.code)
        .filter(FoodNutrient.food_code == code)
        .order_by(Nutrient.code)
        .all()
    )
    CAP = 2000
    out = []
    for nc, nm, unit, amt in rows:
        val = round(amt * 100.0 / base, 1)  # 100g당 함량
        values = []
        if cat:
            vrows = db.execute(text(
                """
                SELECT fn.함량 * 100.0 / f.기준량 AS v
                FROM FOOD_NUTRIENT fn JOIN FOOD f ON f.식품코드 = fn.식품코드
                WHERE f.대분류 = :cat AND fn.영양소코드 = :nc AND f.기준량 > 0
                """
            ), {"cat": cat, "nc": nc}).fetchall()
            values = [float(r.v) for r in vrows]
        total = len(values)
        greater = sum(1 for v in values if v > val)
        # 상위 백분위: 이 식품보다 높은 식품 비율 (작을수록 상위)
        percentile = round((greater + 0.5) / total * 100, 1) if total else None
        sample = values
        if total > CAP:
            step = total / CAP
            sample = [values[int(i * step)] for i in range(CAP)]
        out.append({
            "nutrient_code": nc, "name": nm, "unit": unit,
            "value": val, "percentile": percentile, "sample_size": total,
            "values": [round(v, 1) for v in sample],
        })
    return {"category": cat, "nutrients": out}


@router.get("/{code}")
def food_detail(code: str, db: Session = Depends(get_db), me: Member = Depends(get_current_member)):
    """식품 상세: 기준량당 영양성분 + 질환별 일일 상한(해당 영양소)."""
    f = db.query(Food).filter(Food.code == code).first()
    if not f:
        raise HTTPException(status_code=404, detail="식품을 찾을 수 없습니다.")
    rows = (
        db.query(Nutrient.name, Nutrient.unit, FoodNutrient.amount)
        .join(FoodNutrient, FoodNutrient.nutrient_code == Nutrient.code)
        .filter(FoodNutrient.food_code == code)
        .order_by(Nutrient.code)
        .all()
    )
    # 질환 기준 영양소별 일일 상한 (당류/나트륨/지방 등) → 강조용
    limits = {}
    for d in db.query(Disease).all():
        if d.nutrient and d.nutrient.name not in limits:
            limits[d.nutrient.name] = {"limit": d.daily_limit, "unit": d.nutrient.unit, "disease": d.name}
    nutrients = [{
        "name": n[0], "unit": n[1], "amount": round(n[2], 1),
        "daily_limit": limits.get(n[0], {}).get("limit"),
        "disease": limits.get(n[0], {}).get("disease"),
    } for n in rows]
    return {"code": f.code, "name": f.name, "category": f.category,
            "base_amount": f.base_amount, "base_unit": f.base_unit, "nutrients": nutrients}
