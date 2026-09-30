import threading
from datetime import UTC, datetime

import pytest

from resumefit.limits import AdmissionLease, Refusal, UsageLimiter

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
NEXT_MIDNIGHT = datetime(2026, 3, 11, tzinfo=UTC)


class ConcurrencyProbe:
    """Tracks how many leases are held at once, per visitor and overall."""

    def __init__(self):
        self._lock = threading.Lock()
        self._per_visitor = {}
        self._total = 0
        self.max_per_visitor = 0
        self.max_total = 0

    def enter(self, visitor):
        with self._lock:
            self._per_visitor[visitor] = self._per_visitor.get(visitor, 0) + 1
            self._total += 1
            self.max_per_visitor = max(self.max_per_visitor, self._per_visitor[visitor])
            self.max_total = max(self.max_total, self._total)

    def leave(self, visitor):
        with self._lock:
            self._per_visitor[visitor] -= 1
            self._total -= 1


def flood(usage, visitors):
    barrier = threading.Barrier(len(visitors))
    probe = ConcurrencyProbe()
    outcomes = []

    def request(visitor):
        barrier.wait()
        result = usage.try_admit(visitor, NOW)
        outcomes.append(result)
        if isinstance(result, AdmissionLease):
            probe.enter(visitor)
        barrier.wait()
        if isinstance(result, AdmissionLease):
            probe.leave(visitor)
            result.release()

    threads = [
        threading.Thread(target=request, args=(visitor,)) for visitor in visitors
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return probe, outcomes


@pytest.mark.parametrize("repetition", range(50))
def test_flood_admits_at_most_one_per_visitor_and_three_overall(repetition):
    usage = UsageLimiter(per_visitor_daily=5, global_daily=200, max_concurrent=3)
    visitors = ["same-visitor"] * 20 + [f"visitor-{index}" for index in range(20)]

    probe, outcomes = flood(usage, visitors)

    leases = [result for result in outcomes if isinstance(result, AdmissionLease)]
    refusals = [result for result in outcomes if isinstance(result, Refusal)]
    assert probe.max_per_visitor == 1
    assert probe.max_total == 3
    assert len(leases) == 3
    assert {refusal.reason for refusal in refusals} <= {"already_running", "busy"}
    assert len(refusals) == 37
    assert usage.remaining("same-visitor", NOW) == 5


def test_released_admission_without_start_keeps_quota():
    usage = UsageLimiter(per_visitor_daily=5, global_daily=200, max_concurrent=3)
    lease = usage.try_admit("visitor", NOW)
    assert isinstance(lease, AdmissionLease)

    lease.release()

    assert usage.remaining("visitor", NOW) == 5
    assert isinstance(usage.try_admit("visitor", NOW), AdmissionLease)


def test_start_consumes_one_visitor_and_one_global_count_only_once():
    usage = UsageLimiter(per_visitor_daily=5, global_daily=2, max_concurrent=3)
    lease = usage.try_admit("visitor", NOW)
    assert isinstance(lease, AdmissionLease)

    assert lease.start(NOW) is None
    assert lease.start(NOW) is None

    assert usage.remaining("visitor", NOW) == 1
    assert usage.remaining("someone-else", NOW) == 1


def test_visitor_with_no_quota_left_is_refused_at_admission():
    usage = UsageLimiter(per_visitor_daily=1, global_daily=200, max_concurrent=3)
    lease = usage.try_admit("visitor", NOW)
    assert isinstance(lease, AdmissionLease)
    lease.start(NOW)
    lease.release()

    assert usage.try_admit("visitor", NOW) == Refusal("quota", resets_at=NEXT_MIDNIGHT)


def test_start_after_another_visitor_used_the_last_global_slot_is_refused():
    usage = UsageLimiter(per_visitor_daily=5, global_daily=1, max_concurrent=3)
    first = usage.try_admit("first", NOW)
    second = usage.try_admit("second", NOW)
    assert isinstance(first, AdmissionLease)
    assert isinstance(second, AdmissionLease)
    assert first.start(NOW) is None

    refusal = second.start(NOW)

    assert refusal == Refusal("daily_budget", resets_at=NEXT_MIDNIGHT)
    assert usage.remaining("second", NOW) == 0
    second.release()
    assert usage.try_admit("third", NOW) == Refusal("daily_budget", NEXT_MIDNIGHT)


def test_start_refused_after_visitor_quota_used_elsewhere_consumes_nothing():
    usage = UsageLimiter(
        per_visitor_daily=1,
        global_daily=200,
        max_concurrent=3,
        per_visitor_concurrent=2,
    )
    first = usage.try_admit("visitor", NOW)
    second = usage.try_admit("visitor", NOW)
    assert isinstance(first, AdmissionLease)
    assert isinstance(second, AdmissionLease)
    assert first.start(NOW) is None

    assert second.start(NOW) == Refusal("quota", resets_at=NEXT_MIDNIGHT)
    assert usage.remaining("other", NOW) == 1


def test_start_on_released_lease_is_a_programming_error():
    usage = UsageLimiter(per_visitor_daily=5, global_daily=200, max_concurrent=3)
    lease = usage.try_admit("visitor", NOW)
    assert isinstance(lease, AdmissionLease)
    lease.release()

    with pytest.raises(RuntimeError):
        lease.start(NOW)
