from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Member, MemberDisease, Disease, Nutrient


def filter_members(db, age_min=None, age_max=None, gender=None, disease_code=None):
    """연령대/성별/질환 조건으로 회원 필터링."""
    this_year = date.today().year
    q = db.query(Member).filter(Member.role == "USER", Member.status == "ACTIVE")
    if gender:
        q = q.filter(Member.gender == gender)
    if age_min is not None:
        q = q.filter((this_year - Member.birth_year) >= age_min)
    if age_max is not None:
        q = q.filter((this_year - Member.birth_year) <= age_max)
    if disease_code is not None:
        q = q.join(MemberDisease, MemberDisease.member_code == Member.code).filter(
            MemberDisease.disease_code == disease_code
        )
    return q.all()


def _member_nutrient_avg(db, member_codes, start_date, end_date, nutrient_codes=None):
    """기간 내 일일 누적량 평균."""
    placeholders = ",".join([str(int(c)) for c in member_codes])
    where_nut = ""
    if nutrient_codes:
        where_nut = " AND sn.영양소코드 IN (%s)" % ",".join(str(int(c)) for c in nutrient_codes)
    sql = text(
        f"""
        SELECT ds.회원코드 AS m, sn.영양소코드 AS nc, AVG(sn.누적량) AS a
        FROM DAILY_SUMMARY ds
        JOIN SUMMARY_NUTRIENT sn ON sn.요약코드 = ds.요약코드
        WHERE ds.회원코드 IN ({placeholders})
          AND ds.날짜 BETWEEN :s AND :e {where_nut}
        GROUP BY ds.회원코드, sn.영양소코드
        """
    )
    out = {}
    for r in db.execute(sql, {"s": start_date, "e": end_date}).fetchall():
        out.setdefault(r.nc, {})[r.m] = float(r.a or 0)
    return out


def group_average_nutrients(db: Session, member_codes: list, start_date: date, end_date: date,
                            avg_map=None, nutrients=None):
    """그룹의 영양소 평균 섭취량."""
    if not member_codes:
        return []
    total = len(member_codes)
    if avg_map is None:
        avg_map = _member_nutrient_avg(db, member_codes, start_date, end_date)
    if nutrients is None:
        nutrients = db.query(Nutrient).order_by(Nutrient.code).all()
    result = []
    for n in nutrients:
        per_member = avg_map.get(n.code, {})
        group_avg = sum(per_member.get(c, 0.0) for c in member_codes) / total
        result.append({
            "nutrient_code": n.code,
            "nutrient_name": n.name,
            "unit": n.unit,
            "avg_intake": round(group_avg, 2),
            "member_count": total,
        })
    return result


def nutrient_distributions(db: Session, member_codes: list, start_date: date, end_date: date,
                           avg_map=None, nutrients=None, limit_by=None):
    """영양소 평균 섭취량 분포."""
    if not member_codes:
        return []
    if avg_map is None:
        avg_map = _member_nutrient_avg(db, member_codes, start_date, end_date)
    if limit_by is None:
        limit_by = {d.nutrient_code: d.daily_limit for d in db.query(Disease).all()}
    if nutrients is None:
        nutrients = db.query(Nutrient).order_by(Nutrient.code).all()
    out = []
    for n in nutrients:
        per_member = avg_map.get(n.code, {})
        values = [round(per_member.get(c, 0.0), 2) for c in member_codes]
        out.append({
            "nutrient_code": n.code,
            "nutrient_name": n.name,
            "unit": n.unit,
            "limit": limit_by.get(n.code),
            "values": values,
        })
    return out


