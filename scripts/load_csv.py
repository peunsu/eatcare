"""CSV 로드"""
import sys
import os
import re
import math

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine
from app.models import Nutrient

CSV_PATH = os.path.expanduser(
    "~/workspace/data/전국통합식품영양성분정보_음식_표준데이터.csv"
)

NUTRIENT_COLS = {"당류": "당류(g)", "나트륨": "나트륨(mg)", "지방": "지방(g)"}

AMOUNT_RE = re.compile(r"([\d.]+)\s*([^\d.\s]+)?")


def parse_base_amount(raw):
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return 100.0, "g"
    m = AMOUNT_RE.search(str(raw).strip())
    if not m:
        return 100.0, "g"
    amount = float(m.group(1))
    unit = (m.group(2) or "g").strip()
    return amount, unit


def main():
    db = SessionLocal()
    try:
        nut_code = {n.name: n.code for n in db.query(Nutrient).all()}
    finally:
        db.close()
    for name in NUTRIENT_COLS:
        if name not in nut_code:
            raise SystemExit(f"NUTRIENT '{name}' 가 DB에 없습니다.")

    print(f"CSV 읽는 중: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, encoding="cp949", dtype=str)
    print(f"  총 {len(df):,} 행")

    foods = {}        # 식품코드 -> (식품명, 기준량, 기준단위, 대분류)
    food_nutrients = []  # (식품코드, 영양소코드, 함량)

    for _, row in df.iterrows():
        code = (row.get("식품코드") or "").strip()
        name = (row.get("식품명") or "").strip()
        if not code or not name:
            continue
        if code not in foods:
            amount, unit = parse_base_amount(row.get("영양성분함량기준량"))
            category = (row.get("식품대분류명") or "").strip() or None
            foods[code] = (name, amount, unit, category)
        for nut_name, col in NUTRIENT_COLS.items():
            val = row.get(col)
            if val is None or str(val).strip() == "":
                continue
            try:
                amt = float(val)
            except (ValueError, TypeError):
                continue
            if math.isnan(amt):
                continue
            food_nutrients.append((code, nut_code[nut_name], amt))

    print(f"  FOOD: {len(foods):,} 건, FOOD_NUTRIENT: {len(food_nutrients):,} 건")

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.executemany(
            "INSERT IGNORE INTO FOOD (식품코드, 식품명, 기준량, 기준단위, 대분류) VALUES (%s,%s,%s,%s,%s)",
            [(c, n, a, u, cat) for c, (n, a, u, cat) in foods.items()],
        )
        cur.executemany(
            "INSERT IGNORE INTO FOOD_NUTRIENT (식품코드, 영양소코드, 함량) VALUES (%s,%s,%s)",
            food_nutrients,
        )
        raw.commit()
    finally:
        raw.close()

    print("=== 저장 완료 ===")


if __name__ == "__main__":
    main()
