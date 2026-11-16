"""Bounded offline-only NDJSON bookkeeping, never credential/Live authorization.

Only the launcher supplies fixed startup policy. No executable source, subprocess,
network request, environment credential or client-selected path is accepted.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

from .budget import BudgetExceeded, BudgetLimits
from .call_identity import CALL_ID_PATTERN, REQUEST_DIGEST_PATTERN
from .broker_usage import UsagePolicy, counter, decimal_string, official_usage, validate_usage
from .ledger import BudgetLedger
from .pricing import PriceSnapshot

MAX_FRAME = 16_384
MAX_CONFIG = 65_536
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_ROUTE = re.compile(r"offline-test-only(?:-[A-Za-z0-9_.-]{1,64})?\Z", re.ASCII)
_MODEL = re.compile(r"fixture-[A-Za-z0-9_.-]{1,64}\Z", re.ASCII)
PURPOSES = frozenset({"conversation", "compaction", "judge"})


class ProtocolError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _keys(value: object, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - (optional or set()):
        raise ValueError("invalid object schema")
    return value


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("invalid identifier")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(char) < 32 for char in value):
        raise ValueError("invalid provenance text")
    return value


def _unique_pairs(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _no_number(value: str):
    raise ValueError("non-integer JSON number")


def strict_json(data: bytes) -> object:
    return json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=_unique_pairs,
                      parse_float=_no_number, parse_constant=_no_number)


def canonical(value: object) -> str:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"),
                      default=lambda item: format(item, "f") if isinstance(item, Decimal) else str(item))


def envelope(identity: str | None, *, ok: bool = False, code: str,
             dispatch_allowed: bool = False, **values) -> dict:
    return {"v": 1, "id": identity, "ok": ok, "code": code,
            "dispatch_allowed": dispatch_allowed, "duplicate": False, **values}


@dataclass(frozen=True)
class RoutePolicy:
    prices: PriceSnapshot
    known_fee: Decimal
    usage: UsagePolicy


class BookkeepingBroker:
    def __init__(self, config: dict):
        _keys(config, {"v", "synthetic", "db_path", "scope_id", "max_messages", "limits", "routes"})
        if type(config["v"]) is not int or config["v"] != 1 or config["synthetic"] is not True:
            raise ValueError("only synthetic v1 policy is supported")
        raw_path = config["db_path"]
        if not isinstance(raw_path, str) or len(raw_path) > 1024 or not Path(raw_path).is_absolute():
            raise ValueError("fixed absolute DB path required")
        path = Path(raw_path).resolve()
        scope = _identifier(config["scope_id"])
        max_messages = counter(config["max_messages"], positive=True)
        if max_messages > 100_000:
            raise ValueError("journal limit exceeds bound")
        limit_keys = {"soft_usd", "hard_usd", "per_call_usd", "max_requests", "max_input_tokens",
                      "max_output_tokens", "max_steps", "max_retries"}
        raw_limits = _keys(config["limits"], limit_keys)
        limits = BudgetLimits(**{key: decimal_string(value) if key.endswith("usd") else counter(value)
                                 for key, value in raw_limits.items()})
        routes = config["routes"]
        if not isinstance(routes, list) or not 1 <= len(routes) <= 8:
            raise ValueError("bounded explicit route allowlist required")
        policies: dict[tuple[str, str], RoutePolicy] = {}
        for route in routes:
            _keys(route, {"route_id", "model", "price", "known_extra_fee_usd", "usage_policy"})
            route_id, model = route["route_id"], route["model"]
            if (not isinstance(route_id, str) or not _ROUTE.fullmatch(route_id)
                    or not isinstance(model, str) or not _MODEL.fullmatch(model)):
                raise ValueError("only offline fixture routes/models are supported")
            price = _keys(route["price"], {"version", "source", "captured_at", "input_per_million",
                                           "cached_input_per_million", "output_per_million"})
            prices = PriceSnapshot(route_id, model, _text(price["version"]),
                                   decimal_string(price["input_per_million"]),
                                   decimal_string(price["output_per_million"]),
                                   decimal_string(price["cached_input_per_million"]),
                                   _text(price["source"]), _text(price["captured_at"]), mock=True)
            if prices.input_per_million == 0 or prices.output_per_million == 0:
                raise ValueError("synthetic fixture must use nonzero accounting rates")
            usage = UsagePolicy(**_keys(route["usage_policy"], {"cache_write", "reasoning"}))
            key = (route_id, model)
            if key in policies:
                raise ValueError("duplicate route/model")
            policies[key] = RoutePolicy(prices, decimal_string(route["known_extra_fee_usd"]), usage)
        # Complete validation occurs before opening/migrating a DB.
        self.routes = policies
        self.max_messages = max_messages
        self.ledger = BudgetLedger(path, scope_id=scope, limits=limits)
        fixed = {"v": 1, "synthetic": True, "db_path": str(path), "scope_id": scope,
                 "max_messages": max_messages, "limits": asdict(limits),
                 "routes": {route + "/" + model: asdict(policy)
                            for (route, model), policy in sorted(policies.items())}}
        self.ledger.bind_broker_policy(canonical(fixed))

    def _validate_message(self, message: object) -> dict:
        if not isinstance(message, dict):
            raise ValueError("invalid message")
        if type(message.get("v")) is not int or message["v"] != 1:
            raise ValueError("unsupported version")
        _identifier(message.get("id"))
        op = message.get("op")
        if not isinstance(op, str):
            raise ValueError("operation must be a string")
        common = {"v", "id", "op"}
        if op == "snapshot":
            return _keys(message, common)
        if op == "reserve":
            _keys(message, common | {"task_id", "route_id", "model", "purpose", "input_tokens",
                                     "output_tokens", "retry"}, {"call_id"})
            _identifier(message["task_id"])
            if "call_id" in message:
                # PR4b additive v1 field, canonicalized by ADR-002. Older v1
                # clients that do not send it keep the exact previous behavior;
                # clients must send call-<48hex>, never an egress-local eg- id.
                if not isinstance(message["call_id"], str) or not CALL_ID_PATTERN.fullmatch(message["call_id"]):
                    raise ProtocolError("INVALID_CALL_ID")
            if not isinstance(message["route_id"], str) or not isinstance(message["model"], str):
                raise ValueError("invalid route")
            if not isinstance(message["purpose"], str) or message["purpose"] not in PURPOSES:
                raise ValueError("unknown attribution")
            counter(message["input_tokens"], positive=True)
            counter(message["output_tokens"], positive=True)
            if type(message["retry"]) is not bool:
                raise ValueError("retry must be boolean")
            return message
        if op == "claim":
            _keys(message, common | {"call_id", "reservation_id", "request_digest"},
                  {"expected_route_id", "expected_model"})
            if not isinstance(message["call_id"], str) or not CALL_ID_PATTERN.fullmatch(message["call_id"]):
                raise ProtocolError("INVALID_CALL_ID")
            _identifier(message["reservation_id"])
            if (not isinstance(message["request_digest"], str)
                    or not REQUEST_DIGEST_PATTERN.fullmatch(message["request_digest"])):
                raise ProtocolError("INVALID_REQUEST_DIGEST")
            has_route = "expected_route_id" in message
            has_model = "expected_model" in message
            if has_route != has_model:
                raise ProtocolError("EXPECTED_BINDING_PAIR_REQUIRED")
            if has_route:
                if (not isinstance(message["expected_route_id"], str)
                        or not message["expected_route_id"]
                        or not isinstance(message["expected_model"], str)
                        or not message["expected_model"]):
                    raise ProtocolError("INVALID_EXPECTED_BINDING")
            return message
        if op in {"settle", "fail"}:
            _keys(message, common | {"reservation_id", "usage"})
            _identifier(message["reservation_id"])
            try:
                validate_usage(message["usage"])
            except ValueError:
                raise ProtocolError("INVALID_USAGE") from None
            return message
        raise ValueError("unknown operation")

    def _operate(self, database, request: dict) -> dict:
        identity = request["id"]
        op = request["op"]
        count = database.execute("SELECT COUNT(*) FROM budget_broker_messages WHERE scope_id=?",
                                 (self.ledger.scope_id,)).fetchone()[0]
        # F2: journal capacity is split. Observation never consumes journal quota
        # and never writes a row; it stays available after the journal cap. The
        # aggregate snapshot is a fixed-size object (one bounded NDJSON frame),
        # and serve() processes one line at a time, so frequency/backpressure and
        # response size are bounded by the protocol loop, not by journal storage.
        if op == "snapshot":
            return envelope(identity, ok=True, code="SNAPSHOT", snapshot=self.ledger.snapshot())
        if op in {"settle", "fail"}:
            # Completing an already-counted PENDING reservation is capacity that
            # was reserved when the reservation was admitted. It must remain
            # possible even after new reservations are refused (F2), and the
            # admission invariant below keeps count+1 <= max_messages.
            return self._complete(database, request)
        if op == "reserve":
            pending = database.execute(
                "SELECT COUNT(*) FROM budget_reservations WHERE scope_id=? AND status='PENDING'",
                (self.ledger.scope_id,)).fetchone()[0]
            # Reserve admission reserves ONE journal slot for this request and ONE
            # future settle/fail slot for the same reservation. Existing pending
            # reservations already hold their completion slots, so:
            #   count + new_reserve_row + (pending + this_completion) <= max_messages
            if count + pending + 2 > self.max_messages:
                raise ProtocolError("MESSAGE_LIMIT")
            policy = self.routes.get((request["route_id"], request["model"]))
            if policy is None:
                return envelope(identity, code="ROUTE_BLOCKED")
            try:
                reservation = self.ledger.reserve(task_id=request["task_id"], prices=policy.prices,
                    input_tokens=request["input_tokens"], output_tokens=request["output_tokens"],
                    retry=request["retry"], extra_fees_usd=policy.known_fee)
            except BudgetExceeded:
                # A denial cannot be swallowed by compaction/retry then undone.
                database.execute("UPDATE budget_scopes SET blocked=1 WHERE scope_id=?", (self.ledger.scope_id,))
                return envelope(identity, code="BUDGET_EXCEEDED")
            values = {"reservation_id": reservation.reservation_id,
                      "reservation": json.loads(canonical(asdict(reservation)))}
            if "call_id" in request:
                try:
                    self.ledger.bind_call(request["call_id"], reservation.reservation_id)
                except ValueError:
                    # A call id must never be retargeted; raising rolls back the
                    # whole reservation+journal transaction (fail-closed).
                    raise ProtocolError("CALL_ID_CONFLICT") from None
                values["call_id"] = request["call_id"]
            return envelope(identity, ok=True, code="RESERVED", dispatch_allowed=True, **values)
        raise ProtocolError("UNKNOWN_OPERATION")

    def _complete(self, database, request: dict) -> dict:
        identity = request["id"]
        op = request["op"]
        row = database.execute("SELECT * FROM budget_reservations WHERE scope_id=? AND reservation_id=?",
                               (self.ledger.scope_id, request["reservation_id"])).fetchone()
        if row is None:
            return envelope(identity, code="UNKNOWN_RESERVATION")
        if row["status"] != "PENDING":
            # Repeating a completion (same or new message id) is idempotent:
            # no extra journal row, no double charge, no refund (T-JOURNAL).
            return envelope(identity, code="ALREADY_SETTLED")
        policy = self.routes.get((row["route_id"], row["model"]))
        if policy is None:
            return envelope(identity, code="ROUTE_BLOCKED")
        try:
            # A migrated pending request keeps its original price AND fee.
            # Startup route fees apply only to new reservations, never history.
            usage, mapping = official_usage(request["usage"], input_bound=row["input_bound"],
                output_bound=row["output_bound"], policy=policy.usage, known_fee=Decimal(row["known_fee"]))
        except ValueError:
            return envelope(identity, code="INVALID_USAGE")
        settlement = self.ledger.settle(request["reservation_id"], usage,
                                        status="FAILED" if op == "fail" else "OK")
        self.ledger.mark_claim_completed(request["reservation_id"])
        return envelope(identity, ok=True, code="FAILED" if op == "fail" else "SETTLED",
                        reservation_id=request["reservation_id"], settlement=settlement, usage_mapping=mapping)

    def _completion_precheck(self, database, request: dict) -> dict | None:
        """Return an envelope to reject, or None; runs in journal transaction."""
        row = database.execute(
            "SELECT status,route_id,model,input_bound,output_bound,known_fee "
            "FROM budget_reservations WHERE scope_id=? AND reservation_id=?",
            (self.ledger.scope_id, request["reservation_id"])).fetchone()
        identity = request["id"]
        if row is None:
            return envelope(identity, code="UNKNOWN_RESERVATION")
        if row["status"] != "PENDING":
            return envelope(identity, code="ALREADY_SETTLED")
        policy = self.routes.get((row["route_id"], row["model"]))
        if policy is None:
            return envelope(identity, code="ROUTE_BLOCKED")
        try:
            official_usage(request["usage"], input_bound=row["input_bound"],
                           output_bound=row["output_bound"],
                           policy=policy.usage,
                           known_fee=Decimal(row["known_fee"]))
        except ValueError:
            return envelope(identity, code="INVALID_USAGE")
        return None

    def handle(self, message: object) -> dict:
        identity = None
        if isinstance(message, dict) and isinstance(message.get("id"), str) and _ID.fullmatch(message["id"]):
            identity = message["id"]
        try:
            request = self._validate_message(message)
            # F2: snapshot is a read-only observation. It is NOT journaled (so it
            # neither consumes the message quota nor grows durable storage) and it
            # remains available after the journal cap. Frequency and size are
            # bounded by the serial serve loop and MAX_FRAME.
            if request["op"] == "snapshot":
                with self.ledger._transaction() as database:
                    return self._operate(database, request)
            # ADR-002: claim is an additive v1 op with its own durable unique
            # table/transaction; it is deliberately NOT journaled so it cannot
            # consume the fixed completion/message capacity or be replayed as a
            # second license. Replays are answered from budget_dispatch_claims.
            if request["op"] == "claim":
                result = self.ledger.claim_dispatch(
                    request["call_id"], request["reservation_id"], request["request_digest"],
                    allowed_routes=set(self.routes),
                    expected_route_id=request.get("expected_route_id"),
                    expected_model=request.get("expected_model"))
                if result["ok"]:
                    return envelope(identity, ok=True, code="CLAIMED", dispatch_allowed=True,
                                    claim=result["claim"],
                                    route_id=result.get("route_id"),
                                    model=result.get("model"))
                return envelope(identity, ok=False, code=result["code"], dispatch_allowed=False,
                                duplicate=result.get("duplicate", False), claim=result.get("claim"))
            # F2: a completion repeated with a NEW message id for an already
            # settled reservation is idempotent and must not add another journal
            # row/storage. Exact same-id replays still fall through to journal_once
            # so the original stored response (and duplicate flag) is preserved.
            precheck = None
            if request["op"] in {"settle", "fail"}:
                def precheck(database):
                    return self._completion_precheck(database, request)
            digest = hashlib.sha256(canonical(request).encode("utf-8")).hexdigest()
            response, duplicate = self.ledger.journal_once(
                request["id"], digest, lambda db: self._operate(db, request),
                precheck=precheck)
            if duplicate:
                response["duplicate"] = True
                if response["dispatch_allowed"]:
                    response["dispatch_allowed"] = False
                    response["code"] = "DUPLICATE_NO_DISPATCH"
            return response
        except ProtocolError as exc:
            return envelope(identity, code=exc.code)
        except ValueError as exc:
            code = "IDEMPOTENCY_CONFLICT" if str(exc) == "idempotency conflict" else "INVALID_MESSAGE"
            return envelope(identity, code=code)
        except Exception:
            return envelope(identity, code="INTERNAL_ERROR")


def _emit(output, response: dict) -> None:
    data = (canonical(response) + "\n").encode("utf-8")
    if len(data) > MAX_FRAME:
        raise ValueError("response exceeds frame bound")
    output.write(data)
    output.flush()


def serve(broker: BookkeepingBroker, incoming, outgoing) -> int:
    """No unbounded buffering or background workers; EOF never refunds pending."""
    while True:
        try:
            data = incoming.readline(MAX_FRAME + 1)
            if not data:
                return 0
            if len(data) > MAX_FRAME:
                _emit(outgoing, envelope(None, code="FRAME_TOO_LARGE"))
                return 2
            if not data.endswith(b"\n"):
                _emit(outgoing, envelope(None, code="INCOMPLETE_FRAME"))
                return 2
            try:
                message = strict_json(data)
            except (ValueError, UnicodeError, RecursionError):
                _emit(outgoing, envelope(None, code="INVALID_MESSAGE"))
                continue
            _emit(outgoing, broker.handle(message))
        except Exception:
            # A committed reservation may have lost its ack: keep it, exit, and
            # let the durable idempotency record refuse a repeated dispatch grant.
            return 3


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if len(args) != 2 or args[0] != "--config":
            raise ValueError("fixed startup argument required")
        with Path(args[1]).open("rb") as stream:
            data = stream.read(MAX_CONFIG + 1)
        if len(data) > MAX_CONFIG:
            raise ValueError("startup config exceeds bound")
        broker = BookkeepingBroker(strict_json(data))
    except Exception:
        try:
            _emit(sys.stdout.buffer, envelope(None, code="STARTUP_BLOCKED"))
        except Exception:
            pass
        return 2
    return serve(broker, sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
