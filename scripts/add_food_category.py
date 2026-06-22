"""기존 FOOD에 대분류 컬럼 추가 + CSV(식품대분류명)로 백필. 멱등."""
import sys
import os

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine

CSV_PATH = os.path.expanduser(
    "~/workspace/data/전국통합식품영양성분정보_음식_표준데이터.csv"
)


def main():
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        # 컬럼 추가 (이미 있으면 무시)
        cur.execute("ALTER TABLE FOOD ADD COLUMN IF NOT EXISTS 대분류 VARCHAR(50)")
        raw.commit()

        df = pd.read_csv(CSV_PATH, encoding="cp949", dtype=str)
        seen = {}
        for _, row in df.iterrows():
            code = (row.get("식품코드") or "").strip()
            cat = (row.get("식품대분류명") or "").strip()
            if code and code not in seen:
                seen[code] = cat or None
        print(f"CSV 식품 {len(seen):,}건 분류 매핑")

        cur.executemany("UPDATE FOOD SET 대분류=%s WHERE 식품코드=%s",
                        [(cat, code) for code, cat in seen.items()])
        raw.commit()

        cur.execute("SELECT COUNT(*) FROM FOOD WHERE 대분류 IS NOT NULL")
        filled = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM FOOD")
        total = cur.fetchone()[0]
        print(f"대분류 채워진 FOOD: {filled:,} / {total:,}")
    finally:
        raw.close()


if __name__ == "__main__":
    main()
