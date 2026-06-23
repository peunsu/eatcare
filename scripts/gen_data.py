"""가상 데이터 생성"""
import sys
import os
import math
import random
from datetime import date, datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal, engine
from app.models import Member, Disease, MemberDisease
from app.auth import hash_password
from app.services.nutrition import evaluate_risk, _build_message, RISK_TO_NOTI_TYPE

random.seed(7)

N_MEMBERS = 400
DAYS = 120
DOMAIN = "@sample.local"
PASSWORD = "sample1234"
BATCH = 5000


BASE_MED = {"당류": 0.82, "나트륨": 0.40, "지방": 1.85}  # 중앙값
SIGMA_M = 0.30   # 회원 간 편차
SIGMA_D = 0.45   # 같은 회원의 일별 편차
AMT_MIN, AMT_MAX = 15.0, 700.0

SURNAMES = list("김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남")
GIVEN1 = list("민서지현예준도윤하은수영태광동재성진우경혜")
GIVEN2 = list("준호서연우진아윤지현수빈영철민혁은정원규아")


def rand_name():
    return random.choice(SURNAMES) + random.choice(GIVEN1) + random.choice(GIVEN2)


# 대분류 매핑
SLOT_CATS = {
    "주식": ["밥류", "면 및 만두류", "죽 및 스프류"],
    "국물": ["국 및 탕류", "찌개 및 전골류"],
    "반찬": ["구이류", "볶음류", "조림류", "튀김류", "전·적 및 부침류", "찜류",
            "나물·숙채류", "생채·무침류", "김치류", "장아찌·절임류", "젓갈류", "수·조·어·육류"],
    "빵간식": ["빵 및 과자류"],
    "음료": ["음료 및 차류"],
    "유제품": ["유제품류 및 빙과류"],
}
MEAL_HOURS = {"아침": (6, 9), "점심": (11, 14), "저녁": (17, 21), "간식": (14, 17)}
DISEASE_MULT = {"고혈압": 0.95, "고지혈증": 0.85, "당뇨": 0.7}


def load_nutrients(conn):
    """{영양소명: 코드}, {코드: 상한값}."""
    cur = conn.cursor()
    cur.execute("SELECT 영양소코드, 영양소명 FROM NUTRIENT")
    name2code = {nm: code for code, nm in cur.fetchall()}
    cur.execute("SELECT 영양소코드, 일일상한값 FROM DISEASE")
    lim = {code: float(v) for code, v in cur.fetchall()}
    return name2code, lim


def build_food_pools(conn, nut_codes):
    """{분류: [(식품코드, 기준량, {영양소코드: 함량}), ...]}."""
    cur = conn.cursor()
    cur.execute(
        """SELECT f.식품코드, f.기준량, f.대분류 FROM FOOD f
           WHERE f.대분류 IS NOT NULL
             AND EXISTS (SELECT 1 FROM FOOD_NUTRIENT fn WHERE fn.식품코드 = f.식품코드)"""
    )
    base_cat = {code: (float(base or 100), cat) for code, base, cat in cur.fetchall()}
    in_clause = ",".join(str(int(c)) for c in nut_codes)
    cur.execute(f"SELECT 식품코드, 영양소코드, 함량 FROM FOOD_NUTRIENT WHERE 영양소코드 IN ({in_clause})")
    vecs = {}
    for code, nc, amt in cur.fetchall():
        vecs.setdefault(code, {})[nc] = float(amt or 0)
    used = {c for cats in SLOT_CATS.values() for c in cats}
    pools = {}
    for code, (base, cat) in base_cat.items():
        if cat in used:
            pools.setdefault(cat, []).append((code, base, vecs.get(code, {})))
    return {c: v for c, v in pools.items() if v}


def pick(pools, slot):
    cats = [c for c in SLOT_CATS[slot] if pools.get(c)]
    if not cats:
        return None
    code, base, vec = random.choice(pools[random.choice(cats)])
    return (code, base, vec)


