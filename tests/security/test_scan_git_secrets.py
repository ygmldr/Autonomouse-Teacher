"""Offline tests for the repository secret scanner (G4-F1).

No real credentials, network, model calls or Live approval are involved. Every
synthetic token below is assembled at runtime (or with string concatenation) so
that this test file does not itself contain a scanner-detectable literal value.

Runs under pytest or directly: ``python3 -B tests/security/test_scan_git_secrets.py``.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = REPO_ROOT / "scripts" / "security" / "scan_git_secrets.py"
_SPEC = importlib.util.spec_from_file_location("scan_git_secrets", SCANNER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
scanner = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = scanner
_SPEC.loader.exec_module(scanner)


def _run_scanner(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(SCANNER_PATH), *args],
        cwd=str(cwd or REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=env,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE)


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True, stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE)
    _git(repo, "config", "user.email", "scanner-tests@example.invalid")
    _git(repo, "config", "user.name", "scanner tests")
    _git(repo, "config", "commit.gpgsign", "false")


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _kinds(text: str) -> set[str]:
    return {finding.kind for finding in scanner._scan_text(text, "synthetic.txt", "test")}


def _pem(label: str, block: bool = False) -> str:
    suffix = " BLOCK" if block else ""
    return "-----BEGIN " + label + "PRIVATE KEY" + suffix + "-----"


def _synthetic_material() -> dict[str, str]:
    return {
        "hex": hashlib.sha256(b"g4f-scanner-tests-hex-not-a-credential").hexdigest(),
        "b64": base64.b64encode(
            hashlib.sha256(b"g4f-scanner-tests-b64-not-a-credential").digest()
        ).decode(),
        "openai": "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6",
        "aws": "AKIA" + "ABCDEFGHIJKLMNOP",
        "gcp": "AIza" + "A" * 35,
        "slack": "xoxb-" + "1" * 20,
        "github": "ghp_" + "a" * 36,
        "gitlab": "glpat-" + "a" * 24,
        "npm": "npm_" + "a" * 36,
        "hf": "hf_" + "a" * 34,
        "jwt": "eyJ" + "a" * 20 + "." + "b" * 20 + "." + "c" * 20,
        "jwe": "eyJ" + "a" * 20 + ("." + "b" * 20) * 4,
        "basic": base64.b64encode(
            ("scanner-user:" + hashlib.sha256(b"g4f-basic").hexdigest()).encode()
        ).decode(),
        "webhook": "https://hooks.slack.com/services/" + "T" * 9 + "/" + "B" * 9
        + "/" + "Z" * 24,
        "account_key": "AccountKey=" + "A" * 44 + "==",
    }


def _positive_cases() -> list[tuple[str, str]]:
    material = _synthetic_material()
    high = material["hex"]
    high_b64 = material["b64"]
    return [
        (material["openai"], "openai-key"),
        (material["aws"], "aws-access-key"),
        (material["gcp"], "gcp-api-key"),
        (material["slack"], "slack-token"),
        (material["webhook"], "slack-webhook"),
        (material["github"], "github-token"),
        (material["gitlab"], "gitlab-token"),
        (material["npm"], "npm-token"),
        (material["hf"], "huggingface-token"),
        (material["account_key"], "azure-account-key"),
        (material["jwt"], "jwt"),
        (material["jwe"], "jwe"),
        ("Authorization: Bearer " + "Z" * 40, "bearer-token"),
        ("Authorization: Basic " + material["basic"], "basic-auth"),
        ("Proxy-Authorization: Basic " + material["basic"], "basic-auth"),
        ("DEEPSEEK_API_KEY=" + material["openai"], "env-key-assignment"),
        ("deepseek_api_key=" + high + ";", "env-key-assignment"),
        ("DEEPSEEK_API_KEY = \"" + high + "\"", "env-key-assignment"),
        ("AWS_SECRET_ACCESS_KEY=" + high, "env-key-assignment"),
        ("AZURE_CLIENT_SECRET=" + high, "env-key-assignment"),
        ("GCP_API_KEY=" + high, "env-key-assignment"),
        ("HF_TOKEN=" + high, "env-key-assignment"),
        ("GITLAB_TOKEN=" + high, "env-key-assignment"),
        ("NPM_TOKEN=" + high, "env-key-assignment"),
        ("SLACK_BOT_TOKEN=" + high, "env-key-assignment"),
        ("DATABASE_PASSWORD=" + high, "env-key-assignment"),
        ("MY_SERVICE_TOKEN=" + high, "env-key-assignment"),
        ("SIGNING_KEY=" + high, "env-key-assignment"),
        ("password: \"" + high + "\"", "env-key-assignment"),
        ("\"api_key\": \"" + high_b64 + "\"", "env-key-assignment"),
        ("client_secret: " + high_b64, "env-key-assignment"),
        ("postgresql://user:" + "S3cret" + "Pass@db.example/x", "db-url-password"),
        ("mysql://app:" + high + "@db.internal:3306/app", "db-url-password"),
        ("mongodb+srv://app:" + high + "@cluster.example/app", "db-url-password"),
        ("Server=db.internal;Database=app;User Id=app;Password=" + high + ";",
         "connection-string-password"),
        ("https://203.0.113.10/v1/resource?token=" + high, "url-query-secret"),
        ("https://203.0.113.10/cb?api_key=" + high + "&x=1", "url-query-secret"),
        ("-----BEGIN " + "RSA PRIVATE KEY" + "-----", "private-key-header"),
        (_pem(""), "private-key-header"),
        (_pem("EC "), "private-key-header"),
        (_pem("OPENSSH "), "private-key-header"),
        (_pem("ENCRYPTED "), "private-key-header"),
        (_pem("PGP ", block=True), "private-key-header"),
    ]


def test_self_test_passes() -> None:
    proc = _run_scanner("--self-test")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELFTEST PASS" in proc.stdout


def test_repository_worktree_and_history_is_clean() -> None:
    proc = _run_scanner("--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["findings"] == []
    assert payload["scanned"]["files"] > 0
    assert payload["scanned"]["blobs"] > 0
    assert payload["scanned"]["commits"] > 0


def test_positive_detectors() -> None:
    for text, expected in _positive_cases():
        kinds = _kinds(text)
        assert expected in kinds, f"missing {expected} for {text[:48]!r}"


def test_strict_sentinel_exclusions() -> None:
    for prefix in scanner.ENV_SENTINEL_PREFIXES:
        text = "DEEPSEEK_API_KEY=" + prefix.upper() + "_SELFTEST_VALUE"
        assert not _kinds(text), f"sentinel prefix was flagged: {prefix}"
    for value in ("SENTINEL", "sentinel", "SeNtInEl", "SENTINEL)", "SENTINEL" + "`",
                  "SENTINEL" + "\\n", "sentinel_fake_value",
                  "TEST_ONLY_NEVER_VALID_SECRET_SENTINEL"):
        assert not _kinds("DEEPSEEK_API_KEY=" + value), f"sentinel was flagged: {value}"
    assert not _kinds('DEEPSEEK_API_KEY="SENTINEL".')
    assert not _kinds("DEEPSEEK_API_KEY=SENTINEL   ")
    assert not _kinds("deepseek_api_key=SENTINEL")
    assert not _kinds("MY_SERVICE_TOKEN=TEST_ONLY_NEVER_VALID_SECRET_SENTINEL")
    assert not _kinds("password: \"SENTINEL\"")
    assert not _kinds("Authorization: Bearer abc...")
    assert not _kinds("Authorization: Basic not-base64-value")
    assert "url-query-secret" in _kinds(
        "https://203.0.113.10/cb?token=" + _synthetic_material()["hex"])
    assert not _kinds("TOKEN = \"session-token\"")
    assert not _kinds("key=sk-" + "FAKE-" + "A" * 32)
    assert not _kinds("OPENAI_API_KEY=sk-" + "FAKE-" + "A" * 32)


def test_sentinel_lookalikes_are_reported() -> None:
    material = _synthetic_material()
    attacks = [
        "SENTINEL" + material["hex"],
        "SENTINEL" + material["openai"],
        "TEST_ONLY_" + material["hex"],
        "TEST_ONLY_" + material["b64"],
        "sentinel_abc123",
        "SENTINEL_" + "1234567890" * 6,
    ]
    for value in attacks:
        assert scanner._is_env_test_sentinel(value) is False, value[:24]
        kinds = _kinds("DEEPSEEK_API_KEY=" + value)
        assert "env-key-assignment" in kinds, f"look-alike was not reported: {value[:24]}"
    # Prefix containers that merely contain SENTINEL later are always reported.
    embedded = "ZzSENTINEL" + "A" * 24
    assert "env-key-assignment" in _kinds("DEEPSEEK_API_KEY=" + embedded)


def test_temporary_repo_positive_exit_1_and_masking() -> None:
    material = _synthetic_material()
    secret = material["hex"]
    with tempfile.TemporaryDirectory(prefix="g4f-scanner-positive-") as raw:
        repo = Path(raw)
        _init_repo(repo)
        (repo / "config").mkdir()
        (repo / "config" / "settings.yaml").write_text(
            "service:\n  password: \"" + secret + "\"\n", encoding="utf-8")
        (repo / "notes.txt").write_text("no credentials here\n", encoding="utf-8")
        _commit(repo, "synthetic positive fixture")
        proc = _run_scanner("--root", str(repo), "--json")
        assert proc.returncode == 1, proc.stdout + proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["ok"] is False
        assert payload["findings"]
        assert secret not in proc.stdout
        assert secret not in proc.stderr
        masked = " ".join(finding["masked"] for finding in payload["findings"])
        assert "…(len " in masked or "\\u2026(len " in proc.stdout
        assert masked.startswith("PASSWORD=")
        # The worktree-only scan must fail the same way.
        no_history = _run_scanner("--root", str(repo), "--no-history")
        assert no_history.returncode == 1
        assert secret not in no_history.stdout


def test_temporary_repo_clean_exit_0() -> None:
    material = _synthetic_material()
    with tempfile.TemporaryDirectory(prefix="g4f-scanner-clean-") as raw:
        repo = Path(raw)
        _init_repo(repo)
        (repo / ".env.example").write_text(
            "DEEPSEEK_API_KEY=SENTINEL\n"
            "OPENAI_API_KEY=sk-" + "FAKE-" + "A" * 32 + "\n"
            "MY_SERVICE_TOKEN=TEST_ONLY_NEVER_VALID_SECRET_SENTINEL\n"
            "HF_TOKEN=\"SENTINEL\"\n"
            "password: \"SENTINEL\"\n"
            "Authorization: Bearer abc...\n",
            encoding="utf-8")
        (repo / "README.md").write_text(
            "Example only: DEEPSEEK_API_KEY=SENTINEL and sk-" + "FAKE-example\n",
            encoding="utf-8")
        _commit(repo, "synthetic sentinel-only fixture")
        proc = _run_scanner("--root", str(repo))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "SECRET SCAN OK" in proc.stdout
        assert material["hex"] not in proc.stdout


def main() -> int:
    tests = [
        test_self_test_passes,
        test_repository_worktree_and_history_is_clean,
        test_positive_detectors,
        test_strict_sentinel_exclusions,
        test_sentinel_lookalikes_are_reported,
        test_temporary_repo_positive_exit_1_and_masking,
        test_temporary_repo_clean_exit_0,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception:  # noqa: BLE001 - standalone runner reports every failure
            failed += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    print(f"SECURITY TESTS: {len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
