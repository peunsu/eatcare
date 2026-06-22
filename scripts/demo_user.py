"""데모 사용자 계정(데이터 포함) 1명 생성. 멱등(demo@nutrition.local 재생성).

gen_data 의 끼니 템플릿/목표 섭취 모델을 재사용해 최근 DAYS일치 식단을 채운다.
"""
import sys
import os
import random
from datetime import date, datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, engine
from app.models import Member, Disease, MemberDisease
from app.auth import hash_password
from app.services.nutrition import recompute_daily_summary
import gen_data as G

EMAIL = "demo@nutrition.local"
PASSWORD = "demo1234"
NAME = "데모사용자"
DAYS = G.DAYS                       # 최근 120일
DEMO_DISEASES = ["당뇨", "고혈압"]  # 위험도 단계가 다양하게 나오도록


def main():
    today = date.today()
    db = SessionLocal()
    try:
        old = db.query(Member).filter(Member.email == EMAIL).first()
        if old:
            db.delete(old); db.commit()
            print("기존 데모 계정 정리")
        m = Member(name=NAME, email=EMAIL, password=hash_password(PASSWORD),
                   birth_year=today.year - 45, gender="M",
                   joined_at=today - timedelta(days=DAYS), role="USER", status="ACTIVE")
        db.add(m); db.flush()
        dmap = {d.name: d for d in db.query(Disease).all()}
        for dn in DEMO_DISEASES:
            if dn in dmap:
                db.add(MemberDisease(member_code=m.code, disease_code=dmap[dn].code,
                                     registered_at=today - timedelta(days=DAYS)))
        db.commit()
        code = m.code
    finally:
        db.close()

    # 식단 기록 생성 (매일 성실하게 기록하는 데모)
    conn = engine.raw_connection()
    try:
        name2code, lim = G.load_nutrients(conn)
        pools = G.build_food_pools(conn, list(lim.keys()))
        mbase = G.member_baseline(lim, name2code)
        cur = conn.cursor()
        ins = "INSERT INTO DIET_RECORD (회원코드, 식품코드, 섭취량, 기록일시) VALUES (%s, %s, %s, %s)"
        buf, total = [], 0
        for k in range(DAYS):
            day = today - timedelta(days=k)
            meals = ["점심", "저녁"]
            if random.random() < 0.85: meals.insert(0, "아침")
            if random.random() < 0.4: meals.append("간식")
            for meal, fcode, amt, _vec, _base in G.gen_day(pools, lim, mbase, meals):
                buf.append((code, fcode, amt, G.meal_ts(day, meal))); total += 1
        cur.executemany(ins, buf); conn.commit()
        print(f"데모 식단 기록 {total}건 생성")
    finally:
        conn.close()

    # 일일요약/위험도/알림 재계산 (해당 회원 120일)
    db = SessionLocal()
    try:
        risk = {"정상": 0, "주의": 0, "위험": 0, "경고": 0}
        for k in range(DAYS):
            day = today - timedelta(days=k)
            # 알림 발송일시를 해당 날짜 저녁으로 지정(시간순 정렬이 맞도록)
            notified = datetime.combine(day, datetime.min.time()) + timedelta(hours=21)
            s = recompute_daily_summary(db, code, day, notified_at=notified)
            risk[s.risk] = risk.get(s.risk, 0) + 1
        print("위험도 분포:", risk)
    finally:
        db.close()
    print(f"\n=== 데모 사용자 계정: {EMAIL} / {PASSWORD} ===")


if __name__ == "__main__":
    main()
