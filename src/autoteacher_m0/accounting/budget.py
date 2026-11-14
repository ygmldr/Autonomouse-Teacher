"""Thread-safe preflight reservations for EVERY model step, including retries.

A guard covers one controller's complete experiment, not separate processes. SDKs
that hide autonomous calls must not be presented as precisely guarded by this API.
"""
from dataclasses import dataclass, replace
from decimal import Decimal
from threading import RLock
from uuid import uuid4
from .pricing import PriceSnapshot, money
from .usage import Usage, normalize_usage


class BudgetExceeded(RuntimeError):
    code = "BUDGET_EXCEEDED"


@dataclass(frozen=True)
class BudgetLimits:
    soft_usd: Decimal = Decimal("3")
    hard_usd: Decimal = Decimal("10")
    per_call_usd: Decimal = Decimal("0.20")
    max_requests: int = 50
    max_input_tokens: int = 2_500_000
    max_output_tokens: int = 600_000
    max_steps: int = 8
    max_retries: int = 1

    def __post_init__(self) -> None:
        for name in ("soft_usd", "hard_usd", "per_call_usd"):
            object.__setattr__(self, name, money(getattr(self, name)))
        if self.soft_usd > self.hard_usd:
            raise ValueError("soft budget exceeds hard budget")
        for name in ("max_requests", "max_input_tokens", "max_output_tokens", "max_steps", "max_retries"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("limits must be nonnegative integers")


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    task_id: str
    route_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    extra_fees_usd: Decimal
    retry: bool


class BudgetGuard:
    def __init__(self, prices: PriceSnapshot, limits: BudgetLimits | None = None):
        self.prices = prices
        self.limits = limits or BudgetLimits()
        self._lock = RLock()
        self._pending: dict[str, Reservation] = {}
        self._steps: dict[str, int] = {}
        self._retries: dict[str, int] = {}
        self._requests = 0
        self._input = 0
        self._output = 0
        self._spent = Decimal("0")
        self._breached = False
        self.entries: list[dict] = []

    def reserve(self, *, task_id: str, route_id: str, model: str,
                input_tokens: int, output_tokens: int, retry: bool = False,
                extra_fees_usd: object = 0, max_cost_usd: object | None = None) -> Reservation:
        if not task_id:
            raise ValueError("task_id required")
        if route_id != self.prices.route_id or model != self.prices.model:
            raise ValueError("price snapshot does not match actual channel/model")
        for count in (input_tokens, output_tokens):
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError("positive worst-case token bounds required")
        cost = self.prices.reserve_cost(input_tokens, output_tokens, extra_fees_usd)
        with self._lock:
            limit = self.limits
            pending_cost = sum((r.cost_usd for r in self._pending.values()), Decimal("0"))
            pending_input = sum(r.input_tokens for r in self._pending.values())
            pending_output = sum(r.output_tokens for r in self._pending.values())
            reason = None
            if self._breached:
                reason = "previous settlement exceeded reservation or hard limit"
            elif self._spent >= limit.hard_usd:
                reason = "total hard budget already reached"
            elif self._input >= limit.max_input_tokens or self._output >= limit.max_output_tokens:
                reason = "token limit already reached"
            elif cost > limit.per_call_usd or (max_cost_usd is not None and cost > money(max_cost_usd)):
                reason = "per-call budget"
            elif self._spent + pending_cost + cost > limit.hard_usd:
                reason = "total hard budget"
            elif self._requests >= limit.max_requests:
                reason = "request limit"
            elif self._steps.get(task_id, 0) >= limit.max_steps:
                reason = "task step limit (retries included)"
            elif retry and self._retries.get(task_id, 0) >= limit.max_retries:
                reason = "task retry limit"
            elif self._input + pending_input + input_tokens > limit.max_input_tokens:
                reason = "input token limit"
            elif self._output + pending_output + output_tokens > limit.max_output_tokens:
                reason = "output token limit"
            if reason:
                raise BudgetExceeded(reason)
            reservation = Reservation(str(uuid4()), task_id, route_id, model,
                                      input_tokens, output_tokens, cost, money(extra_fees_usd), retry)
            self._pending[reservation.reservation_id] = reservation
            self._requests += 1
            self._steps[task_id] = self._steps.get(task_id, 0) + 1
            if retry:
                self._retries[task_id] = self._retries.get(task_id, 0) + 1
            return reservation

    def settle(self, reservation: Reservation, usage: Usage | None = None, *,
               status: str = "OK") -> dict:
        with self._lock:
            current = self._pending.get(reservation.reservation_id)
            if current != reservation:
                raise ValueError("unknown/already settled reservation")
            usage = usage or normalize_usage(None, None, reserved_input=current.input_tokens,
                                             reserved_output=current.output_tokens,
                                             extra_fees_usd=current.extra_fees_usd)
            if usage.actual_cost_usd is None and usage.extra_fees_usd < current.extra_fees_usd:
                # The known request surcharge is owed even on a missing/partial
                # response; an authoritative total bill is already inclusive.
                usage = replace(usage, extra_fees_usd=current.extra_fees_usd)
            cost = usage.cost(self.prices)
            if usage.estimated and usage.actual_cost_usd is None:
                cost = max(cost, current.cost_usd)
            # Even if a provider breaks the bound, account honestly, trip closed,
            # and never conceal the overrun by clipping actual usage/cost.
            exceeded = (usage.input_tokens > current.input_tokens
                        or usage.output_tokens > current.output_tokens or cost > current.cost_usd)
            del self._pending[current.reservation_id]
            self._input += usage.input_tokens
            self._output += usage.output_tokens
            self._spent += cost
            self._breached |= (exceeded or self._spent > self.limits.hard_usd
                              or self._input > self.limits.max_input_tokens
                              or self._output > self.limits.max_output_tokens)
            entry = {"reservation_id": current.reservation_id, "task_id": current.task_id,
                     "route_id": current.route_id, "model": current.model,
                     "price_version": self.prices.version, "status": status,
                     "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                     "cached_input_tokens": usage.cached_input_tokens,
                     "cost_usd": format(cost, "f"), "estimated": usage.estimated,
                     "cost_kind": "actual" if usage.actual_cost_usd is not None else "estimated",
                     "reservation_exceeded": exceeded, "retry": current.retry}
            self.entries.append(entry)
            return dict(entry)

    def fail(self, reservation: Reservation, usage: Usage | None = None) -> dict:
        # No refund on a missing response: a timed-out provider may have billed it.
        return self.settle(reservation, usage, status="FAILED")

    def snapshot(self) -> dict:
        with self._lock:
            return {"spent_usd": format(self._spent, "f"), "requests": self._requests,
                    "input_tokens": self._input, "output_tokens": self._output,
                    "pending": len(self._pending),
                    "reserved_usd": format(sum((r.cost_usd for r in self._pending.values()), Decimal("0")), "f"),
                    "soft_exceeded": self._spent >= self.limits.soft_usd,
                    "blocked": self._breached, "price_version": self.prices.version}
