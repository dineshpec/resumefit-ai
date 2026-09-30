"""In-process usage limits and the optional access-code gate.

State lives in memory and is lost on restart (accepted for one process on one
host). Every method is thread-safe because Streamlit runs each session in its
own thread.
"""

import hmac
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

RefusalReason = Literal["already_running", "busy", "daily_budget", "quota"]
GateResult = Literal["ok", "wrong", "locked"]


@dataclass(frozen=True)
class Refusal:
    reason: RefusalReason
    resets_at: datetime | None


class UsageLimiter:
    def __init__(
        self,
        per_visitor_daily: int,
        global_daily: int,
        max_concurrent: int,
        per_visitor_concurrent: int = 1,
    ) -> None:
        self._per_visitor_daily = per_visitor_daily
        self._global_daily = global_daily
        self._max_concurrent = max_concurrent
        self._per_visitor_concurrent = per_visitor_concurrent
        self._lock = threading.Lock()
        self._day: date | None = None
        self._started_today: dict[str, int] = {}
        self._global_started_today = 0
        self._admitted: dict[str, int] = {}
        self._admitted_total = 0

    def try_admit(self, visitor: str, now: datetime) -> "AdmissionLease | Refusal":
        """Take a concurrency slot without consuming any daily quota."""
        today = _utc_day(now)
        with self._lock:
            self._roll_over(today)
            if self._admitted.get(visitor, 0) >= self._per_visitor_concurrent:
                return Refusal("already_running", None)
            if self._admitted_total >= self._max_concurrent:
                return Refusal("busy", None)
            refusal = self._daily_refusal(visitor, today)
            if refusal is not None:
                return refusal
            self._admitted[visitor] = self._admitted.get(visitor, 0) + 1
            self._admitted_total += 1
        return AdmissionLease(self, visitor)

    def remaining(self, visitor: str, now: datetime) -> int:
        """Analyses this visitor can still start today, bounded by the global cap."""
        today = _utc_day(now)
        with self._lock:
            self._roll_over(today)
            visitor_left = self._per_visitor_daily - self._started_today.get(visitor, 0)
            global_left = self._global_daily - self._global_started_today
        return max(0, min(visitor_left, global_left))

    def _start(self, visitor: str, now: datetime) -> Refusal | None:
        today = _utc_day(now)
        with self._lock:
            self._roll_over(today)
            refusal = self._daily_refusal(visitor, today)
            if refusal is not None:
                return refusal
            self._started_today[visitor] = self._started_today.get(visitor, 0) + 1
            self._global_started_today += 1
        return None

    def _release(self, visitor: str) -> None:
        with self._lock:
            remaining = self._admitted[visitor] - 1
            if remaining:
                self._admitted[visitor] = remaining
            else:
                del self._admitted[visitor]
            self._admitted_total -= 1

    def _daily_refusal(self, visitor: str, today: date) -> Refusal | None:
        if self._global_started_today >= self._global_daily:
            return Refusal("daily_budget", _next_midnight(today))
        if self._started_today.get(visitor, 0) >= self._per_visitor_daily:
            return Refusal("quota", _next_midnight(today))
        return None

    def _roll_over(self, today: date) -> None:
        if self._day != today:
            self._day = today
            self._started_today.clear()
            self._global_started_today = 0


class AdmissionLease:
    """One admitted request. Release it in ``finally``; start it at team start."""

    def __init__(self, limiter: UsageLimiter, visitor: str) -> None:
        self._limiter = limiter
        self._visitor = visitor
        self._lock = threading.Lock()
        self._started = False
        self._released = False

    def start(self, now: datetime) -> Refusal | None:
        """Consume one visitor and one global daily count, at most once per lease."""
        with self._lock:
            if self._released:
                raise RuntimeError("cannot start a released admission lease")
            if self._started:
                return None
            refusal = self._limiter._start(self._visitor, now)
            self._started = refusal is None
            return refusal

    def release(self) -> None:
        """Free the admission slots; calling it again does nothing."""
        with self._lock:
            if self._released:
                return
            self._released = True
        self._limiter._release(self._visitor)


class AccessGate:
    def __init__(
        self,
        code: str,
        max_failures: int = 5,
        lockout: timedelta = timedelta(minutes=15),
    ) -> None:
        self._code = code.encode()
        self._max_failures = max_failures
        self._lockout = lockout
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._locked_until: dict[str, datetime] = {}

    @property
    def required(self) -> bool:
        return bool(self._code)

    def attempt(self, visitor: str, code: str, now: datetime) -> GateResult:
        """Check a code; the attempt that reaches the failure limit returns "locked"."""
        if not self.required:
            return "ok"
        with self._lock:
            locked_until = self._locked_until.get(visitor)
            if locked_until is not None:
                if now < locked_until:
                    return "locked"
                del self._locked_until[visitor]
            if hmac.compare_digest(code.encode(), self._code):
                self._failures.pop(visitor, None)
                return "ok"
            failures = self._failures.get(visitor, 0) + 1
            if failures < self._max_failures:
                self._failures[visitor] = failures
                return "wrong"
            self._failures.pop(visitor, None)
            self._locked_until[visitor] = now + self._lockout
            return "locked"


def _utc_day(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError("the clock must return timezone-aware datetimes")
    return now.astimezone(UTC).date()


def _next_midnight(today: date) -> datetime:
    return datetime.combine(today + timedelta(days=1), time.min, tzinfo=UTC)
