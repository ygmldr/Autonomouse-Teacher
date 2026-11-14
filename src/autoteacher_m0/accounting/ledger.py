"""SQLite persistent, cross-process budget reservations for a fixed budget scope.

Use ONE durable scope/database for all channels/experiments sharing an approved
budget. Route changes never reset this ledger. Pending requests survive crashes;
they remain charged at their full bounds until explicit conservative settlement.
This is accounting infrastructure, not permission to enable blocked Live calls.
"""
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
from threading import local
from uuid import uuid4

from .budget import BudgetExceeded, BudgetLimits, Reservation
from .pricing import PriceSnapshot, money
from .usage import Usage, normalize_usage


def _json_dataclass(value: object) -> str:
    return json.dumps(asdict(value), default=lambda item: format(item, "f") if isinstance(item, Decimal) else str(item),
                      sort_keys=True, separators=(",", ":"))


class BudgetLedger:
    def __init__(self, path: Path | str, *, scope_id: str, limits: BudgetLimits | None = None):
        if not scope_id:
            raise ValueError("stable budget scope id required")
        self.path = str(path)
        if self.path == ":memory:":
            raise ValueError("persistent ledger requires a file")
        self.scope_id = scope_id
        self.limits = limits or BudgetLimits()
        self._local = local()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as database:
            database.executescript("""
                CREATE TABLE IF NOT EXISTS budget_scopes (
                  scope_id TEXT PRIMARY KEY, limits_json TEXT NOT NULL, blocked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS budget_reservations (
                  reservation_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, task_id TEXT NOT NULL,
                  route_id TEXT NOT NULL, model TEXT NOT NULL, price_json TEXT NOT NULL,
                  input_bound INTEGER NOT NULL, output_bound INTEGER NOT NULL,
                  reserved_cost TEXT NOT NULL, known_fee TEXT NOT NULL, retry INTEGER NOT NULL,
                  status TEXT NOT NULL, input_used INTEGER NOT NULL, output_used INTEGER NOT NULL,
                  cost TEXT NOT NULL, estimated INTEGER NOT NULL, settlement_json TEXT);
                CREATE INDEX IF NOT EXISTS budget_scope_idx ON budget_reservations(scope_id);
            """)
            # executescript ends SQLite's implicit transaction. Re-enter an
            # immediate transaction before comparing/creating immutable policy.
            database.execute("BEGIN IMMEDIATE")
            encoded = _json_dataclass(self.limits)
            current = database.execute("SELECT limits_json FROM budget_scopes WHERE scope_id=?",
                                       (scope_id,)).fetchone()
            if current is None:
                database.execute("INSERT INTO budget_scopes VALUES (?,?,0)", (scope_id, encoded))
            elif BudgetLimits(**json.loads(current[0])) != self.limits:
                # Legacy policies may have used scientific Decimal strings.
                # Compare exact numeric policy, not a formatting-only change.
                raise ValueError("existing budget scope policy differs; cannot silently relax limits")

    @contextmanager
    def _transaction(self):
        """Compose journal + bookkeeping under one durable writer transaction.

        Nested public operations use per-thread SAVEPOINTs, never a second DB
        connection/commit. Legacy callers keep their original atomic behavior.
        """
        parent = getattr(self._local, "database", None)
        if parent is not None:
            savepoint = "nested_" + uuid4().hex
            parent.execute("SAVEPOINT " + savepoint)
            try:
                yield parent
                parent.execute("RELEASE " + savepoint)
            except BaseException:
                parent.execute("ROLLBACK TO " + savepoint)
                parent.execute("RELEASE " + savepoint)
                raise
            return
        database = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        database.row_factory = sqlite3.Row
        try:
            database.execute("PRAGMA busy_timeout=30000")
            database.execute("PRAGMA synchronous=FULL")
            database.execute("BEGIN IMMEDIATE")
            self._local.database = database
            yield database
            database.commit()
        except BaseException:
            database.rollback()
            raise
        finally:
            self._local.database = None
            database.close()

    def bind_broker_policy(self, policy_json: str) -> None:
        """Additive v1 migration; preserve every legacy reservation and counter.

        Only a trusted launcher chooses policy. A DB gets one broker scope and
        policy for its lifetime; this audit binding is NOT human authorization.
        """
        with self._transaction() as database:
            database.execute("CREATE TABLE IF NOT EXISTS budget_broker_policy ("
                             "singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                             "scope_id TEXT NOT NULL, policy_json TEXT NOT NULL)")
            database.execute("CREATE TABLE IF NOT EXISTS budget_broker_messages ("
                             "scope_id TEXT NOT NULL, message_id TEXT NOT NULL, digest TEXT NOT NULL, "
                             "response_json TEXT NOT NULL, PRIMARY KEY(scope_id,message_id))")
            current = database.execute("SELECT scope_id,policy_json FROM budget_broker_policy WHERE singleton=1").fetchone()
            if current is None:
                scopes = database.execute("SELECT scope_id FROM budget_scopes").fetchall()
                if any(row[0] != self.scope_id for row in scopes):
                    raise ValueError("broker requires exactly its fixed scope")
                database.execute("INSERT INTO budget_broker_policy VALUES (1,?,?)", (self.scope_id, policy_json))
            elif current[0] != self.scope_id or current[1] != policy_json:
                raise ValueError("broker startup policy differs from durable policy")

    def journal_once(self, message_id: str, digest: str, operation) -> tuple[dict, bool]:
        """Atomically commit a trusted in-process operation plus its reply.

        No protocol accepts callbacks. A lost acknowledgement never reruns the
        operation. Callers MUST suppress dispatch authorization on replay; this
        method alone cannot guarantee exactly-once external provider execution.
        """
        with self._transaction() as database:
            previous = database.execute("SELECT digest,response_json FROM budget_broker_messages "
                                        "WHERE scope_id=? AND message_id=?", (self.scope_id, message_id)).fetchone()
            if previous is not None:
                if previous[0] != digest:
                    raise ValueError("idempotency conflict")
                return json.loads(previous[1]), True
            response = operation(database)
            encoded = json.dumps(response, allow_nan=False, sort_keys=True, separators=(",", ":"))
            database.execute("INSERT INTO budget_broker_messages VALUES (?,?,?,?)",
                             (self.scope_id, message_id, digest, encoded))
            return response, False

    def _state(self, database: sqlite3.Connection) -> tuple[list[sqlite3.Row], bool]:
        rows = database.execute("SELECT * FROM budget_reservations WHERE scope_id=?", (self.scope_id,)).fetchall()
        blocked = database.execute("SELECT blocked FROM budget_scopes WHERE scope_id=?", (self.scope_id,)).fetchone()[0]
        return rows, bool(blocked)

    def reserve(self, *, task_id: str, prices: PriceSnapshot, input_tokens: int,
                output_tokens: int, retry: bool = False, extra_fees_usd: object = 0,
                max_cost_usd: object | None = None) -> Reservation:
        if not task_id:
            raise ValueError("task_id required")
        for count in (input_tokens, output_tokens):
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError("positive conservative token bounds required")
        fee = money(extra_fees_usd)
        cost = prices.reserve_cost(input_tokens, output_tokens, fee)
        with self._transaction() as database:
            rows, blocked = self._state(database)
            spent = sum((Decimal(row["cost"]) for row in rows), Decimal(0))
            total_input = sum(row["input_used"] for row in rows)
            total_output = sum(row["output_used"] for row in rows)
            steps = sum(row["task_id"] == task_id for row in rows)
            retries = sum(row["task_id"] == task_id and row["retry"] for row in rows)
            limit = self.limits
            reason = None
            if blocked:
                reason = "previous settlement exceeded a bound"
            elif spent >= limit.hard_usd or spent + cost > limit.hard_usd:
                reason = "total hard budget"
            elif cost > limit.per_call_usd or (max_cost_usd is not None and cost > money(max_cost_usd)):
                reason = "per-call budget"
            elif len(rows) >= limit.max_requests:
                reason = "request limit"
            elif steps >= limit.max_steps:
                reason = "task step limit (retries included)"
            elif retry and retries >= limit.max_retries:
                reason = "task retry limit"
            elif total_input >= limit.max_input_tokens or total_input + input_tokens > limit.max_input_tokens:
                reason = "input token limit"
            elif total_output >= limit.max_output_tokens or total_output + output_tokens > limit.max_output_tokens:
                reason = "output token limit"
            if reason:
                raise BudgetExceeded(reason)
            reservation = Reservation(str(uuid4()), task_id, prices.route_id, prices.model,
                                      input_tokens, output_tokens, cost, fee, retry)
            database.execute("INSERT INTO budget_reservations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                reservation.reservation_id, self.scope_id, task_id, prices.route_id, prices.model,
                _json_dataclass(prices), input_tokens, output_tokens, format(cost, "f"), format(fee, "f"), int(retry),
                "PENDING", input_tokens, output_tokens, format(cost, "f"), 1, None))
            return reservation

    def settle(self, reservation: Reservation | str, usage: Usage | None = None, *, status: str = "OK") -> dict:
        identity = reservation.reservation_id if isinstance(reservation, Reservation) else reservation
        if status == "PENDING":
            raise ValueError("settlement status cannot be pending")
        with self._transaction() as database:
            row = database.execute("SELECT * FROM budget_reservations WHERE reservation_id=? AND scope_id=?",
                                   (identity, self.scope_id)).fetchone()
            if row is None or row["status"] != "PENDING":
                raise ValueError("unknown/already settled reservation")
            prices = PriceSnapshot(**json.loads(row["price_json"]))
            usage = usage or normalize_usage(None, None, reserved_input=row["input_bound"],
                                             reserved_output=row["output_bound"],
                                             extra_fees_usd=row["known_fee"])
            if usage.actual_cost_usd is None and usage.extra_fees_usd < Decimal(row["known_fee"]):
                usage = replace(usage, extra_fees_usd=Decimal(row["known_fee"]))
            cost = usage.cost(prices)
            if usage.estimated and usage.actual_cost_usd is None:
                # Missing/partial usage cannot refund the worst-case cache path
                # or known fees, even when cache reads cost more than plain input.
                cost = max(cost, Decimal(row["reserved_cost"]))
            exceeded = (cost > Decimal(row["reserved_cost"]) or usage.input_tokens > row["input_bound"]
                        or usage.output_tokens > row["output_bound"])
            entry = {"reservation_id": identity, "scope_id": self.scope_id, "task_id": row["task_id"],
                     "route_id": row["route_id"], "model": row["model"], "price_version": prices.version,
                     "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                     "cached_input_tokens": usage.cached_input_tokens, "cost_usd": format(cost, "f"),
                     "estimated": usage.estimated, "status": status,
                     "cost_kind": "actual" if usage.actual_cost_usd is not None else "estimated",
                     "reservation_exceeded": exceeded}
            database.execute("UPDATE budget_reservations SET status=?,input_used=?,output_used=?,cost=?,estimated=?,"
                             "settlement_json=? WHERE reservation_id=?", (
                                 status, usage.input_tokens, usage.output_tokens, format(cost, "f"), int(usage.estimated),
                                 json.dumps(entry, sort_keys=True), identity))
            if exceeded:
                database.execute("UPDATE budget_scopes SET blocked=1 WHERE scope_id=?", (self.scope_id,))
            return entry

    def fail(self, reservation: Reservation | str, usage: Usage | None = None) -> dict:
        return self.settle(reservation, usage, status="FAILED")

    def snapshot(self) -> dict:
        with self._transaction() as database:
            rows, blocked = self._state(database)
            pending = [row for row in rows if row["status"] == "PENDING"]
            committed = sum((Decimal(row["cost"]) for row in rows), Decimal(0))
            reserved = sum((Decimal(row["cost"]) for row in pending), Decimal(0))
            return {"scope_id": self.scope_id, "requests": len(rows), "pending": len(pending),
                    "spent_usd": format(committed - reserved, "f"), "reserved_usd": format(reserved, "f"),
                    "committed_usd": format(committed, "f"),
                    "input_tokens": sum(row["input_used"] for row in rows),
                    "output_tokens": sum(row["output_used"] for row in rows),
                    "soft_exceeded": committed >= self.limits.soft_usd, "blocked": blocked,
                    "routes": sorted({row["route_id"] for row in rows})}