def meal_slots(meal):
    """식사 구성 템플릿"""
    slots = []
    if meal == "아침":
        if random.random() < 0.5:
            slots.append("주식")
            if random.random() < 0.6: slots.append("국물")
            slots.append("반찬")
        else:
            slots.append("빵간식")
            if random.random() < 0.6: slots.append("유제품")
            if random.random() < 0.5: slots.append("음료")
    elif meal in ("점심", "저녁"):
        slots.append("주식")
        if random.random() < 0.55: slots.append("국물")
        slots += ["반찬"] * random.randint(1, 2)
        if random.random() < 0.3: slots.append("음료")
    else:  # 간식
        for _ in range(random.randint(1, 2)):
            slots.append(random.choices(["빵간식", "음료", "유제품"], weights=[5, 4, 3])[0])
    return slots


def dominant(vec, base, lim):
    """상한값 대비 섭취량이 가장 높은 영양소코드"""
    best, best_load = None, 0.0
    for nc, L in lim.items():
        a = vec.get(nc, 0.0)
        if a <= 0:
            continue
        load = (a / base) / L
        if load > best_load:
            best_load, best = load, nc
    return best


def gen_day(pools, lim, mbase, meals):
    """[(meal, code, amount, vec, base)]."""
    items = []  # [meal, code, base, vec]
    for meal in meals:
        for slot in meal_slots(meal):
            p = pick(pools, slot)
            if p:
                items.append([meal, p[0], p[1], p[2]])
    if not items:
        return []
    # 영양소별 당일 목표 섭취량
    T = {nc: lim[nc] * mbase[nc] * random.lognormvariate(0, SIGMA_D) for nc in lim}
    # 식품을 영양소 그룹으로 분배
    groups = {nc: [] for nc in lim}
    none = []
    for it in items:
        g = dominant(it[3], it[2], lim)
        (groups[g] if g is not None else none).append(it)
    out = []
    for nc, gitems in groups.items():
        if not gitems:
            continue
        ws = [random.uniform(0.5, 1.5) for _ in gitems]
        sw = sum(ws)
        for it, w in zip(gitems, ws):
            vn = it[3].get(nc, 0.0)
            contrib = (w / sw) * T[nc]
            amt = contrib * it[2] / vn if vn > 0 else random.uniform(30, 120)
            amt = round(min(max(amt, AMT_MIN), AMT_MAX), 1)
            out.append((it[0], it[1], amt, it[3], it[2]))
    for it in none:
        out.append((it[0], it[1], round(random.uniform(30, 120), 1), it[3], it[2]))
    return out


def member_baseline(lim, name2code):
    """회원별 영양소 기준치. {영양소코드: 배수}."""
    mb = {}
    for name, code in name2code.items():
        if code in lim:
            mb[code] = random.lognormvariate(math.log(BASE_MED.get(name, 0.8)), SIGMA_M)
    return mb


def meal_ts(day, meal):
    lo, hi = MEAL_HOURS[meal]
    return datetime.combine(day, datetime.min.time()) + timedelta(
        hours=random.randint(lo, hi), minutes=random.randint(0, 59))


def run_stats():
    conn = engine.raw_connection()
    try:
        name2code, lim = load_nutrients(conn)
        pools = build_food_pools(conn, list(lim.keys()))
    finally:
        conn.close()
    code2name = {c: n for n, c in name2code.items()}
    today = date.today()
    days = [today - timedelta(days=k) for k in range(DAYS)]
    samples = {nc: [] for nc in lim}      # (회원,날짜) 총섭취량
    n_days = 0
    for _ in range(N_MEMBERS):
        mbase = member_baseline(lim, name2code)
        adherence = random.uniform(0.5, 0.9)
        for day in days:
            if random.random() > adherence:
                continue
            meals = []
            if random.random() < 0.75: meals.append("아침")
            if random.random() < 0.90: meals.append("점심")
            if random.random() < 0.92: meals.append("저녁")
            if random.random() < 0.35: meals.append("간식")
            recs = gen_day(pools, lim, mbase, meals)
            if not recs:
                continue
            n_days += 1
            tot = {nc: 0.0 for nc in lim}
            for _meal, _code, amt, vec, base in recs:
                for nc in lim:
                    a = vec.get(nc, 0.0)
                    if a:
                        tot[nc] += a * amt / base
            for nc in lim:
                samples[nc].append(tot[nc])

    def pct(vals, q):
        s = sorted(vals)
        return s[min(len(s) - 1, int(q * len(s)))]

    print(f"시뮬레이션: {n_days:,} (회원,날짜)")
    print(f"{'영양소':<8}{'상한':>8}{'평균%':>8}{'중앙%':>8}{'p90%':>8}{'초과%':>8}")
    for nc, L in lim.items():
        v = samples[nc]
        mean = sum(v) / len(v)
        over = sum(1 for x in v if x > L) / len(v) * 100
        print(f"{code2name[nc]:<8}{L:>8.0f}{mean/L*100:>8.0f}{pct(v,0.5)/L*100:>8.0f}"
              f"{pct(v,0.9)/L*100:>8.0f}{over:>8.0f}")


