"""การจำกัดการ login ผิดซ้ำๆ (LoginRateLimiter) ใช้นาฬิกาจำลองแทนการรอจริง"""
from app.rate_limit import LoginRateLimiter

IP = "10.0.0.1"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(max_per_user=5, max_per_ip=20, window=900):
    clock = FakeClock()
    return LoginRateLimiter(max_per_user, max_per_ip, window, clock=clock), clock


def fail(limiter, times, ip=IP, username="student01@example.com"):
    for _ in range(times):
        limiter.record_failure(ip, username)


def test_not_locked_below_user_limit():
    limiter, _ = make()
    fail(limiter, 4)
    assert limiter.retry_after(IP, "student01@example.com") == 0


def test_locked_after_user_limit_for_whole_window():
    limiter, _ = make()
    fail(limiter, 5)
    assert limiter.retry_after(IP, "student01@example.com") == 900


def test_lock_lifts_when_oldest_counted_failure_leaves_window():
    limiter, clock = make()
    fail(limiter, 5)
    clock.now += 899
    assert limiter.retry_after(IP, "student01@example.com") == 1
    clock.now += 1
    assert limiter.retry_after(IP, "student01@example.com") == 0


def test_sliding_window_waits_for_the_failure_that_crossed_the_limit():
    limiter, clock = make()
    fail(limiter, 4)  # t=1000
    clock.now += 600
    fail(limiter, 2)  # t=1600: ผิดครบ 6 ครั้ง
    # ต้องรอให้หลุดออก 2 ครั้ง (เหลือ 4) -> ครั้งที่ 2 ของชุดแรกหลุดที่ t=1900
    assert limiter.retry_after(IP, "student01@example.com") == 300


def test_username_is_case_and_space_insensitive():
    limiter, _ = make()
    fail(limiter, 5, username="  Student01@Example.com ")
    assert limiter.retry_after(IP, "student01@example.com") > 0


def test_same_user_from_another_ip_is_not_locked():
    # กันไม่ให้คนอื่นล็อกบัญชีของเหยื่อได้จากเครื่องตัวเอง
    limiter, _ = make()
    fail(limiter, 5)
    assert limiter.retry_after("10.0.0.2", "student01@example.com") == 0


def test_ip_limit_blocks_trying_many_usernames():
    limiter, _ = make()
    for i in range(20):
        limiter.record_failure(IP, f"user{i}")
    assert limiter.retry_after(IP, "someone-new") == 900


def test_success_resets_user_counter_but_not_ip_counter():
    limiter, _ = make(max_per_ip=6)
    fail(limiter, 4)
    limiter.reset(IP, "student01@example.com")
    fail(limiter, 4)  # นับใหม่: 4 < 5 ยังไม่ล็อกบัญชี
    assert limiter.retry_after(IP, "student01@example.com") > 0  # แต่ IP ผิดครบ 8 >= 6 แล้ว
    limiter2, _ = make()
    fail(limiter2, 4)
    limiter2.reset(IP, "student01@example.com")
    fail(limiter2, 4)
    assert limiter2.retry_after(IP, "student01@example.com") == 0
