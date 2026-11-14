"""Explicit official TokenUsage -> ledger mapping, without importing the SDK.

inputTokens is UNCACHED; cacheReadTokens/cacheWriteTokens are disjoint. Known
fixture billing rules are mandatory. Unknown dimensions/rules are never free.
"""
from dataclasses import dataclass
from decimal import Decimal
import re

from .usage import Usage
from .pricing import money

MAX_COUNTER = 1_000_000_000
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,9})?\Z", re.ASCII)
USAGE_KEYS = frozenset({"inputTokens", "cacheReadTokens", "cacheWriteTokens", "outputTokens",
                        "reasoningTokens", "totalTokens", "actual_cost_usd"})


def decimal_string(value: object) -> Decimal:
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise ValueError("invalid decimal")
    result = money(value)
    if result > MAX_COUNTER:
        raise ValueError("decimal exceeds protocol bound")
    return result


def counter(value: object, *, positive: bool = False) -> int:
    if type(value) is not int or value < int(positive) or value > MAX_COUNTER:
        raise ValueError("invalid token counter")
    return value


@dataclass(frozen=True)
class UsagePolicy:
    cache_write: str
    reasoning: str

    def __post_init__(self) -> None:
        if self.cache_write != "input_rate":
            raise ValueError("unknown cache-write billing rule")
        if self.reasoning not in {"included_in_output", "additional_output"}:
            raise ValueError("unknown reasoning billing rule")


def validate_usage(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - USAGE_KEYS:
        raise ValueError("unknown usage schema")
    for key, count in value.items():
        if count is not None:
            if key == "actual_cost_usd":
                decimal_string(count)
            else:
                counter(count)


def official_usage(value: dict | None, *, input_bound: int, output_bound: int,
                   policy: UsagePolicy, known_fee: Decimal) -> tuple[Usage, dict]:
    validate_usage(value)
    raw = value or {}
    parts = [raw.get(key) for key in ("inputTokens", "cacheReadTokens", "cacheWriteTokens")]
    complete_input = all(part is not None for part in parts)
    known_input = sum(part for part in parts if part is not None)
    total_input = known_input if complete_input else max(input_bound, known_input)
    # No cache discount on an incomplete input dimension. The ledger additionally
    # enforces no-invoice estimates >= full worst-case reservation cost.
    cache_read = raw["cacheReadTokens"] if complete_input else 0
    output = raw.get("outputTokens")
    reasoning = raw.get("reasoningTokens")
    complete_output = output is not None and (
        policy.reasoning == "included_in_output" or reasoning is not None)
    known_output = (output or 0) + ((reasoning or 0) if policy.reasoning == "additional_output" else 0)
    total_output = known_output if complete_output else max(output_bound, known_output)
    if policy.reasoning == "included_in_output" and reasoning is not None and output is not None and reasoning > output:
        raise ValueError("reasoning subset exceeds inclusive output")
    total = raw.get("totalTokens")
    if total is not None and complete_input and complete_output and total != total_input + total_output:
        raise ValueError("inconsistent total tokens")
    actual = raw.get("actual_cost_usd")
    estimated = not complete_input or not complete_output
    usage = Usage(total_input, total_output, cache_read, estimated,
                  None if actual is None else decimal_string(actual), known_fee)
    return usage, {"input_semantics": "uncached+cacheRead+cacheWrite",
                   "cache_write_rule": policy.cache_write, "reasoning_rule": policy.reasoning,
                   "complete_input": complete_input, "complete_output": complete_output,
                   "reasoning_tokens": reasoning, "cache_write_tokens": raw.get("cacheWriteTokens")}
