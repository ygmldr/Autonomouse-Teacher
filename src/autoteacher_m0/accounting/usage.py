"""Usage normalization with conservative, explicitly estimated missing values."""
from dataclasses import dataclass
from decimal import Decimal
from .pricing import PriceSnapshot, money


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    estimated: bool = False
    actual_cost_usd: Decimal | None = None
    extra_fees_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for count in (self.input_tokens, self.output_tokens, self.cached_input_tokens):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("invalid usage count")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("invalid cached usage")
        object.__setattr__(self, "extra_fees_usd", money(self.extra_fees_usd))
        if self.actual_cost_usd is not None:
            object.__setattr__(self, "actual_cost_usd", money(self.actual_cost_usd))

    def cost(self, prices: PriceSnapshot) -> Decimal:
        if self.actual_cost_usd is not None:
            return self.actual_cost_usd
        return prices.cost(self.input_tokens, self.output_tokens, self.cached_input_tokens,
                           self.extra_fees_usd)


def conservative_input_bound(prompt: str, context_tokens: int = 0) -> int:
    """UTF-8 byte bound plus overhead; caller MUST include all history/tools/system context.

    This is not a verified provider tokenizer or a guarantee on hidden runtime steps.
    Live controllers need enforced context/output limits and external kill protection.
    """
    if context_tokens < 0:
        raise ValueError("context_tokens must be nonnegative")
    return max(1, len(prompt.encode("utf-8")) + context_tokens + 256)


def normalize_usage(input_tokens: int | None, output_tokens: int | None, *,
                    reserved_input: int, reserved_output: int,
                    cached_input_tokens: int = 0, actual_cost_usd: object | None = None,
                    extra_fees_usd: object = 0) -> Usage:
    # A missing/failed response can still be billed. Never substitute zero.
    if reserved_input <= 0 or reserved_output <= 0:
        raise ValueError("positive conservative reservation bounds required")
    missing = input_tokens is None or output_tokens is None
    return Usage(reserved_input if input_tokens is None else input_tokens,
                 reserved_output if output_tokens is None else output_tokens,
                 cached_input_tokens, missing,
                 None if actual_cost_usd is None else money(actual_cost_usd),
                 money(extra_fees_usd))