def create_members(db):
    """멤버 생성"""
    diseases = db.query(Disease).all()
    pw = hash_password(PASSWORD)
    today = date.today()
    buckets = [(19, 29, 15), (30, 39, 20), (40, 49, 22), (50, 59, 22), (60, 69, 14), (70, 80, 7)]
    ages_lohi = [(a, b) for a, b, _ in buckets]
    weights = [w for _, _, w in buckets]
    for i in range(N_MEMBERS):
        lo, hi = random.choices(ages_lohi, weights=weights)[0]
        age = random.randint(lo, hi)
        birth = today.year - age
        gender = random.choice(["M", "F"])
        status = "INACTIVE" if random.random() < 0.05 else "ACTIVE"
        joined = today - timedelta(days=random.randint(0, 730))
        m = Member(name=rand_name(), email=f"user{i+1:03d}{DOMAIN}", password=pw,
                   birth_year=birth, gender=gender, joined_at=joined,
                   role="USER", status=status)
        db.add(m); db.flush()
        latent = 1 / (1 + math.exp(-(0.06 * (age - 50) + random.gauss(0, 1))))
        for d in diseases:
            p = min(0.85, latent * DISEASE_MULT.get(d.name, 0.8))
            if random.random() < p:
                reg = joined + timedelta(days=random.randint(0, max(1, (today - joined).days)))
                db.add(MemberDisease(member_code=m.code, disease_code=d.code, registered_at=reg))
    db.commit()
    return N_MEMBERS


def gen_records(conn, member_ids, name2code, lim):
    """식단 기록 생성"""
    cur = conn.cursor()
    pools = build_food_pools(conn, list(lim.keys()))
    today = date.today()
    days = [today - timedelta(days=k) for k in range(DAYS)]
    ins = "INSERT INTO DIET_RECORD (회원코드, 식품코드, 섭취량, 기록일시) VALUES (%s, %s, %s, %s)"
    buf, total = [], 0
    for mid in member_ids:
        mbase = member_baseline(lim, name2code)
        adherence = random.uniform(0.5, 0.9)
        for day in days:
            if random.random() > adherence:
                continue
            meals = []
            if random.random() < 0.75: meals.append("아침")
            if random.random() < 0.90: meals.append("점심")
            if random.random() < 0.92: meals.append("저녁")
            if random.random() < 0.35: meals.append("간식")
            for meal, code, amt, _vec, _base in gen_day(pools, lim, mbase, meals):
                buf.append((mid, code, amt, meal_ts(day, meal)))
                total += 1
            if len(buf) >= BATCH:
                cur.executemany(ins, buf); conn.commit(); buf = []
    if buf:
        cur.executemany(ins, buf); conn.commit()
    return total


def build_thresholds(conn):
    """상한값 계산"""
    cur = conn.cursor()
    cur.execute(
        """SELECT md.회원코드, d.질환명, d.영양소코드, n.영양소명, n.단위, d.일일상한값
           FROM MEMBER_DISEASE md
           JOIN DISEASE d ON d.질환코드 = md.질환코드
           JOIN NUTRIENT n ON n.영양소코드 = d.영양소코드"""
    )
    th = {}
    for mc, dname, nc, nname, unit, limit in cur.fetchall():
        th.setdefault(mc, []).append({
            "disease": dname, "nutrient_code": nc, "nutrient_name": nname,
            "unit": unit, "limit": float(limit),
        })
    return th


