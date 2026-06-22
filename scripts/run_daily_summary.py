"""매일 자정 배치: 전 활성 회원의 '전날' 일일요약·위험도·알림을 확정한다.

cron 예) 0 0 * * *  → 자정에 어제치 요약을 마감. 앱 사용/조회 여부와 무관하게 알림 보장.
기존 recompute_daily_summary 로직을 그대로 재사용(위험도 규칙 단일 소스).
"""
import sys
import os
from datetime import date, timedelta, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Member
from app.services.nutrition import recompute_daily_summary


def main(target: date | None = None):
    target = target or (date.today() - timedelta(days=1))  # 어제(완료된 하루)
    db = SessionLocal()
    try:
        codes = [
            m.code for m in db.query(Member)
            .filter(Member.role == "USER", Member.status == "ACTIVE").all()
        ]
    finally:
        db.close()

    risk = {"정상": 0, "주의": 0, "위험": 0, "경고": 0}
    db = SessionLocal()
    try:
        for code in codes:
            s = recompute_daily_summary(db, code, target)  # emit_notifications=True, sent_at=now(≈자정)
            risk[s.risk] = risk.get(s.risk, 0) + 1
    finally:
        db.close()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {target} 일일요약 확정 — 회원 {len(codes)}명, 위험도 {risk}")


if __name__ == "__main__":
    # 인자로 날짜 지정 가능(YYYY-MM-DD), 없으면 어제
    tgt = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    main(tgt)
