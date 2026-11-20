"""R2-03: protocol rejection vs dispatch-layer rejection observation.

A malformed schema, an auxiliary (non-conversation) purpose and an unauthorized
raw-UDS peer are all refused before any Reserve/Claim/Fake.  The request-layer
journal must record the protocol/transport truth, and the legacy dispatch-window
rejection row must not pretend a dispatch existed (``dispatch_seq: null``,
``controller_entered: false``, never ``reserved``/``dispatched``).
"""
from __future__ import annotations

from autoteacher_m0.bridge.protocol import ERROR_CODES
from autoteacher_m0.bridge.request_lifecycle import (
    EVENT_CONTROLLER_ENTERED, EVENT_FAILED_BEFORE_RESERVE, EVENT_PROTOCOL_REJECTED,
    EVENT_RECEIVED,
)

import g4f3_support as f3
import g4r_support as g4r


def _collect(controller, payload):
    frames = []
    for item in controller.handle_envelope(f3.envelope(payload)):
        frames.append({"kind": item.kind, "payload": item.payload})
    return frames


def test_r2_03_bad_schema_rejected_at_request_layer(tmp_path) -> None:
    controller, broker, fake, attempts, gate = g4r.start_real_controller(tmp_path)
    try:
        bad = dict(f3.request_payload())
        bad["unknown_field"] = "x"
        frames = _collect(controller, bad)
        code = f3.call_error(frames)
        assert code in ERROR_CODES and code != "INTERNAL", frames
        rows = g4r.lifecycle_events(tmp_path)
        assert [row["event"] for row in rows] == [EVENT_RECEIVED,
                                                  EVENT_PROTOCOL_REJECTED]
        assert rows[1]["code"] == code
        assert rows[1]["controller_entered"] is False
        assert rows[1]["dispatch_seq"] is None
        assert rows[1]["reserved"] is False
        dispatch = g4r.dispatch_rows(tmp_path)
        assert len(dispatch) == 1, dispatch
        assert dispatch[0]["dispatch_seq"] is None
        assert dispatch[0]["controller_entered"] is False
        assert dispatch[0]["request_level_only"] is True
        assert dispatch[0]["reserved"] is False
        assert dispatch[0]["dispatched"] is False
        assert dispatch[0]["outcome"] == "rejected"
        assert dispatch[0]["error_code"] == code
        state = g4r.broker_snapshot(broker)
        assert state["requests"] == 0 and state["reserved_usd"] == "0", state
        assert fake.received_count() == 0
        assert attempts.attempts() == [] and attempts.pending_intents() == []
    finally:
        f3.close_all(broker, fake, attempts)


def test_r2_03_unknown_purpose_matches_protocol_code(tmp_path) -> None:
    controller, broker, fake, attempts, gate = g4r.start_real_controller(tmp_path)
    try:
        frames = _collect(controller, f3.request_payload(purpose="title"))
        code = f3.call_error(frames)
        assert code == "BAD_TYPE", frames
        rows = g4r.lifecycle_events(tmp_path)
        assert rows[1]["event"] == EVENT_PROTOCOL_REJECTED
        assert rows[1]["code"] == code
        assert rows[0]["purpose"] == "title"
        assert g4r.broker_snapshot(broker)["requests"] == 0
        assert fake.received_count() == 0
        assert attempts.attempts() == []
    finally:
        f3.close_all(broker, fake, attempts)


def test_r2_03_unauthorized_raw_uds_peer_rejected_before_reserve(tmp_path) -> None:
    controller, broker, fake, attempts, gate = g4r.start_real_controller(tmp_path)
    controller.require_origin = True
    payload = f3.request_payload()
    env = f3.envelope(payload)
    # Kernel-reported peer with a UID that is not the Admission launcher UID.
    controller.observe_peer(env.transport_id, uid=4321, gid=4321, pid=1234)
    try:
        frames = []
        for item in controller.handle_envelope(env):
            frames.append({"kind": item.kind, "payload": item.payload})
        code = f3.call_error(frames)
        assert code == "ADMISSION_LAUNCHER_MISMATCH", frames
        rows = g4r.lifecycle_events(tmp_path)
        assert [row["event"] for row in rows] == [
            EVENT_RECEIVED, EVENT_CONTROLLER_ENTERED,
            EVENT_FAILED_BEFORE_RESERVE]
        assert rows[0]["origin_uid"] == 4321
        assert rows[2]["controller_entered"] is True
        assert rows[2]["code"] == code
        assert rows[2]["stage"] == "admission"
        assert rows[2]["reserved"] is False
        assert isinstance(rows[2]["dispatch_seq"], int)
        dispatch = g4r.dispatch_rows(tmp_path)
        assert len(dispatch) == 1, dispatch
        assert dispatch[0]["reserved"] is False
        assert dispatch[0]["dispatched"] is False
        assert dispatch[0]["error_code"] == code
        state = g4r.broker_snapshot(broker)
        assert state["requests"] == 0 and state["reserved_usd"] == "0", state
        assert fake.received_count() == 0
        assert attempts.attempts() == [] and attempts.pending_intents() == []
    finally:
        f3.close_all(broker, fake, attempts)