def food_category_distribution(db: Session, member_codes: list, start_date: date, end_date: date, top: int = 8):
    """그룹의 섭취 식품을 대분류별로 집계."""
    if not member_codes:
        return []
    placeholders = ",".join([str(int(c)) for c in member_codes])
    sql = text(
        f"""
        SELECT COALESCE(f.대분류, '미분류') AS category, COUNT(*) AS cnt
        FROM DIET_RECORD dr
        JOIN FOOD f ON f.식품코드 = dr.식품코드
        WHERE dr.회원코드 IN ({placeholders})
          AND DATE(dr.기록일시) BETWEEN :s AND :e
        GROUP BY category
        ORDER BY cnt DESC
        LIMIT :top
        """
    )
    rows = db.execute(sql, {"s": start_date, "e": end_date, "top": top}).fetchall()
    return [{"category": r.category, "count": int(r.cnt)} for r in rows]


def nutrient_over_ratio(db: Session, member_codes: list, start_date: date, end_date: date,
                        avg_map=None, nutrients=None, limit_by=None):
    """필터된 그룹에서 영양소 표준 상한을 초과한 회원 비율."""
    if not member_codes:
        return []
    total = len(member_codes)
    if limit_by is None:
        limit_by = {d.nutrient_code: d.daily_limit for d in db.query(Disease).all()}
    if avg_map is None:
        avg_map = _member_nutrient_avg(db, member_codes, start_date, end_date)
    if nutrients is None:
        nutrients = db.query(Nutrient).order_by(Nutrient.code).all()
    out = []
    for n in nutrients:
        lim = limit_by.get(n.code)
        if lim is None:
            continue
        per = avg_map.get(n.code, {})
        over = sum(1 for c in member_codes if per.get(c, 0.0) > lim)
        out.append({
            "nutrient_name": n.name, "unit": n.unit, "limit": lim,
            "total_members": total, "over_members": over,
            "over_ratio": round(over / total, 3),
        })
    return out


def risk_distribution(db: Session, member_codes: list, start_date: date, end_date: date):
    """기간 내 일일요약의 위험도 분포."""
    dist = {"정상": 0, "주의": 0, "위험": 0, "경고": 0}
    if not member_codes:
        return dist
    placeholders = ",".join([str(int(c)) for c in member_codes])
    sql = text(
        f"""SELECT 위험도 AS r, COUNT(*) AS c FROM DAILY_SUMMARY
            WHERE 회원코드 IN ({placeholders}) AND 날짜 BETWEEN :s AND :e
            GROUP BY 위험도"""
    )
    for row in db.execute(sql, {"s": start_date, "e": end_date}).fetchall():
        if row.r in dist:
            dist[row.r] = int(row.c)
    return dist


def over_threshold_ratio(db: Session, member_codes: list, start_date: date, end_date: date,
                         avg_map=None, disease_nutrients=None):
    """질환별로, 그룹 내 해당 질환을 보유한 회원 중 기준 영양소 상한을 초과한 비율."""
    if not member_codes:
        return []
    if disease_nutrients is None:
        disease_nutrients = db.query(Disease, Nutrient).join(Nutrient, Nutrient.code == Disease.nutrient_code).all()
    if avg_map is None:
        nutrient_codes = [d.nutrient_code for d, _ in disease_nutrients]
        avg_map = _member_nutrient_avg(db, member_codes, start_date, end_date, nutrient_codes)
    patients = {}
    for dc, mc in (
        db.query(MemberDisease.disease_code, MemberDisease.member_code)
        .filter(MemberDisease.member_code.in_(member_codes)).all()
    ):
        patients.setdefault(dc, set()).add(mc)
    out = []
    for d, n in disease_nutrients:
        group = patients.get(d.code, set())
        per_member = avg_map.get(d.nutrient_code, {})
        over = sum(1 for c in group if per_member.get(c, 0.0) > d.daily_limit)
        out.append({
            "disease": d.name,
            "nutrient_name": n.name,
            "unit": n.unit,
            "limit": d.daily_limit,
            "total_members": len(group),
            "over_members": over,
            "over_ratio": round(over / len(group), 3) if group else 0.0,
        })
    return out
