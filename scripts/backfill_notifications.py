"""기존 인공 데이터에 변경된 알림 로직을 반영(backfill).

변경된 로직(§10.2.3): 자정 배치가 그날 일일요약을 기준으로 **위험도와 무관하게 1건**
알림을 발송한다(정상=NORMAL 포함). 기존 데이터는 구(舊) 로직으로 생성되어 위험도가
'정상'이 아닌 요약에만 알림이 있으므로, 다음과 같이 정합화한다.

각 DAILY_SUMMARY(요약)에 대해 (요약 날짜의 다음날 00:00 = 발송 시각):
  - 발송 시각이 현재 이전이고 알림이 없으면  → INSERT (위험도별 유형)
  - 알림이 이미 있으면                       → 알림유형·알림내용만 UPDATE(읽음·발송시각 보존),
                                               중복분(>1)은 삭제
  - 발송 시각이 미래(=아직 자정 배치 전, 오늘 요약)면 → 알림 삭제(아직 미발송)

위험도/메시지/유형은 앱 로직(evaluate_risk·_build_message·RISK_TO_NOTI_TYPE)을 그대로
재사용하므로 앱 실시간 결과와 단일 진실 소스를 유지한다. 멱등(여러 번 실행해도 동일).

실행:  python scripts/backfill_notifications.py
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

        # 0) 알림유형 ENUM 에 NORMAL 보장(멱등) — 정상 알림 삽입 전제
        cur.execute(
            "ALTER TABLE NOTIFICATION "
            "MODIFY 알림유형 ENUM('NORMAL','WARNING','DANGER','CRITICAL') NOT NULL"
        )
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM NOTIFICATION")
        before = cur.fetchone()[0]

        # 1) 입력 적재
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
            if sent_at <= now:                      # 자정 배치가 지난 날 → 알림 1건 보장
                if not cur_codes:
                    inserts.append((sc, ntype, content, sent_at, 0))
                else:
                    updates.append((ntype, content, cur_codes[0]))   # 유형·내용만(읽음·시각 보존)
                    deletes.extend(cur_codes[1:])                    # 중복 제거
            else:                                   # 아직 미발송(오늘 요약 등)
                deletes.extend(cur_codes)

        # 2) 반영(배치)
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

        # 3) 결과 요약
        cur.execute("SELECT COUNT(*) FROM NOTIFICATION")
        after = cur.fetchone()[0]
        cur.execute("SELECT 알림유형, COUNT(*) FROM NOTIFICATION GROUP BY 알림유형")
        dist = {t: c for t, c in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM DAILY_SUMMARY")
        n_summary = cur.fetchone()[0]

        print(f"요약 {n_summary:,}건 · 알림 {before:,} → {after:,}건 "
              f"(INSERT {len(inserts):,} / UPDATE {len(updates):,} / DELETE {len(deletes):,})")
        print("알림유형 분포:", dist)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
