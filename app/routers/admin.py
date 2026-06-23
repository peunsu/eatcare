from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Member, MemberDisease, Disease, DailySummary, SummaryNutrient, Nutrient, DietRecord, Food, Notification, FoodNutrient,
)
from app.auth import require_admin
from app.services.stats import (
    filter_members, group_average_nutrients, over_threshold_ratio, risk_distribution,
    nutrient_distributions, food_category_distribution, nutrient_over_ratio,
    _member_nutrient_avg,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

DISEASE_WEIGHT = {"당뇨": 4, "고혈압": 2, "고지혈증": 1}


@router.get("/report")
def group_report(
    age_min: int | None = Query(None),
    age_max: int | None = Query(None),
    gender: str | None = Query(None, pattern="^[MF]$"),
    disease_code: int | None = Query(None),
    start: date_type | None = Query(None),
    end: date_type | None = Query(None),
    db: Session = Depends(get_db),
    _: Member = Depends(require_admin),
):
    end = end or date_type.today()
    start = start or (end - timedelta(days=30))
    members = filter_members(db, age_min, age_max, gender, disease_code)
    codes = [m.code for m in members]
    avg_map = _member_nutrient_avg(db, codes, start, end) if codes else {}
    nutrients = db.query(Nutrient).order_by(Nutrient.code).all()
    disease_nutrients = db.query(Disease, Nutrient).join(Nutrient, Nutrient.code == Disease.nutrient_code).all()
    limit_by = {d.nutrient_code: d.daily_limit for d, _ in disease_nutrients}
    return {
        "filters": {"age_min": age_min, "age_max": age_max, "gender": gender,
                    "disease_code": disease_code, "start": str(start), "end": str(end)},
        "member_count": len(codes),
        "averages": group_average_nutrients(db, codes, start, end, avg_map=avg_map, nutrients=nutrients),
        "over_threshold": over_threshold_ratio(db, codes, start, end, avg_map=avg_map, disease_nutrients=disease_nutrients),
        "nutrient_over": nutrient_over_ratio(db, codes, start, end, avg_map=avg_map, nutrients=nutrients, limit_by=limit_by),
        "risk_distribution": risk_distribution(db, codes, start, end),
        "distributions": nutrient_distributions(db, codes, start, end, avg_map=avg_map, nutrients=nutrients, limit_by=limit_by),
        "food_categories": food_category_distribution(db, codes, start, end),
    }


def _member_diseases(db, code):
    rows = (
        db.query(Disease.name, MemberDisease.registered_at)
        .join(MemberDisease, MemberDisease.disease_code == Disease.code)
        .filter(MemberDisease.member_code == code)
        .all()
    )
    return rows


def _latest_summaries(db, codes):
    """회원별 최신 일일요약 조회"""
    if not codes:
        return {}
    ph = ",".join(str(int(c)) for c in codes)
    rows = db.execute(text(
        f"""
        SELECT 회원코드, 날짜, 위험도 FROM (
          SELECT 회원코드, 날짜, 위험도,
                 ROW_NUMBER() OVER (PARTITION BY 회원코드 ORDER BY 날짜 DESC, 요약코드 DESC) rn
          FROM DAILY_SUMMARY WHERE 회원코드 IN ({ph})
        ) t WHERE rn = 1
        """
    )).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


@router.get("/members")
def list_members(
    age_min: int | None = Query(None),
    age_max: int | None = Query(None),
    gender: str | None = Query(None, pattern="^[MF]$"),
    disease_code: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    sort: str = Query("code"),
    order: str = Query("asc"),
    db: Session = Depends(get_db),
    _: Member = Depends(require_admin),
):
    """필터 조건에 맞는 회원 목록(식별정보 제외). 페이지네이션 및 정렬 지원."""
    this_year = date_type.today().year
    members = filter_members(db, age_min, age_max, gender, disease_code)
    if sort == "risk":
        rank = {"정상": 0, "주의": 1, "위험": 2, "경고": 3}
        lm = _latest_summaries(db, [m.code for m in members])
        latest = {mc: rank.get(rk, -1) for mc, (_dt, rk) in lm.items()}
        members = sorted(members, key=lambda m: latest.get(m.code, -1), reverse=(order == "desc"))
    elif sort == "disease":
        codes = [m.code for m in members]
        dcount, dscore = {}, {}
        if codes:
            for nm, mc in (
                db.query(Disease.name, MemberDisease.member_code)
                .join(MemberDisease, MemberDisease.disease_code == Disease.code)
                .filter(MemberDisease.member_code.in_(codes)).all()
            ):
                dcount[mc] = dcount.get(mc, 0) + 1
                dscore[mc] = dscore.get(mc, 0) + DISEASE_WEIGHT.get(nm, 0)
        members = sorted(members, key=lambda m: (dcount.get(m.code, 0), dscore.get(m.code, 0)),
                         reverse=(order == "desc"))
    else:
        keyfn = {
            "code": lambda m: m.code,
            "age": lambda m: (this_year - m.birth_year) if m.birth_year else -1,
            "gender": lambda m: m.gender or "",
            "joined": lambda m: m.joined_at or date_type.min,
        }.get(sort)
        if keyfn:
            members = sorted(members, key=keyfn, reverse=(order == "desc"))
    total = len(members)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    page_members = members[start:start + page_size]
    page_codes = [m.code for m in page_members]
    latest_map = _latest_summaries(db, page_codes)
    disease_map: dict[int, list] = {}
    if page_codes:
        for nm, mc in (
            db.query(Disease.name, MemberDisease.member_code)
            .join(MemberDisease, MemberDisease.disease_code == Disease.code)
            .filter(MemberDisease.member_code.in_(page_codes)).all()
        ):
            disease_map.setdefault(mc, []).append(nm)
        for names in disease_map.values():
            names.sort(key=lambda n: -DISEASE_WEIGHT.get(n, 0))
    out = []
    for m in page_members:
        latest = latest_map.get(m.code)
        out.append({
            "member_code": m.code,
            "age": (this_year - m.birth_year) if m.birth_year else None,
            "birth_year": m.birth_year,
            "gender": m.gender,
            "joined_at": str(m.joined_at),
            "status": m.status,
            "diseases": disease_map.get(m.code, []),
            "latest_date": str(latest[0]) if latest else None,
            "latest_risk": latest[1] if latest else None,
        })
    return {
        "member_count": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "members": out,
    }


@router.get("/members/{code}")
def member_detail(code: int, db: Session = Depends(get_db), _: Member = Depends(require_admin)):
    """회원 상세 정보(식별정보 제외)."""
    m = db.query(Member).filter(Member.code == code).first()
    if not m:
        raise HTTPException(status_code=404, detail="회원을 찾을 수 없습니다.")
    this_year = date_type.today().year

    summaries = (
        db.query(DailySummary)
        .filter(DailySummary.member_code == code)
        .order_by(DailySummary.date.desc())
        .limit(30)
        .all()
    )
    
    summ_codes = [s.code for s in summaries]
    sn_map: dict[int, list] = {}
    if summ_codes:
        for sc, nm, un, tot in (
            db.query(SummaryNutrient.summary_code, Nutrient.name, Nutrient.unit, SummaryNutrient.total)
            .join(Nutrient, Nutrient.code == SummaryNutrient.nutrient_code)
            .filter(SummaryNutrient.summary_code.in_(summ_codes)).all()
        ):
            sn_map.setdefault(sc, []).append((nm, un, tot))
    summ_out = [{
        "date": str(s.date), "risk": s.risk,
        "nutrients": [{"name": nm, "unit": un, "total": round(tot, 2)} for nm, un, tot in sn_map.get(s.code, [])],
    } for s in summaries]

    records = (
        db.query(DietRecord, Food)
        .join(Food, Food.code == DietRecord.food_code)
        .filter(DietRecord.member_code == code)
        .order_by(DietRecord.recorded_at.desc())
        .limit(50)
        .all()
    )
    
    rec_codes = [r.food_code for r, _ in records]
    fn_map = {}
    if rec_codes:
        for fc, nm, un, amt in (
            db.query(FoodNutrient.food_code, Nutrient.name, Nutrient.unit, FoodNutrient.amount)
            .join(Nutrient, Nutrient.code == FoodNutrient.nutrient_code)
            .filter(FoodNutrient.food_code.in_(rec_codes)).all()
        ):
            fn_map.setdefault(fc, []).append((nm, un, amt))
    rec_out = []
    for r, f in records:
        base = (f.base_amount or 100) or 100
        nuts = [{"name": nm, "unit": un, "amount": round(amt * r.amount / base, 1)} for nm, un, amt in fn_map.get(r.food_code, [])]
        rec_out.append({
            "food_code": r.food_code, "food_name": f.name, "category": f.category,
            "amount": r.amount, "recorded_at": str(r.recorded_at), "nutrients": nuts,
        })

    return {
        "member_code": m.code,
        "age": (this_year - m.birth_year) if m.birth_year else None,
        "birth_year": m.birth_year,
        "gender": m.gender,
        "joined_at": str(m.joined_at),
        "status": m.status,
        "role": m.role,
        "diseases": [{"name": d[0], "registered_at": str(d[1])} for d in _member_diseases(db, code)],
        "summaries": summ_out,
        "records": rec_out,
        "food_categories": food_category_distribution(db, [code], date_type.today() - timedelta(days=13), date_type.today()),
        "notifications": [
            {"type": n.type, "content": n.content, "sent_at": str(n.sent_at), "is_read": n.is_read, "date": str(dt)}
            for n, dt in (
                db.query(Notification, DailySummary.date)
                .join(DailySummary, DailySummary.code == Notification.summary_code)
                .filter(DailySummary.member_code == code)
                .order_by(Notification.sent_at.desc()).all()
            )
        ],
    }
