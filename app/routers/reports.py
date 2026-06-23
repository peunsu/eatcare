from datetime import date as date_type, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Member, Nutrient, Disease, DailySummary, SummaryNutrient
from app.schemas import DailyReportOut, NutrientStatus
from app.auth import get_current_member
from app.services.nutrition import (
    compute_daily_nutrients, get_member_thresholds, evaluate_risk, recompute_daily_summary,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/trend")
def trend(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db),
          me: Member = Depends(get_current_member)):
    """최근 N일 영양소 누적량/위험도 추이."""
    end = date_type.today()
    start = end - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]

    summaries = (
        db.query(DailySummary)
        .filter(DailySummary.member_code == me.code,
                DailySummary.date >= start, DailySummary.date <= end)
        .all()
    )
    by_date = {s.date: s for s in summaries}
    sdate = {s.code: s.date for s in summaries}
    totals = {}  # (date, nutrient_code) -> total
    if summaries:
        for sn in db.query(SummaryNutrient).filter(
                SummaryNutrient.summary_code.in_([s.code for s in summaries])).all():
            totals[(sdate[sn.summary_code], sn.nutrient_code)] = sn.total

    limit_by = {d.nutrient_code: d.daily_limit for d in db.query(Disease).all()}
    nutrients = []
    for n in db.query(Nutrient).order_by(Nutrient.code).all():
        nutrients.append({
            "code": n.code, "name": n.name, "unit": n.unit, "limit": limit_by.get(n.code),
            "totals": [round(totals.get((d, n.code), 0.0), 2) for d in dates],
        })
    risks = [by_date[d].risk if d in by_date else "정상" for d in dates]
    return {"dates": [str(d) for d in dates], "nutrients": nutrients, "risks": risks}


@router.get("/daily", response_model=DailyReportOut)
def daily_report(date: date_type | None = None, db: Session = Depends(get_db),
                 me: Member = Depends(get_current_member)):
    target = date or date_type.today()
    recompute_daily_summary(db, me.code, target, emit_notifications=False)

    totals = compute_daily_nutrients(db, me.code, target)
    thresholds = get_member_thresholds(db, me.code)
    risk, _ = evaluate_risk(thresholds, totals)

    std_limit = {d.nutrient_code: d.daily_limit for d in db.query(Disease).all()}
    monitored = {t["nutrient_code"] for t in thresholds}
    nut_by_code = {n.code: n for n in db.query(Nutrient).all()}

    codes = set(totals) | set(std_limit)
    nutrients = []
    for code in sorted(codes):
        n = nut_by_code.get(code)
        if not n:
            continue
        total = round(totals.get(code, 0.0), 2)
        limit = std_limit.get(code)
        nutrients.append(NutrientStatus(
            nutrient_name=n.name, unit=n.unit, total=total,
            limit=limit, exceeded=(limit is not None and total > limit),
            monitored=(code in monitored),
        ))
    return DailyReportOut(date=target, risk=risk, nutrients=nutrients)
