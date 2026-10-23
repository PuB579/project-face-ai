"""สูตรคะแนนเข้าเรียน (compute_score) ทั้งโหมด direct และ per_session"""
from decimal import Decimal

import pytest

from app.models import ScoreMode
from app.routers.scores import compute_score
from conftest import make_rule


def score(rule, present=0, absent=0, late=()):
    return compute_score(rule, present, absent, list(late))


# ---------------------------------------------------------------------------
# direct: เต็ม full_score, ขาดครั้งละ full_score / session_count, สายหักตามขั้น
# ---------------------------------------------------------------------------
def test_direct_full_score_when_never_absent_or_late():
    assert score(make_rule(), present=16) == Decimal("10.00")


def test_direct_absence_deducts_full_over_session_count():
    # 10 / 16 = 0.625 ต่อครั้งที่ขาด
    assert score(make_rule(), present=14, absent=2) == Decimal("8.75")


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (4, "10.00"),  # ยังไม่ถึงขั้นแรก
        (5, "9.00"),  # ขั้น 5 นาที หัก 1
        (15, "8.00"),  # ใช้ขั้นสูงสุดที่ไม่เกินนาทีที่สาย (10 นาที หัก 2)
        (20, "7.00"),
        (90, "7.00"),
    ],
)
def test_direct_late_uses_highest_matching_tier(minutes, expected):
    assert score(make_rule(), late=[minutes]) == Decimal(expected)


def test_direct_late_tiers_are_matched_regardless_of_order():
    rule = make_rule(tiers=((20, "3"), (5, "1"), (10, "2")))
    assert score(rule, late=[12]) == Decimal("8.00")


def test_direct_score_never_goes_below_zero():
    assert score(make_rule(), absent=20, late=[30, 30]) == Decimal("0.00")


def test_direct_without_session_count_has_no_absence_deduction():
    assert score(make_rule(session_count=0), absent=5) == Decimal("10.00")


def test_direct_rounds_half_up_to_two_decimals():
    # 10 - 10/3 = 6.666... -> 6.67
    assert score(make_rule(session_count=3), absent=1) == Decimal("6.67")


# ---------------------------------------------------------------------------
# per_session: ครั้งละ session_full_score รวมเป็นคะแนนดิบ แล้วแปลงสัดส่วนเป็น full_score
# ---------------------------------------------------------------------------
def per_session(**kw):
    kw.setdefault("session_count", 20)
    return make_rule(mode=ScoreMode.per_session, **kw)


def test_per_session_converts_raw_points_to_full_score():
    # เข้า 18 จาก 20 ครั้ง = 180 / 200 -> 9.00 จาก 10
    assert score(per_session(), present=18, absent=2) == Decimal("9.00")


def test_per_session_late_session_earns_points_minus_tier():
    # 19 ครั้งเต็ม + สาย 12 นาที (10 - 2 = 8) = 198 / 200 -> 9.90
    assert score(per_session(), present=19, late=[12]) == Decimal("9.90")


def test_per_session_late_penalty_cannot_go_below_zero_for_that_session():
    rule = per_session(session_count=2, session_full="1", tiers=((5, "3"),))
    # ครั้งที่สายได้ max(0, 1 - 3) = 0 ไม่ใช่ -2: 1 / 2 -> 5.00
    assert score(rule, present=1, late=[10]) == Decimal("5.00")


def test_per_session_sessions_not_yet_held_do_not_count():
    # ผ่านไปแค่ 5 ครั้งจาก 20: 50 / 200 -> 2.50 (คะแนนเพิ่มขึ้นเรื่อยๆ ตามคาบที่เรียน)
    assert score(per_session(), present=5) == Decimal("2.50")


def test_per_session_is_capped_at_full_score():
    assert score(per_session(), present=25) == Decimal("10.00")


def test_per_session_with_no_possible_points_scores_zero():
    assert score(per_session(session_count=0), present=3) == Decimal("0.00")


def test_per_session_rounds_half_up_not_bankers():
    # 1 / 200 * 1 = 0.005 -> 0.01 (ROUND_HALF_UP; แบบ banker's จะได้ 0.00)
    rule = per_session(full="1", session_count=200, session_full="1")
    assert score(rule, present=1) == Decimal("0.01")
