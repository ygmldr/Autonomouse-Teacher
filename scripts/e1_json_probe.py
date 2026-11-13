"""Emit E1-02 dedicated OFFLINE evidence; execute ONLY in no-Key isolation.

No Runtime injection, network, SDK startup, credential lookup or Live permission.
The first-round report remains historical; this is a new incremental probe.
"""
import json

from autoteacher_m0.contracts import RuntimeFailure
from autoteacher_m0.runtime.structured_output import (
    E1Output, MAX_E1_JSON_BYTES, run_e1_mock_validation, validate_e1_json,
)

GOOD = '{"skill_id":"binary_search","ready":true}'


def main() -> int:
    vectors = {
        "invalid_json": "{ malformed sk-FAKE_ONLY",
        "missing_field": '{"skill_id":"binary_search"}',
        "integer_not_boolean": '{"skill_id":"binary_search","ready":1}',
        "string_not_boolean": '{"skill_id":"binary_search","ready":"true"}',
        "false_not_ready": '{"skill_id":"binary_search","ready":false}',
        "wrong_skill": '{"skill_id":"other","ready":true}',
        "extra_field": '{"skill_id":"binary_search","ready":true,"api_key":"sk-FAKE_ONLY"}',
        "duplicate_member": '{"skill_id":"binary_search","ready":true,"ready":true}',
        "non_json_nan": '{"skill_id":"binary_search","ready":NaN}',
        "array_not_object": "[]",
        "over_byte_limit": GOOD + " " * MAX_E1_JSON_BYTES,
    }
    checks = []
    for name, text in vectors.items():
        try:
            validate_e1_json(text)
        except RuntimeFailure as exc:
            assert exc.code == "INVALID_OUTPUT"
            assert exc.__context__ is None and exc.__cause__ is None
            assert "sk-FAKE_ONLY" not in str(exc)
            checks.append({"name": name, "status": "PASS", "error_code": exc.code})
        else:
            raise AssertionError("invalid E1-02 test vector was accepted")
    default = run_e1_mock_validation()
    assert isinstance(default.output, E1Output) and default.output.ready is True
    assert default.status == "SUCCESS" and len(default.attempts) == 1
    recovered = run_e1_mock_validation(responses=(vectors["extra_field"], GOOD), max_retries=1)
    assert recovered.status == "SUCCESS" and len(recovered.attempts) == 2
    assert recovered.attempts[0].error_code == "INVALID_OUTPUT"
    assert len({item.run_id for item in recovered.attempts}) == 2
    exhausted = run_e1_mock_validation(responses=(vectors["extra_field"], "broken"), max_retries=1)
    assert exhausted.status == "ERROR" and exhausted.output is None
    assert len(exhausted.attempts) == 2 and exhausted.error_code == "INVALID_OUTPUT"
    document = {
        "case_id": "E1-02", "scope": "DEDICATED_OFFLINE_JSON_PYDANTIC",
        "offline_validation": "PASS", "real_model_json": "BLOCKED",
        "sdk_initialized": False, "billable_api_calls": 0, "billable_cost_usd": "0",
        "max_json_utf8_bytes": MAX_E1_JSON_BYTES, "max_mock_retry": 1,
        "invalid_vectors": checks, "default_existing_mock": default.to_dict(),
        "invalid_then_valid": recovered.to_dict(), "retry_exhausted": exhausted.to_dict(),
        "limits": ["Deterministic local Mock only, not a provider/SDK retry test.",
                   "Production LiveGate and HarnessAdapter remain unchanged and blocked.",
                   "Does not rewrite the first-round NOT RUN evidence or satisfy real E1-02."],
    }
    output = json.dumps(document, indent=2, allow_nan=False)
    assert "sk-FAKE_ONLY" not in output
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
