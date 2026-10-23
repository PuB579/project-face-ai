"""
จำกัดการ login ผิดซ้ำๆ (กันการเดารหัสผ่าน)
=========================================
นับเฉพาะครั้งที่ login "ไม่สำเร็จ" ในช่วงเวลาล่าสุด (sliding window) แยก 2 แบบ:
- ต่อ (IP, ชื่อผู้ใช้): กันการเดารหัสผ่านของบัญชีเดียว
- ต่อ IP:              กันการไล่ลองหลายบัญชีจากเครื่องเดียว
ไม่จำกัดต่อชื่อผู้ใช้อย่างเดียว เพราะคนอื่นจะกด login ผิดเพื่อล็อกบัญชีของเหยื่อได้

เก็บในหน่วยความจำของ process (รีเซ็ตเมื่อรีสตาร์ตเซิร์ฟเวอร์) เพียงพอสำหรับ uvicorn process เดียว
ถ้ารันหลาย worker หรืออยู่หลัง reverse proxy ต้องย้ายไปเก็บที่ส่วนกลาง (เช่น Redis)
และอ่าน IP จริงจาก X-Forwarded-For แทน
"""
import math
import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self, max_per_user: int, max_per_ip: int, window_seconds: int, clock=time.monotonic):
        self.max_per_user = max_per_user
        self.max_per_ip = max_per_ip
        self.window = window_seconds
        self._clock = clock
        self._failures: dict[tuple, deque[float]] = defaultdict(deque)
        # endpoint แบบ sync ของ FastAPI รันใน threadpool จึงต้องล็อกก่อนแก้ข้อมูล
        self._lock = threading.Lock()

    @staticmethod
    def _keys(ip: str, username: str) -> tuple[tuple, tuple]:
        return ("user", ip, username.strip().lower()), ("ip", ip)

    def _prune(self, key: tuple, now: float) -> deque[float]:
        q = self._failures[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if not q:
            del self._failures[key]
        return q

    def retry_after(self, ip: str, username: str) -> int:
        """จำนวนวินาทีที่ต้องรอก่อน login ได้อีก (0 = ยังไม่ถูกล็อก)"""
        now = self._clock()
        wait = 0.0
        with self._lock:
            for key, limit in zip(self._keys(ip, username), (self.max_per_user, self.max_per_ip)):
                q = self._prune(key, now)
                if len(q) >= limit:
                    # ปลดล็อกเมื่อครั้งที่ผิดซึ่งทำให้เกินลิมิตหลุดออกจากหน้าต่างเวลา
                    wait = max(wait, q[-limit] + self.window - now)
        return math.ceil(wait) if wait > 0 else 0

    def record_failure(self, ip: str, username: str) -> None:
        now = self._clock()
        with self._lock:
            for key in self._keys(ip, username):
                self._failures[key].append(now)

    def reset(self, ip: str, username: str) -> None:
        """login สำเร็จ: ล้างตัวนับของบัญชีนี้ (ไม่ล้างตัวนับของ IP)"""
        user_key, _ = self._keys(ip, username)
        with self._lock:
            self._failures.pop(user_key, None)
