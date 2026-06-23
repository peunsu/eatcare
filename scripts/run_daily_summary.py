"""매일 자정에 일일 요약 생성하는 스크립트. cron job 에서 실행됨."""
import sys
import os
from datetime import date, timedelta, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Member
from app.services.nutrition import recompute_daily_summary


def main(target: date | None = None):
    target = target or (date.today() - timedelta(days=1))
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
            s = recompute_daily_summary(db, code, target)  # emit_notifications=True, sent_at=now
            risk[s.risk] = risk.get(s.risk, 0) + 1
    finally:
        db.close()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {target} 일일요약 확정 — 회원 {len(codes)}명, 위험도 {risk}")


if __name__ == "__main__":
    tgt = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None
    main(tgt)
