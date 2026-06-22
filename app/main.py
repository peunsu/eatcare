"""FastAPI 진입점: 라우터 등록 + 정적 프론트엔드 서빙."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import auth, members, diet, reports, notifications, admin, foods

app = FastAPI(title="개인 맞춤형 건강 및 식단 관리 시스템")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(members.router)
app.include_router(diet.router)
app.include_router(reports.router)
app.include_router(notifications.router)
app.include_router(admin.router)
app.include_router(foods.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}

# 정적 프론트엔드 (frontend/ 디렉토리를 / 로 서빙)
_FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(_FRONTEND):
    app.mount("/", StaticFiles(directory=_FRONTEND, html=True), name="frontend")
