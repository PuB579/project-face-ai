"""
ตัวช่วยสร้างออบเจกต์โมเดลแบบไม่บันทึกลงฐานข้อมูล (transient) สำหรับ unit test
import app.* แค่สร้าง engine ไว้เฉยๆ ยังไม่ต่อ MySQL จนกว่าจะมีการ query
"""
import datetime as dt
from decimal import Decimal

from app.models import (
    AttendanceDetail,
    AttendanceScoreRule,
    AttendanceSession,
    AttendanceStatus,
    Class,
    LateTier,
    ScoreMode,
)

DAY = dt.date(2026, 10, 20)  # วันอังคาร


def at(hhmm: str, day: dt.date = DAY) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.fromisoformat(hhmm))


def make_class(open_offset=0, close_offset=30, late_threshold=5) -> Class:
    return Class(
        checkin_open_offset_minutes=open_offset,
        checkin_close_offset_minutes=close_offset,
        late_threshold_minutes=late_threshold,
    )


def make_session(start="08:30", end="10:00", day: dt.date = DAY) -> AttendanceSession:
    return AttendanceSession(
        session_date=day,
        start_time=dt.time.fromisoformat(start) if start else None,
        end_time=dt.time.fromisoformat(end) if end else None,
    )


def make_detail(status: AttendanceStatus, check_in="08:31") -> AttendanceDetail:
    return AttendanceDetail(status=status, check_in_time=dt.time.fromisoformat(check_in))


def make_rule(
    mode=ScoreMode.direct,
    full="10",
    session_count=16,
    session_full="10",
    tiers=((5, "1"), (10, "2"), (20, "3")),
) -> AttendanceScoreRule:
    # ค่า Numeric ที่อ่านจาก MySQL เป็น Decimal จึงใช้ Decimal ให้เหมือนของจริง
    return AttendanceScoreRule(
        mode=mode,
        full_score=Decimal(full),
        session_count=session_count,
        session_full_score=Decimal(session_full),
        late_tiers=[LateTier(min_minutes=m, deduction=Decimal(d)) for m, d in tiers],
    )
