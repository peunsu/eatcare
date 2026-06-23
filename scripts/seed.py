import sys
import os
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Nutrient, Disease, Member
from app.auth import hash_password

# (영양소명, 단위)
NUTRIENTS = [("당류", "g"), ("나트륨", "mg"), ("지방", "g")]

# (질환명, 기준영양소명, 일일상한값)
DISEASES = [("당뇨", "당류", 50.0), ("고혈압", "나트륨", 2000.0), ("고지혈증", "지방", 60.0)]

ADMIN = {"email": "admin@nutrition.local", "password": "admin1234", "name": "운영자"}


def main():
    db = SessionLocal()
    try:
        # 영양소
        nut_map = {}
        for name, unit in NUTRIENTS:
            n = db.query(Nutrient).filter(Nutrient.name == name).first()
            if not n:
                n = Nutrient(name=name, unit=unit)
                db.add(n)
                db.flush()
            nut_map[name] = n.code
        # 질환
        for dname, nname, limit in DISEASES:
            d = db.query(Disease).filter(Disease.name == dname).first()
            if not d:
                db.add(Disease(name=dname, nutrient_code=nut_map[nname], daily_limit=limit))
        # 운영자
        admin = db.query(Member).filter(Member.email == ADMIN["email"]).first()
        if not admin:
            db.add(Member(
                name=ADMIN["name"], email=ADMIN["email"],
                password=hash_password(ADMIN["password"]),
                joined_at=date.today(), role="ADMIN", status="ACTIVE",
            ))
        db.commit()

        for n in db.query(Nutrient).all():
            print(f"  NUTRIENT {n.code}: {n.name} ({n.unit})")
        for d in db.query(Disease).all():
            print(f"  DISEASE  {d.code}: {d.name} -> 영양소{d.nutrient_code} 기준치 {d.daily_limit}")
        print(f"  ADMIN: {ADMIN['email']} / {ADMIN['password']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
