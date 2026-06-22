"""애플리케이션 설정."""
import os

# DB 접속 (기존 MariaDB, 계정 user/user)
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "user")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "nutrition")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
)

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "nutrition-system-secret-key-2025")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))

# 위험도 판정용 영양소명 (DISEASE.영양소코드로 매핑되지만, 표시용 상수)
TARGET_NUTRIENTS = ["당류", "나트륨", "지방"]
