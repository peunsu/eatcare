"""데모 데이터: 다양한 연령/성별/질환의 회원 + 식단기록 → 위험도 분포 생성. 멱등."""
import sys
import os
from datetime import date, datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal
from app.models import Member, Disease, MemberDisease, DietRecord, Nutrient
from app.auth import hash_password
from app.services.nutrition import recompute_daily_summary

PW = hash_password("demo1234")
DOMAIN = "@demo.local"

# (이름, 출생년도, 성별, [질환명...], {영양소명: 목표배수(상한 대비)})
PEOPLE = [
    ("김영희", 1975, "F", ["당뇨"],            {"당류": 1.5}),                 # 1초과 → 주의
    ("정대현", 1955, "M", ["당뇨", "고혈압"],  {"당류": 1.4, "나트륨": 1.6}),   # 2초과 → 위험
    ("이철수", 1968, "M", ["고혈압", "고지혈증"], {"나트륨": 1.5, "지방": 1.3}), # 2초과 → 위험
    ("박민지", 1980, "F", ["고혈압"],          {"나트륨": 0.6}),               # 미만 → 정상
    ("한지훈", 1978, "M", ["고지혈증"],        {"지방": 1.4}),                 # 1초과 → 주의
    ("최수진", 1990, "F", [],                  {"당류": 0.5}),                 # 질환없음 → 정상
]


def top_food_for(db, nutrient_code):
    """해당 영양소 함량이 높은 식품 1건 (식품코드, 함량, 기준량)."""
    row = db.execute(text(
        """SELECT fn.식품코드 AS code, fn.함량 AS amt, f.기준량 AS base
           FROM FOOD_NUTRIENT fn JOIN FOOD f ON f.식품코드 = fn.식품코드
           WHERE fn.영양소코드 = :nc AND fn.함량 > 0
           ORDER BY fn.함량 DESC LIMIT 1"""), {"nc": nutrient_code}).fetchone()
    return row


def main():
    db = SessionLocal()
    try:
        # 영양소명/질환명 → 코드, 상한
        nut = {n.name: n.code for n in db.query(Nutrient).all()}
        dis = {d.name: d for d in db.query(Disease).all()}

        # 영양소별 대표 식품 캐시
        food_for = {name: top_food_for(db, code) for name, code in nut.items()}

        # 기존 데모 삭제(멱등)
        for m in db.query(Member).filter(Member.email.like("%" + DOMAIN)).all():
            db.delete(m)
        db.commit()

        today = date.today()
        for name, birth, gender, diseases, targets in PEOPLE:
            email = name + DOMAIN
            m = Member(name=name, email=email, password=PW, birth_year=birth,
                       gender=gender, joined_at=today, role="USER", status="ACTIVE")
            db.add(m); db.flush()
            for dn in diseases:
                db.add(MemberDisease(member_code=m.code, disease_code=dis[dn].code, registered_at=today))
            # 식단기록: 영양소별 목표배수에 맞춰 섭취량 계산
            for nutri_name, factor in targets.items():
                f = food_for[nutri_name]
                d = dis_by_nutrient(dis, nut[nutri_name])
                threshold = d.daily_limit if d else 50.0
                per_unit = f.amt / f.base                      # 단위 g당 함량
                amount = (threshold * factor) / per_unit        # 목표 누적량 달성 섭취량(g)
                db.add(DietRecord(member_code=m.code, food_code=f.code,
                                  amount=round(amount, 1), recorded_at=datetime.now()))
            db.commit()
            summary = recompute_daily_summary(db, m.code, today)
            print(f"  {name} ({birth}/{gender}) {diseases} → 위험도 {summary.risk}")

        print("\n=== 데모 데이터 생성 완료 (비밀번호 모두 demo1234) ===")
    finally:
        db.close()


def dis_by_nutrient(dis_map, nutrient_code):
    for d in dis_map.values():
        if d.nutrient_code == nutrient_code:
            return d
    return None


if __name__ == "__main__":
    main()
