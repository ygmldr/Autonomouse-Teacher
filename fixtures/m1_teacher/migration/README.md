# B-PR3 legacy v1 fixture (pre-PR3 engine, structured responses)

`schema_v1_structured_legacy.sqlite` is a **genuine** SQLite database written by
the pre-B-PR3 engine at base commit `4706250` (worktree `/root/at-m1a-mvp`),
before any scoped-idempotency code existed. It is committed as a binary test
fixture so the v1 -> v2 migration and the legacy digest adapter are exercised
against real old-engine bytes, not against a current-engine database downgraded
in the test.

Contents (synthetic CF fixtures only, no PII/network/keys):

| learner | session | response kind | `result_id` in fixture |
| --- | --- | --- | --- |
| `m1b.pr3.legacy.structured` | `session.pr3.legacy.structured` | structured dict `{"answer": "A", "why": "because"}` | explicit token `legacy.structured.token.1` |
| `m1b.pr3.legacy.default` | `session.pr3.legacy.default` | same structured dict | old default shape `result:<session>:0:item.bs.mcq.001:622f5b364e154174` |

The old engine's `_canonical_response()` used
`json.dumps(..., sort_keys=True, ensure_ascii=False, allow_nan=False)` **without**
`separators`, so its 16-hex `response_digest` for the dict response is
`622f5b364e154174` (default JSON spacing). B-PR3 new writes use compact JSON,
hence the separate `legacy_request_digest` projection in
`m1_teacher/idempotency.py` (review P1-1).

Schema version is `1`; `result_scopes` does not exist. Tests copy this file to a
temporary directory before opening it (the fixture itself is never mutated).

Regeneration (only when the base fixture must change):

```bash
cd /root/at-m1a-mvp
PYTHONPATH=/root/at-m1a-mvp "/root/Autonomous Teacher/.venv/bin/python" \
    /tmp/gen_pr3_v1_structured_fixture.py \
    /path/to/pr3_v1_structured_legacy.sqlite
```

`pr3_v1_structured_legacy.manifest.json` records the session/item/turn/result ids
and the response payload used by the tests.
