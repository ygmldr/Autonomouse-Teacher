"""Phase-2 wheel-only verification; run ONLY in the approved no-Key container.

Keep the original verifier byte-for-byte for historical provenance. This extends
it using the actually installed package API and an explicit standalone probe.
No source package checkout, production Runtime, SDK process or Key is used.
"""
import json
from pathlib import Path
import sys

from verify_installed import emit, execute, main as verify_original_wheel


def main() -> int:
    assert verify_original_wheel() == 0
    from autoteacher_m0.contracts import RuntimeFailure
    from autoteacher_m0.runtime import structured_output

    origin = str(structured_output.__file__)
    assert origin.startswith("/work/site/")
    assert not Path("/project/src/autoteacher_m0/__init__.py").exists()
    good = '{"skill_id":"binary_search","ready":true}'
    output = structured_output.validate_e1_json(good)
    assert isinstance(output, structured_output.E1Output)
    assert output.model_dump() == {"skill_id": "binary_search", "ready": True}
    failures = []
    for text in ('{"skill_id":"binary_search","ready":1}',
                 '{"skill_id":"binary_search","ready":"true"}',
                 '{"skill_id":"binary_search","ready":false}',
                 '{"skill_id":"binary_search","ready":true,"api_key":"sk-FAKE_ONLY"}'):
        try:
            structured_output.validate_e1_json(text)
        except RuntimeFailure as exc:
            assert exc.code == "INVALID_OUTPUT"
            assert exc.__cause__ is None and exc.__context__ is None
            assert "sk-FAKE_ONLY" not in str(exc)
            failures.append(exc.code)
        else:
            raise AssertionError("installed strict E1-02 API accepted invalid output")
    retry = structured_output.run_e1_mock_validation(responses=("{broken", good), max_retries=1)
    assert retry.status == "SUCCESS" and len(retry.attempts) == 2
    assert len({item.run_id for item in retry.attempts}) == 2
    assert retry.attempts[0].error_code == "INVALID_OUTPUT"
    probe = json.loads(execute([sys.executable, "-B", "/input/e1_json_probe.py"]))
    assert probe["offline_validation"] == "PASS" and probe["real_model_json"] == "BLOCKED"
    assert probe["sdk_initialized"] is False and probe["billable_api_calls"] == 0
    assert len(probe["invalid_vectors"]) == 11
    document = {
        "phase": 2, "case_id": "E1-02", "installed_api_origin": origin,
        "cwd": str(Path.cwd()), "source_checkout_visible": False,
        "strict_invalid_checks": failures, "retry": retry.to_dict(),
        "standalone_script_origin": "/input/e1_json_probe.py",
        "standalone_probe": probe, "offline_e1_02": "PASS", "real_e1_02": "BLOCKED",
        "sdk_lifecycle_tested_by_this_verifier": False,
        "production_gate": "UNCHANGED_CLOSED",
    }
    payload = json.dumps(document, indent=2, allow_nan=False).encode()
    assert b"sk-FAKE_ONLY" not in payload
    emit("e1-02-installed.json", payload)
    print("PHASE2_INSTALLED_API_AND_SCRIPT_PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
