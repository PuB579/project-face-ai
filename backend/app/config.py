"""
การตั้งค่าของแอปพลิเคชันทั้งหมด อ่านค่าจาก environment variables (หรือไฟล์ .env)
ฐานข้อมูลจริงถูกสร้างไว้แล้วใน MySQL/MariaDB ผ่าน phpMyAdmin
backend นี้แค่ "ต่อ" เข้าไปเท่านั้น ไม่ได้สร้างตารางเอง
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ----- Database -----
    # ตัวอย่าง: mysql+pymysql://root:password@localhost:3306/project_face_ai_db?charset=utf8mb4
    database_url: str = (
        "mysql+pymysql://root:password@localhost:3306/project_face_ai_db?charset=utf8mb4"
    )

    # ----- JWT / Auth -----
    secret_key: str = "change-this-secret-key-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8  # 8 ชั่วโมง

    # ----- จำกัดการ login ผิด (ดู app/rate_limit.py) -----
    login_max_failures_per_user: int = 5  # ต่อ IP + ชื่อผู้ใช้
    login_max_failures_per_ip: int = 20
    login_failure_window_minutes: int = 15

    # ----- Uploads -----
    uploads_dir: str = "uploads"
    face_uploads_subdir: str = "faces"

    # ----- Face recognition (ค่า fallback เท่านั้น ถ้าตาราง classes ไม่ได้กำหนดไว้) -----
    default_late_threshold_minutes: int = 5
    default_face_confidence_threshold: int = 85
    # face_recognition library ให้ "ระยะห่าง" (distance) ยิ่งน้อยยิ่งเหมือน
    # เราแปลงเป็น "confidence" แบบเปอร์เซ็นต์ (0-100) เพื่อให้เทียบกับ threshold ข้างบนได้ง่าย
    face_distance_cutoff: float = 0.6

    # ----- CORS -----
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
