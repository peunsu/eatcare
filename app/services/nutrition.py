"""핵심 영양소 로직 (제안서 Pseudo Code 구현).

- compute_daily_nutrients : 일일 영양소 누적 섭취량 집계
- evaluate_risk           : Decision Table 기반 위험도 산정
- recompute_daily_summary : 일일요약 upsert + SUMMARY_NUTRIENT 갱신 + 알림 생성
"""
from datetime import datetime, date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    Disease, MemberDisease, Nutrient, DailySummary, SummaryNutrient, Notification,
)

RISK_LEVELS = ["정상", "주의", "위험", "경고"]
RISK_TO_NOTI_TYPE = {"정상": "NORMAL", "주의": "WARNING", "위험": "DANGER", "경고": "CRITICAL"}


def compute_daily_nutrients(db: Session, member_code: int, target_date: date) -> dict:
    """DIET_RECORD → FOOD → FOOD_NUTRIENT 연계로 영양소별 누적 섭취량 계산.
    누적량 = Σ (함량 × 섭취량 / 기준량). 반환: {영양소코드: 누적량}.
    """
    sql = text(
        """
        SELECT fn.영양소코드 AS code,
               SUM(fn.함량 * dr.섭취량 / NULLIF(f.기준량, 0)) AS total
        FROM DIET_RECORD dr
        JOIN FOOD f          ON dr.식품코드 = f.식품코드
        JOIN FOOD_NUTRIENT fn ON fn.식품코드 = f.식품코드
        WHERE dr.회원코드 = :m AND DATE(dr.기록일시) = :d
        GROUP BY fn.영양소코드
        """
    )
    rows = db.execute(sql, {"m": member_code, "d": target_date}).fetchall()
    return {r.code: float(r.total or 0) for r in rows}


def get_member_thresholds(db: Session, member_code: int) -> list:
    """회원의 기저질환별 (질환, 기준영양소, 상한값) 목록."""
    q = (
        db.query(Disease, Nutrient)
        .join(MemberDisease, MemberDisease.disease_code == Disease.code)
        .join(Nutrient, Nutrient.code == Disease.nutrient_code)
        .filter(MemberDisease.member_code == member_code)
        .all()
    )
    return [
        {
            "disease": d.name,
            "nutrient_code": d.nutrient_code,
            "nutrient_name": n.name,
            "unit": n.unit,
            "limit": d.daily_limit,
        }
        for d, n in q
    ]


def evaluate_risk(thresholds: list, totals: dict):
    """기저질환별 기준 영양소가 상한값을 초과한 개수로 위험도 결정.
    0=정상, 1=주의, 2=위험, 3=경고. 반환: (위험도, 초과목록).
    """
    exceeded = []
    for t in thresholds:
        intake = totals.get(t["nutrient_code"], 0.0)
        if intake > t["limit"]:
            exceeded.append({
                "disease": t["disease"],
                "nutrient_name": t["nutrient_name"],
                "unit": t["unit"],
                "intake": round(intake, 2),
                "limit": t["limit"],
            })
    risk = RISK_LEVELS[min(len(exceeded), 3)]
    return risk, exceeded


def _build_message(risk: str, exceeded: list) -> str:
    if not exceeded:                        # 위험도 정상 — 초과 없음
        return "오늘 섭취한 영양소가 모두 일일 상한 이내입니다. (위험도: 정상)"
    parts = [f"{e['nutrient_name']} {e['intake']}{e['unit']}(상한 {e['limit']}{e['unit']})" for e in exceeded]
    return "일일 상한 초과: " + ", ".join(parts)


def recompute_daily_summary(db: Session, member_code: int, target_date: date,
                            notified_at: datetime | None = None,
                            emit_notifications: bool = True) -> DailySummary:
    """특정 날짜의 누적/위험도/요약을 재계산하여 저장. 멱등.
    notified_at: 신규 알림 발송일시(미지정 시 현재 시각).
    emit_notifications: False면 요약 값만 갱신하고 알림은 건드리지 않음(조회 시 사용).
    """
    totals = compute_daily_nutrients(db, member_code, target_date)
    thresholds = get_member_thresholds(db, member_code)
    risk, exceeded = evaluate_risk(thresholds, totals)

    # DAILY_SUMMARY upsert (회원코드+날짜 UNIQUE)
    summary = (
        db.query(DailySummary)
        .filter(DailySummary.member_code == member_code, DailySummary.date == target_date)
        .first()
    )
    if summary is None:
        summary = DailySummary(member_code=member_code, date=target_date, risk=risk)
        db.add(summary)
        db.flush()
    else:
        summary.risk = risk

    # SUMMARY_NUTRIENT 재구성
    db.query(SummaryNutrient).filter(SummaryNutrient.summary_code == summary.code).delete()
    for code, total in totals.items():
        db.add(SummaryNutrient(summary_code=summary.code, nutrient_code=code, total=round(total, 4)))

    # 알림: 자정 배치에서 그날 일일요약을 기준으로 위험도와 무관하게 1건 발송.
    # (통째 삭제/재생성하지 않고 읽음·발송시각 보존 → 재실행에 안전)
    if emit_notifications:
        existing = (
            db.query(Notification)
            .filter(Notification.summary_code == summary.code)
            .order_by(Notification.code)
            .all()
        )
        ntype = RISK_TO_NOTI_TYPE[risk]
        content = _build_message(risk, exceeded)
        if not existing:                   # 신규 통지(1회 생성)
            db.add(Notification(
                summary_code=summary.code, type=ntype, content=content,
                sent_at=notified_at or datetime.now(), is_read=False,
            ))
        else:                              # 내용/등급만 최신화, 읽음·발송시각 보존
            keep = existing[0]
            keep.type = ntype
            keep.content = content
            for n in existing[1:]:
                db.delete(n)

    db.commit()
    db.refresh(summary)
    return summary
