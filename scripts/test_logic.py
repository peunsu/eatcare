"""핵심 로직 검증: 당뇨+고혈압 회원이 당류>50g & 나트륨>2000mg 섭취 → '위험' + DANGER 알림."""
import sys
import os
from datetime import date, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Member, Disease, MemberDisease, DietRecord, Notification, DailySummary, SummaryNutrient
from app.services.nutrition import recompute_daily_summary
from app.auth import hash_password

TEST_EMAIL = "test_logic@nutrition.local"
FOOD_CODE = "D202-120000000-1180"  # 당류 5.75/100g, 나트륨 321/100g
AMOUNT = 1000.0  # g → 당류 57.5, 나트륨 3210


def cleanup(db):
    m = db.query(Member).filter(Member.email == TEST_EMAIL).first()
    if m:
        db.delete(m)  # cascade로 식단/요약/알림 삭제
        db.commit()


def main():
    db = SessionLocal()
    try:
        cleanup(db)
        # 회원 생성
        m = Member(name="테스트", email=TEST_EMAIL, password=hash_password("x"),
                   birth_year=1980, gender="F", joined_at=date.today(), role="USER", status="ACTIVE")
        db.add(m); db.flush()
        # 당뇨 + 고혈압 등록
        for dname in ("당뇨", "고혈압"):
            d = db.query(Disease).filter(Disease.name == dname).first()
            db.add(MemberDisease(member_code=m.code, disease_code=d.code, registered_at=date.today()))
        # 식단기록
        db.add(DietRecord(member_code=m.code, food_code=FOOD_CODE, amount=AMOUNT, recorded_at=datetime.now()))
        db.commit()

        today = date.today()
        summary = recompute_daily_summary(db, m.code, today)

        totals = {sn.nutrient.name: round(sn.total, 2) for sn in
                  db.query(SummaryNutrient).filter(SummaryNutrient.summary_code == summary.code).all()}
        notis = db.query(Notification).filter(Notification.summary_code == summary.code).all()

        print("누적 섭취량:", totals)
        print("위험도:", summary.risk)
        print("알림:", [(n.type, n.content) for n in notis])

        assert totals.get("당류", 0) > 50, "당류 초과 실패"
        assert totals.get("나트륨", 0) > 2000, "나트륨 초과 실패"
        assert summary.risk == "위험", f"위험도 기대 '위험' 실제 '{summary.risk}'"
        assert len(notis) == 1 and notis[0].type == "DANGER", "DANGER 알림 1건 기대"
        print("\n✅ 검증 통과: 당류/나트륨 초과 2건 → '위험' + DANGER 알림")
    finally:
        cleanup(db)
        db.close()


if __name__ == "__main__":
    main()
