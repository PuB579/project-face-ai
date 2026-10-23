"""กฎช่วงเวลาเช็คชื่อ / เส้นแบ่งเข้าเรียน-มาสาย / การนับขาด"""
import datetime as dt

import pytest

from app.attendance_utils import checkin_window, effective_status, late_minutes
from app.models import AttendanceStatus
from app.routers.attendance import _determine_status
from conftest import DAY, at, make_class, make_detail, make_session


# ---------------------------------------------------------------------------
# checkin_window: [start - open_offset, เวลาเลิกเรียน]
# ---------------------------------------------------------------------------
def test_window_opens_before_start_and_closes_at_end_of_class():
    open_dt, close_dt = checkin_window(make_session("08:30", "10:00"), make_class(open_offset=15))
    assert open_dt == at("08:15")
    assert close_dt == at("10:00")


def test_window_without_end_time_closes_after_close_offset():
    _, close_dt = checkin_window(make_session("08:30", None), make_class(close_offset=30))
    assert close_dt == at("09:00")


def test_window_with_end_time_ignores_close_offset():
    _, close_dt = checkin_window(make_session("08:30", "12:00"), make_class(close_offset=30))
    assert close_dt == at("12:00")


def test_window_is_empty_without_start_time():
    assert checkin_window(make_session(None, None), make_class()) == (None, None)


# ---------------------------------------------------------------------------
# effective_status: ไม่มีแถวเช็คชื่อ -> upcoming / open / absent ตามเวลา
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("08:14", "upcoming"),  # ก่อนเปิดเช็คชื่อ
        ("08:15", "open"),  # เปิดพอดี
        ("09:30", "open"),
        ("10:00", "open"),  # ปิดพอดี ยังเช็คชื่อได้
        ("10:01", "absent"),  # หลังเลิกเรียน
    ],
)
def test_status_without_record_follows_window(now, expected):
    session, class_ = make_session("08:30", "10:00"), make_class(open_offset=15)
    assert effective_status(session, class_, None, at(now)) == expected


@pytest.mark.parametrize("status", [AttendanceStatus.present, AttendanceStatus.late, AttendanceStatus.absent])
def test_recorded_status_wins_over_window(status):
    session, class_ = make_session("08:30", "10:00"), make_class()
    detail = make_detail(status)
    # แม้ยังไม่ถึงเวลาเปิด หรือเลยเวลาปิดไปแล้ว ก็ใช้สถานะที่บันทึกไว้
    assert effective_status(session, class_, detail, at("07:00")) == status.value
    assert effective_status(session, class_, detail, at("23:00")) == status.value


def test_session_without_start_time_is_open_on_its_day_and_absent_afterwards():
    session, class_ = make_session(None, None), make_class()
    assert effective_status(session, class_, None, at("23:59")) == "open"
    assert effective_status(session, class_, None, at("00:00", DAY + dt.timedelta(days=1))) == "absent"


def test_past_session_without_record_is_absent():
    session, class_ = make_session("08:30", "10:00", day=DAY - dt.timedelta(days=7)), make_class()
    assert effective_status(session, class_, None, at("08:00")) == "absent"


# ---------------------------------------------------------------------------
# _determine_status: เช็คชื่อภายใน start + late_threshold = เข้าเรียน, หลังจากนั้น = มาสาย
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("check_in", "expected"),
    [
        ("08:20", AttendanceStatus.present),  # ก่อนเริ่มเรียน
        ("08:30", AttendanceStatus.present),
        ("08:35:00", AttendanceStatus.present),  # ถึงเส้นพอดี ยังนับตรงเวลา
        ("08:35:01", AttendanceStatus.late),  # เกินเส้นไป 1 วินาที
        ("09:59", AttendanceStatus.late),
    ],
)
def test_late_cutoff(check_in, expected):
    session = make_session("08:30", "10:00")
    assert _determine_status(session, dt.time.fromisoformat(check_in), 5) == expected


def test_zero_threshold_means_late_right_after_start():
    session = make_session("08:30", "10:00")
    assert _determine_status(session, dt.time(8, 30), 0) == AttendanceStatus.present
    assert _determine_status(session, dt.time(8, 30, 1), 0) == AttendanceStatus.late


def test_session_without_start_time_counts_as_present():
    assert _determine_status(make_session(None, None), dt.time(23, 0), 5) == AttendanceStatus.present


# ---------------------------------------------------------------------------
# late_minutes: นาทีที่สายนับจากเวลาเริ่มคาบ (ปัดเศษวินาทีทิ้ง, ไม่ติดลบ)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("check_in", "expected"),
    [("08:20", 0), ("08:30", 0), ("08:42:59", 12), ("09:30", 60)],
)
def test_late_minutes(check_in, expected):
    assert late_minutes(make_session("08:30", "10:00"), dt.time.fromisoformat(check_in)) == expected


def test_late_minutes_is_none_without_times():
    assert late_minutes(make_session(None, None), dt.time(9, 0)) is None
    assert late_minutes(make_session("08:30", "10:00"), None) is None
