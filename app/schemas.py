from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, Field


# ---- 인증 ----
class SignupRequest(BaseModel):
    name: str
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=4)
    birth_year: Optional[int] = None
    gender: Optional[str] = Field(default=None, pattern="^[MF]$")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ---- 회원 ----
class MemberOut(BaseModel):
    code: int
    name: str
    email: str
    birth_year: Optional[int]
    gender: Optional[str]
    role: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    birth_year: Optional[int] = None
    gender: Optional[str] = Field(default=None, pattern="^[MF]$")


# ---- 질환 ----
class DiseaseOut(BaseModel):
    code: int
    name: str
    nutrient_name: str
    unit: str
    daily_limit: float


class MemberDiseaseIn(BaseModel):
    disease_code: int


class MemberDiseaseOut(BaseModel):
    disease_code: int
    name: str
    registered_at: date


# ---- 식품 / 식단 ----
class FoodOut(BaseModel):
    code: str
    name: str
    base_amount: float
    base_unit: str


class DietRecordIn(BaseModel):
    food_code: str
    amount: float = Field(gt=0)
    recorded_at: Optional[datetime] = None


class DietRecordOut(BaseModel):
    code: int
    food_code: str
    food_name: str
    category: Optional[str] = None
    amount: float
    recorded_at: datetime
    nutrients: list = []   # [{name, unit, amount}] — 섭취량 기준 함유량


# ---- 리포트 ----
class NutrientStatus(BaseModel):
    nutrient_name: str
    unit: str
    total: float
    limit: Optional[float] = None
    exceeded: bool = False
    monitored: bool = False


class DailyReportOut(BaseModel):
    date: date
    risk: str
    nutrients: List[NutrientStatus]


class NotificationOut(BaseModel):
    code: int
    type: str
    content: str
    sent_at: datetime
    is_read: bool
    date: date
