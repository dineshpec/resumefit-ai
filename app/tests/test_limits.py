import threading
from datetime import UTC, datetime, timedelta

import pytest

from resumefit.limits import AccessGate, AdmissionLease, Refusal, UsageLimiter

MORNING = datetime(2026, 3, 10, 9, 30, tzinfo=UTC)
NEXT_MIDNIGHT = datetime(2026, 3, 11, tzinfo=UTC)


def limiter(**overrides):
    settings = {"per_visitor_daily": 5, "global_daily": 200, "max_concurrent": 3}
    settings.update(overrides)
    return UsageLimiter(**settings)


def run_once(usage, visitor, now=MORNING):
    lease = usage.try_admit(visitor, now)
    assert isinstance(lease, AdmissionLease)
    assert lease.start(now) is None
    lease.release()


def test_sixth_start_on_same_utc_day_is_refused_until_midnight():
    usage = limiter()
    for _ in range(5):
        run_once(usage, "visitor-a")

    refusal = usage.try_admit("visitor-a", MORNING + timedelta(hours=1))

    assert refusal == Refusal("quota", resets_at=NEXT_MIDNIGHT)
    assert usage.remaining("visitor-a", MORNING) == 0


def test_quota_resets_at_the_utc_day_boundary():
    usage = limiter()
    for _ in range(5):
        run_once(usage, "visitor-a")

    lease = usage.try_admit("visitor-a", NEXT_MIDNIGHT)

    assert isinstance(lease, AdmissionLease)
    assert usage.remaining("visitor-a", NEXT_MIDNIGHT) == 5


def test_second_concurrent_admission_for_same_visitor_is_refused():
    usage = limiter()
    first = usage.try_admit("visitor-a", MORNING)

    second = usage.try_admit("visitor-a", MORNING)

    assert isinstance(first, AdmissionLease)
    assert second == Refusal("already_running", resets_at=None)


def test_fourth_global_admission_is_refused_as_busy_without_using_quota():
    usage = limiter()
    for visitor in ("a", "b", "c"):
        assert isinstance(usage.try_admit(visitor, MORNING), AdmissionLease)

    refusal = usage.try_admit("d", MORNING)

    assert refusal == Refusal("busy", resets_at=None)
    assert usage.remaining("d", MORNING) == 5


def test_global_daily_cap_refuses_a_different_visitor_until_next_day():
    usage = limiter(global_daily=2)
    run_once(usage, "a")
    run_once(usage, "b")

    refusal = usage.try_admit("c", MORNING)

    assert refusal == Refusal("daily_budget", resets_at=NEXT_MIDNIGHT)
    assert isinstance(usage.try_admit("c", NEXT_MIDNIGHT), AdmissionLease)


def test_remaining_never_exceeds_what_the_global_cap_allows():
    usage = limiter(global_daily=2)
    run_once(usage, "a")

    assert usage.remaining("b", MORNING) == 1


def test_racing_threads_get_exactly_three_admission_leases():
    usage = limiter()
    barrier = threading.Barrier(20)
    results = []

    def contend(index):
        barrier.wait()
        results.append(usage.try_admit(f"visitor-{index}", MORNING))

    threads = [threading.Thread(target=contend, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    leases = [result for result in results if isinstance(result, AdmissionLease)]
    assert len(leases) == 3
    assert all(
        result == Refusal("busy", None) for result in results if result not in leases
    )


def test_release_is_idempotent_and_frees_the_slot():
    usage = limiter(max_concurrent=1)
    lease = usage.try_admit("a", MORNING)
    assert isinstance(lease, AdmissionLease)

    lease.release()
    lease.release()

    assert isinstance(usage.try_admit("b", MORNING), AdmissionLease)
    assert usage.try_admit("c", MORNING) == Refusal("busy", None)


def test_naive_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        limiter().try_admit("a", datetime(2026, 3, 10, 9, 30))


def test_five_wrong_codes_lock_even_the_right_code_for_fifteen_minutes():
    gate = AccessGate("open-sesame")
    results = [gate.attempt("a", "wrong", MORNING) for _ in range(5)]

    assert results == ["wrong"] * 4 + ["locked"]
    assert gate.attempt("a", "open-sesame", MORNING + timedelta(minutes=14)) == "locked"
    assert gate.attempt("a", "open-sesame", MORNING + timedelta(minutes=15)) == "ok"


def test_lockout_is_per_visitor():
    gate = AccessGate("open-sesame")
    for _ in range(5):
        gate.attempt("a", "wrong", MORNING)

    assert gate.attempt("b", "open-sesame", MORNING) == "ok"


def test_correct_code_resets_the_failure_count():
    gate = AccessGate("open-sesame")
    for _ in range(4):
        gate.attempt("a", "wrong", MORNING)
    assert gate.attempt("a", "open-sesame", MORNING) == "ok"

    assert [gate.attempt("a", "wrong", MORNING) for _ in range(4)] == ["wrong"] * 4


def test_gate_is_not_required_when_no_code_is_configured():
    gate = AccessGate("")

    assert not gate.required
    assert gate.attempt("a", "", MORNING) == "ok"


def test_gate_is_required_when_a_code_is_configured():
    assert AccessGate("open-sesame").required
