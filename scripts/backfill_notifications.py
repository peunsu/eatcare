"""
인공적으로 생성한 데이터에 대해 알림을 생성하는 스크립트
실제 데이터가 아니라 인공 데이터이기 때문에 별도로 구현하였음.
"""
import sys
import os
from datetime import date, datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine
from app.services.nutrition import evaluate_risk, _build_message, RISK_TO_NOTI_TYPE

BATCH = 5000


def build_thresholds(cur):
    cur.execute(
        """SELECT md.회원코드, d.질환명, d.영양소코드, n.영양소명, n.단위, d.일일상한값
           FROM MEMBER_DISEASE md
           JOIN DISEASE d  ON d.질환코드 = md.질환코드
           JOIN NUTRIENT n ON n.영양소코드 = d.영양소코드"""
    )
    th = {}
    for mc, dname, nc, nname, unit, limit in cur.fetchall():
        th.setdefault(mc, []).append({
            "disease": dname, "nutrient_code": nc, "nutrient_name": nname,
            "unit": unit, "limit": float(limit),
        })
    return th


def main():
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()

        # 알림 유형 ENUM으로 설정
        cur.execute(
            "ALTER TABLE NOTIFICATION "
            "MODIFY 알림유형 ENUM('NORMAL','WARNING','DANGER','CRITICAL') NOT NULL"
        )
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM NOTIFICATION")
        before = cur.fetchone()[0]

        # 입력값 준비
        thresholds = build_thresholds(cur)

        cur.execute("SELECT 요약코드, 회원코드, 날짜 FROM DAILY_SUMMARY")
        summaries = cur.fetchall()  # (sc, mc, d)

        cur.execute("SELECT 요약코드, 영양소코드, 누적량 FROM SUMMARY_NUTRIENT")
        totals = {}
        for sc, nc, total in cur.fetchall():
            totals.setdefault(sc, {})[nc] = float(total or 0)

        cur.execute("SELECT 요약코드, 알림코드 FROM NOTIFICATION ORDER BY 요약코드, 알림코드")
        existing = {}
        for sc, ncode in cur.fetchall():
            existing.setdefault(sc, []).append(ncode)

        now = datetime.now()

        inserts, updates, deletes = [], [], []
        for sc, mc, d in summaries:
            risk, exceeded = evaluate_risk(thresholds.get(mc, []), totals.get(sc, {}))
            ntype = RISK_TO_NOTI_TYPE[risk]
            content = _build_message(risk, exceeded)
            sent_at = datetime.combine(d + timedelta(days=1), datetime.min.time())
            cur_codes = existing.get(sc, [])
            if sent_at <= now:
                if not cur_codes:
                    inserts.append((sc, ntype, content, sent_at, 0))
                else:
                    updates.append((ntype, content, cur_codes[0]))   # 알림 유형과 내용 업데이트
                    deletes.extend(cur_codes[1:])                    # 중복 제거
            else:
                deletes.extend(cur_codes)

        # DB 반영
        if deletes:
            for i in range(0, len(deletes), BATCH):
                chunk = deletes[i:i + BATCH]
                ph = ",".join(["%s"] * len(chunk))
                cur.execute(f"DELETE FROM NOTIFICATION WHERE 알림코드 IN ({ph})", chunk)
                conn.commit()
        if updates:
            upd = "UPDATE NOTIFICATION SET 알림유형=%s, 알림내용=%s WHERE 알림코드=%s"
            for i in range(0, len(updates), BATCH):
                cur.executemany(upd, updates[i:i + BATCH]); conn.commit()
        if inserts:
            ins = ("INSERT INTO NOTIFICATION (요약코드, 알림유형, 알림내용, 발송일시, 읽음여부) "
                   "VALUES (%s, %s, %s, %s, %s)")
            for i in range(0, len(inserts), BATCH):
                cur.executemany(ins, inserts[i:i + BATCH]); conn.commit()

        # 디버깅을 위해 결과 출력
        cur.execute("SELECT COUNT(*) FROM NOTIFICATION")
        after = cur.fetchone()[0]
        cur.execute("SELECT 알림유형, COUNT(*) FROM NOTIFICATION GROUP BY 알림유형")
        dist = {t: c for t, c in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM DAILY_SUMMARY")
        n_summary = cur.fetchone()[0]

        print(f"요약 {n_summary:,}건, 알림 {before:,} -> {after:,}건 "
              f"(INSERT {len(inserts):,} / UPDATE {len(updates):,} / DELETE {len(deletes):,})")
        print("알림유형 분포:", dist)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
