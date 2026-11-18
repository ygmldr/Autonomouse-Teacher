"""G4-A-08: expiry, not-before, clock skew and revoked authorization ids deny."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from autoteacher_m0.security.authorization import AuthorizationRejected
from g4a_support import NOW

NOT_BEFORE = datetime(2026, 11, 18, 11, 55, 0, tzinfo=timezone.utc)
EXPIRES = datetime(2026, 11, 18, 12, 30, 0, tzinfo=timezone.utc)
AUTH_ID = "auth-g4a-synthetic-1"


def _decision(trusted, **kwargs):
    return trusted.load(**kwargs)


def test_a08_not_before_boundary_is_inclusive_expiry_is_exclusive(trusted) -> None:
    assert _decision(trusted, now=NOT_BEFORE).approved is True
    expired = _decision(trusted, now=EXPIRES)
    assert expired.approved is False
    assert "AUTHORIZATION_NOT_CURRENT" in expired.reasons
    assert "AUTHORIZATION_EXPIRED" in expired.reasons
    assert expired.signature_valid is True  # the signature is still valid


@pytest.mark.parametrize("moment,code", [
    (NOT_BEFORE - timedelta(microseconds=1), "AUTHORIZATION_NOT_YET_VALID"),
    (NOT_BEFORE - timedelta(seconds=1), "AUTHORIZATION_NOT_YET_VALID"),
    (NOT_BEFORE - timedelta(minutes=5), "AUTHORIZATION_NOT_YET_VALID"),
    (EXPIRES, "AUTHORIZATION_EXPIRED"),
    (EXPIRES + timedelta(microseconds=1), "AUTHORIZATION_EXPIRED"),
    (EXPIRES + timedelta(hours=1), "AUTHORIZATION_EXPIRED"),
])
def test_a08_zero_clock_skew_tolerance(trusted, moment: datetime, code: str) -> None:
    decision = _decision(trusted, now=moment)
    assert decision.approved is False
    assert code in decision.reasons, decision.reasons
    assert "AUTHORIZATION_NOT_CURRENT" in decision.reasons


def test_a08_stale_authorization_also_reports_age(trusted) -> None:
    decision = _decision(trusted, now=NOW + timedelta(days=8))
    assert decision.approved is False
    assert "AUTHORIZATION_TOO_OLD" in decision.reasons
    assert "AUTHORIZATION_EXPIRED" in decision.reasons


def test_a08_invalid_time_window_is_rejected(trusted) -> None:
    payload = copy.deepcopy(trusted.payload)
    payload["not_before_utc"] = "2026-11-18T11:40:00Z"  # before issued_utc
    trusted.write_signed(payload)
    decision = trusted.load()
    assert "AUTHORIZATION_TIME_WINDOW_INVALID" in decision.reasons

    payload = copy.deepcopy(trusted.payload)
    payload["expires_utc"] = "2026-11-19T12:01:00Z"  # more than 24h lifetime
    trusted.write_signed(payload)
    assert "AUTHORIZATION_LIFETIME_TOO_LONG" in trusted.load().reasons

    payload = copy.deepcopy(trusted.payload)
    payload["expires_utc"] = "2026-11-18T12:00:00"
    trusted.write_signed(payload)
    assert "AUTHORIZATION_TIME_INVALID" in trusted.load().reasons


def test_a08_revoked_authorization_id_is_denied(trusted) -> None:
    trusted.set_revocations([AUTH_ID])
    decision = trusted.load()
    assert decision.approved is False
    assert "AUTHORIZATION_REVOKED" in decision.reasons
    assert decision.signature_valid is True
    assert trusted.use_records() == []


def test_a08_revocation_matching_is_exact(trusted) -> None:
    trusted.set_revocations([AUTH_ID.upper()])
    assert trusted.load().approved is True


@pytest.mark.parametrize("body", [
    "not json",
    json.dumps({"schema": "at-m0/revocation/v1", "revoked_ids": ["x"], "extra": 1}),
    json.dumps({"schema": "at-m0/revocation/v1", "revoked_ids": "x"}),
    json.dumps({"schema": "at-m0/revocation/v1", "revoked_ids": [1]}),
    json.dumps(["not", "an", "object"]),
])
def test_a08_malformed_revocation_file_fails_closed(trusted, body: str) -> None:
    trusted.revocations.write_text(body, encoding="utf-8")
    decision = trusted.load()
    assert decision.approved is False
    assert decision.reasons[0].startswith("EXTERNAL_AUTHORIZATION_INVALID"), decision.reasons


def test_a08_expired_or_revoked_authorization_cannot_be_consumed(trusted) -> None:
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume(now=EXPIRES)
    assert "AUTHORIZATION_NOT_CURRENT" in error.value.reasons
    assert trusted.use_records() == []

    trusted.set_revocations([AUTH_ID])
    with pytest.raises(AuthorizationRejected) as error:
        trusted.consume()
    assert "AUTHORIZATION_REVOKED" in error.value.reasons
    assert trusted.use_records() == []
