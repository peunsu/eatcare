"""성능 인덱스 추가(멱등). 라이브 DB에 1회 실행."""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine

# 식품명에서 공백을 제거하여 검색명 칼럼 생성 -> 검색 시 인덱스로 사용
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
