"""Explicit channel-specific price snapshots; no live prices are invented."""
from dataclasses import dataclass
from decimal import Decimal


def money(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("amount must be finite and nonnegative")
    return result


@dataclass(frozen=True)
class PriceSnapshot:
    route_id: str
    model: str
    version: str
    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal
    source: str
    captured_at: str
    mock: bool = False

    def __post_init__(self) -> None:
        if not all((self.route_id, self.model, self.version, self.source, self.captured_at)):
            raise ValueError("price provenance is required")
        for name in ("input_per_million", "output_per_million", "cached_input_per_million"):
            object.__setattr__(self, name, money(getattr(self, name)))
        if not self.mock and max(self.input_per_million, self.output_per_million) == 0:
            raise ValueError("live pricing cannot silently default to zero")

    def cost(self, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0,
             extra_fees: object = 0) -> Decimal:
        for count in (input_tokens, output_tokens, cached_input_tokens):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("token counts must be nonnegative integers")
        if cached_input_tokens > input_tokens:
            raise ValueError("cached input cannot exceed total input")
        return ((input_tokens - cached_input_tokens) * self.input_per_million
                + cached_input_tokens * self.cached_input_per_million
                + output_tokens * self.output_per_million) / Decimal(1_000_000) + money(extra_fees)

    def reserve_cost(self, input_tokens: int, output_tokens: int, extra_fees: object = 0) -> Decimal:
        # Reserve the more expensive cache path: cache discounts are never assumed.
        rate = max(self.input_per_million, self.cached_input_per_million)
        return (input_tokens * rate + output_tokens * self.output_per_million) / Decimal(1_000_000) + money(extra_fees)


def mock_prices() -> PriceSnapshot:
    """Synthetic nonzero accounting units, NOT DeepSeek's real price."""
    return PriceSnapshot("mock", "deepseek-flash", "mock-price-v1", Decimal("1"),
                         Decimal("2"), Decimal("0.5"), "synthetic offline fixture",
                         "2026-11-14T00:00:00Z", mock=True)
