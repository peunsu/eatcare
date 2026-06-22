"""성능 인덱스 추가(멱등). 라이브 DB에 1회 실행."""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine

# 멱등 DDL (MariaDB 10.5+: IF NOT EXISTS 지원)
# 검색명 = 공백 제거 STORED 생성 컬럼 → 검색 시 REPLACE 재계산 없이 인덱스 스캔
STATEMENTS = [
    "ALTER TABLE FOOD ADD COLUMN IF NOT EXISTS 검색명 VARCHAR(255) AS (REPLACE(식품명, ' ', '')) STORED",
    "CREATE INDEX IF NOT EXISTS idx_food_category ON FOOD(대분류)",
    "CREATE INDEX IF NOT EXISTS idx_food_search ON FOOD(검색명)",
]


def main():
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        for ddl in STATEMENTS:
            cur.execute(ddl)
            raw.commit()
            print(f"적용: {ddl[:60]}...")
        cur.execute("SHOW INDEX FROM FOOD")
        idx = sorted({row[2] for row in cur.fetchall()})
        print(f"FOOD 인덱스: {idx}")
    finally:
        raw.close()


if __name__ == "__main__":
    main()
