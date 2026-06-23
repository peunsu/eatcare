from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, Boolean, Enum,
    ForeignKey, UniqueConstraint, Index, Computed,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Nutrient(Base):
    __tablename__ = "NUTRIENT"
    code = Column("영양소코드", Integer, primary_key=True, autoincrement=True)
    name = Column("영양소명", String(50), nullable=False)
    unit = Column("단위", String(20), nullable=False)


class Food(Base):
    __tablename__ = "FOOD"
    code = Column("식품코드", String(32), primary_key=True)
    name = Column("식품명", String(255), nullable=False)
    base_amount = Column("기준량", Float, nullable=False, default=100)
    base_unit = Column("기준단위", String(20), nullable=False, default="g")
    category = Column("대분류", String(50))
    search_name = Column("검색명", String(255), Computed("REPLACE(식품명, ' ', '')", persisted=True))

    nutrients = relationship("FoodNutrient", back_populates="food")
    __table_args__ = (Index("idx_food_category", "대분류"), Index("idx_food_search", "검색명"))


class Disease(Base):
    __tablename__ = "DISEASE"
    code = Column("질환코드", Integer, primary_key=True, autoincrement=True)
    name = Column("질환명", String(50), nullable=False)
    nutrient_code = Column("영양소코드", Integer, ForeignKey("NUTRIENT.영양소코드"), nullable=False)
    daily_limit = Column("일일상한값", Float, nullable=False)

    nutrient = relationship("Nutrient")


class Member(Base):
    __tablename__ = "MEMBER"
    code = Column("회원코드", Integer, primary_key=True, autoincrement=True)
    name = Column("이름", String(50), nullable=False)
    birth_year = Column("출생년도", Integer)
    gender = Column("성별", Enum("M", "F"))
    email = Column("이메일", String(255), nullable=False, unique=True)
    password = Column("비밀번호", String(255), nullable=False)
    joined_at = Column("가입일", Date, nullable=False)
    role = Column("역할", Enum("USER", "ADMIN"), nullable=False, default="USER")
    status = Column("계정상태", Enum("ACTIVE", "INACTIVE"), nullable=False, default="ACTIVE")


class FoodNutrient(Base):
    __tablename__ = "FOOD_NUTRIENT"
    food_code = Column("식품코드", String(32), ForeignKey("FOOD.식품코드", ondelete="CASCADE"), primary_key=True)
    nutrient_code = Column("영양소코드", Integer, ForeignKey("NUTRIENT.영양소코드", ondelete="CASCADE"), primary_key=True)
    amount = Column("함량", Float, nullable=False)

    food = relationship("Food", back_populates="nutrients")
    nutrient = relationship("Nutrient")


class MemberDisease(Base):
    __tablename__ = "MEMBER_DISEASE"
    member_code = Column("회원코드", Integer, ForeignKey("MEMBER.회원코드", ondelete="CASCADE"), primary_key=True)
    disease_code = Column("질환코드", Integer, ForeignKey("DISEASE.질환코드", ondelete="CASCADE"), primary_key=True)
    registered_at = Column("등록일", Date, nullable=False)

    disease = relationship("Disease")


class DietRecord(Base):
    __tablename__ = "DIET_RECORD"
    code = Column("기록코드", Integer, primary_key=True, autoincrement=True)
    member_code = Column("회원코드", Integer, ForeignKey("MEMBER.회원코드", ondelete="CASCADE"), nullable=False)
    food_code = Column("식품코드", String(32), ForeignKey("FOOD.식품코드"), nullable=False)
    amount = Column("섭취량", Float, nullable=False)
    recorded_at = Column("기록일시", DateTime, nullable=False)

    food = relationship("Food")
    __table_args__ = (Index("idx_dr_member_date", "회원코드", "기록일시"),)


class DailySummary(Base):
    __tablename__ = "DAILY_SUMMARY"
    code = Column("요약코드", Integer, primary_key=True, autoincrement=True)
    member_code = Column("회원코드", Integer, ForeignKey("MEMBER.회원코드", ondelete="CASCADE"), nullable=False)
    date = Column("날짜", Date, nullable=False)
    risk = Column("위험도", Enum("정상", "주의", "위험", "경고"), nullable=False, default="정상")

    nutrients = relationship("SummaryNutrient", back_populates="summary", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="summary", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("회원코드", "날짜", name="uk_summary_member_date"),)


class SummaryNutrient(Base):
    __tablename__ = "SUMMARY_NUTRIENT"
    summary_code = Column("요약코드", Integer, ForeignKey("DAILY_SUMMARY.요약코드", ondelete="CASCADE"), primary_key=True)
    nutrient_code = Column("영양소코드", Integer, ForeignKey("NUTRIENT.영양소코드", ondelete="CASCADE"), primary_key=True)
    total = Column("누적량", Float, nullable=False)

    summary = relationship("DailySummary", back_populates="nutrients")
    nutrient = relationship("Nutrient")


class Notification(Base):
    __tablename__ = "NOTIFICATION"
    code = Column("알림코드", Integer, primary_key=True, autoincrement=True)
    summary_code = Column("요약코드", Integer, ForeignKey("DAILY_SUMMARY.요약코드", ondelete="CASCADE"), nullable=False)
    type = Column("알림유형", Enum("NORMAL", "WARNING", "DANGER", "CRITICAL"), nullable=False)
    content = Column("알림내용", String(255), nullable=False)
    sent_at = Column("발송일시", DateTime, nullable=False)
    is_read = Column("읽음여부", Boolean, nullable=False, default=False)

    summary = relationship("DailySummary", back_populates="notifications")