def gen_summaries(conn):
    """일일요약 계산"""
    cur = conn.cursor()
    cur.execute(
        """SELECT dr.회원코드, DATE(dr.기록일시) AS d, fn.영양소코드,
                  SUM(fn.함량 * dr.섭취량 / NULLIF(f.기준량, 0)) AS total
           FROM DIET_RECORD dr
           JOIN FOOD f          ON dr.식품코드 = f.식품코드
           JOIN FOOD_NUTRIENT fn ON fn.식품코드 = f.식품코드
           GROUP BY dr.회원코드, d, fn.영양소코드"""
    )
    totals = {}
    for mc, d, nc, total in cur.fetchall():
        totals.setdefault((mc, d), {})[nc] = float(total or 0)
    thresholds = build_thresholds(conn)

    risk_count = {"정상": 0, "주의": 0, "위험": 0, "경고": 0}
    summ_rows, meta = [], []
    for (mc, d), tmap in totals.items():
        risk, exceeded = evaluate_risk(thresholds.get(mc, []), tmap)
        risk_count[risk] += 1
        summ_rows.append((mc, d, risk))
        meta.append((mc, d, tmap, risk, exceeded))
    ins_s = "INSERT INTO DAILY_SUMMARY (회원코드, 날짜, 위험도) VALUES (%s, %s, %s)"
    for i in range(0, len(summ_rows), BATCH):
        cur.executemany(ins_s, summ_rows[i:i + BATCH]); conn.commit()

    cur.execute("SELECT 요약코드, 회원코드, 날짜 FROM DAILY_SUMMARY")
    code_of = {(mc, d): sc for sc, mc, d in cur.fetchall()}

    sn_rows, noti_rows = [], []
    for mc, d, tmap, risk, exceeded in meta:
        sc = code_of[(mc, d)]
        for nc, total in tmap.items():
            sn_rows.append((sc, nc, round(total, 4)))
        noti_rows.append((sc, RISK_TO_NOTI_TYPE[risk], _build_message(risk, exceeded),
                          datetime.combine(d + timedelta(days=1), datetime.min.time()), 0))
    ins_sn = "INSERT INTO SUMMARY_NUTRIENT (요약코드, 영양소코드, 누적량) VALUES (%s, %s, %s)"
    for i in range(0, len(sn_rows), BATCH):
        cur.executemany(ins_sn, sn_rows[i:i + BATCH]); conn.commit()
    ins_n = "INSERT INTO NOTIFICATION (요약코드, 알림유형, 알림내용, 발송일시, 읽음여부) VALUES (%s, %s, %s, %s, %s)"
    for i in range(0, len(noti_rows), BATCH):
        cur.executemany(ins_n, noti_rows[i:i + BATCH]); conn.commit()
    return risk_count, len(summ_rows), len(noti_rows)


def main():
    db = SessionLocal()
    try:
        old = db.query(Member).filter(Member.role == "USER").all()
        for m in old:
            db.delete(m)
        db.commit()
        print(f"기존 회원 {len(old)}명 정리")
        n = create_members(db)
        ids = [r[0] for r in db.execute(text("SELECT 회원코드 FROM MEMBER WHERE 역할='USER'")).fetchall()]
        print(f"회원 {n}명 생성")
    finally:
        db.close()

    conn = engine.raw_connection()
    try:
        name2code, lim = load_nutrients(conn)
        total = gen_records(conn, ids, name2code, lim)
        print(f"식단 기록 {total:,}건 생성")
        risk_count, n_summary, n_noti = gen_summaries(conn)
        print(f"일일요약 {n_summary:,}건, 알림 {n_noti:,}건 생성")
        print("위험도 분포:", risk_count)
        print(f"\n=== 완료 (회원 {N_MEMBERS}명 / 이력 {DAYS}일 / 비밀번호 {PASSWORD}) ===")
    finally:
        conn.close()


if __name__ == "__main__":
    if "--stats" in sys.argv:
        run_stats()
    else:
        main()
