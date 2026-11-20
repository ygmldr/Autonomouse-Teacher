"""Data-integrity tests for the B-PR1 trusted-judge certification fixtures (M1-B).

This module validates the synthetic judge-certification corpus only:

* ``fixtures/m1_teacher/judge/certification/cases.json`` — 14 reference cases with
  the full hidden test set copied from the CC0-1.0 ``m1_offline`` CF fixtures;
* ``fixtures/m1_teacher/judge/certification/negatives.json`` — wrong / syntax-error
  / runtime-exception / timeout / missing-function / edge-correct submissions;
* ``fixtures/m1_teacher/judge/sentinels/sentinels.json`` — synthetic sentinels and
  trust-boundary attack templates.

Guarantees of this test module: offline and deterministic (stdlib only, no network,
no provider/Key), reference solutions are executed locally as *trusted* fixtures to
prove every hidden expected value, and ``TLE`` payloads are **never executed**.  The
module never prints or embeds sentinel values: it only compares existence/booleans.

Evidence class: ``MOCK`` / ``DETERMINISTIC``.
"""

from __future__ import annotations

import ast
import json
import re
import signal
from pathlib import Path, PurePosixPath

# ---------------------------------------------------------------------------
# Paths and frozen corpus constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures" / "m1_teacher"
JUDGE_DIR = FIXTURES_ROOT / "judge"
CERT_DIR = JUDGE_DIR / "certification"
CASES_PATH = CERT_DIR / "cases.json"
NEGATIVES_PATH = CERT_DIR / "negatives.json"
SENTINELS_PATH = JUDGE_DIR / "sentinels" / "sentinels.json"
README_PATH = JUDGE_DIR / "README.md"
ADAPTER_PATH = REPO_ROOT / "m1_teacher" / "domains" / "cf_binary_search.py"

SCHEMA_CASES = "m1b.judge.certification.v0"
SCHEMA_NEGATIVES = "m1b.judge.certification.negatives.v0"
SCHEMA_SENTINELS = "m1b.judge.sentinels.v0"
EVIDENCE_CLASS = "MOCK"
LICENSE_ID = "CC0-1.0"

EXPECTED_CASE_IDS = frozenset(
    {
        "cf_array_max_subarray",
        "cf_array_running_sum",
        "cf_array_sum_even",
        "cf_bs_first_index",
        "cf_bs_search_insert",
        "cf_dp_climb_stairs",
        "cf_dp_coin_change",
        "cf_dp_lcs",
        "cf_graph_bfs_dist",
        "cf_graph_count_components",
        "cf_sort_insertion",
        "cf_tp_dedupe_sorted",
        "cf_tp_is_palindrome",
        "cf_tp_pair_sum_sorted",
    }
)

EXPECTED_FUNCTION_NAMES = {
    "cf_array_max_subarray": "max_subarray_sum",
    "cf_array_running_sum": "running_sum",
    "cf_array_sum_even": "sum_even",
    "cf_bs_first_index": "first_index",
    "cf_bs_search_insert": "search_insert",
    "cf_dp_climb_stairs": "climb_stairs",
    "cf_dp_coin_change": "coin_change",
    "cf_dp_lcs": "lcs_length",
    "cf_graph_bfs_dist": "shortest_path",
    "cf_graph_count_components": "count_components",
    "cf_sort_insertion": "insertion_sort",
    "cf_tp_dedupe_sorted": "dedupe_sorted",
    "cf_tp_is_palindrome": "is_palindrome",
    "cf_tp_pair_sum_sorted": "pair_sum_sorted",
}

EXPECTED_HIDDEN_TEST_TOTAL = 112
MIN_TESTS_PER_CASE = 7

ALLOWED_CASE_FILE_KEYS = {
    "schema_version",
    "evidence_class",
    "synthetic",
    "license",
    "provenance",
    "cases",
}
ALLOWED_CASE_KEYS = {
    "case_id",
    "title",
    "function_name",
    "timeout_s",
    "expected_classification",
    "boundary_note",
    "reference_solution",
    "tests",
}
ALLOWED_TEST_KEYS = {"args", "expected", "kind"}
ALLOWED_TEST_KINDS = {"normal", "edge", "large"}
ALLOWED_NEGATIVE_FILE_KEYS = {
    "schema_version",
    "evidence_class",
    "synthetic",
    "license",
    "negatives",
}
ALLOWED_NEGATIVE_KEYS = {
    "negative_id",
    "case_id",
    "title",
    "description",
    "failure_mode",
    "code",
    "expected_classification",
}
ALLOWED_CLASSIFICATIONS = {"PASS", "WA", "RE", "TLE"}
FAILURE_MODE_CLASSIFICATION = {
    "constant_return": "WA",
    "off_by_one": "WA",
    "edge_correct": "PASS",
    "syntax_error": "RE",
    "runtime_exception": "RE",
    "missing_function": "RE",
    "infinite_loop": "TLE",
}
ALLOWED_SENTINEL_FILE_KEYS = {
    "schema_version",
    "evidence_class",
    "synthetic",
    "license",
    "purpose",
    "sentinel_expected",
    "sentinel_secret_token",
    "host_sentinel_relative_path",
    "host_sentinel_content",
    "attack_templates",
}
ALLOWED_ATTACK_KEYS = {
    "attack_id",
    "attack_family",
    "description",
    "code",
    "expected_blocked",
    "expected_classification",
    "synthetic_test_only",
}
REQUIRED_ATTACK_FAMILIES = frozenset(
    {
        "stack_frame_probe",
        "argv_result_forgery",
        "host_sentinel_read",
        "socket_connect",
        "fork_subprocess",
        "infinite_loop",
        "forged_protocol_output",
        "write_runner_source",
        "exit_code_tamper",
        "exception_override",
    }
)
SENTINEL_VALUE_RE = re.compile(r"^SENTINEL_[A-Za-z0-9_]+$")
BOUNDARY_KEYWORDS = (
    "边界",
    "空",
    "单元素",
    "单字符",
    "单节点",
    "重复",
    "负",
    "不可达",
    "无解",
    "自环",
    "忽略",
    "全",
    "两端",
    "越界",
    "插入位置",
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
IPV4_RE = re.compile(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")
ISO_DATETIME_RE = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
TIMESTAMP_KEY_TOKENS = ("timestamp", "generated_at", "generated_on", "created_at", "updated_at")
ALLOWED_TEST_MODULE_IMPORTS = {"__future__", "ast", "json", "re", "signal", "pathlib"}

# Credential / external-payload tokens that must never appear in this synthetic corpus.
# Stored reversed so any future self-scan of this module cannot match its own denylist.
FORBIDDEN_CORPUS_TOKENS = [
    "https://",
    "http://",
    "://",
    "www.",
    "api_key",
    "api-key",
    "apikey",
    "sk-",
    "bearer ",
    "authorization:",
    "aws_secret",
    "ghp_",
    "xoxb-",
    "-----begin",
    "/root/",
    "/home/",
    "/users/",
    "/etc/",
    "c:\\",
    "password=",
    "passwd=",
    "secret_key",
    "private_key",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rev(value: str) -> str:
    """Reverse a token (kept for denylist construction that is self-scan safe)."""
    return value[::-1]


def _present(text: str, needle: str) -> bool:
    """Existence-only check so failures never echo fixture contents."""
    return needle in text


def _matches(actual: object, expected: object) -> bool:
    """Type-strict equality (bool/int/list distinctions matter for judging)."""
    return type(actual) is type(expected) and actual == expected


def _matches_sentinel_pattern(value: str) -> bool:
    return SENTINEL_VALUE_RE.match(value) is not None


def _is_json_value(value: object) -> bool:
    if isinstance(value, (bool, int, float, str)) or value is None:
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    return False


def _assert_exact_keys(mapping: object, allowed: set, where: str) -> None:
    assert isinstance(mapping, dict), f"{where}: expected a JSON object"
    unknown = sorted(set(mapping) - allowed)
    missing = sorted(allowed - set(mapping))
    assert not unknown, f"{where}: unknown field(s) in strict schema"
    assert not missing, f"{where}: missing required field(s)"


def _load(path: Path) -> tuple:
    assert path.is_file(), f"missing judge certification fixture: {path.name}"
    raw = path.read_text(encoding="utf-8")
    assert raw.strip(), f"empty judge certification fixture: {path.name}"
    assert not raw.startswith("\ufeff"), f"UTF-8 BOM found in judge fixture: {path.name}"
    payload = json.loads(raw)
    assert isinstance(payload, dict), f"judge fixture {path.name} must decode to an object"
    return payload, raw


def _cases() -> list:
    return _load(CASES_PATH)[0]["cases"]


def _negatives() -> list:
    return _load(NEGATIVES_PATH)[0]["negatives"]


def _sentinels() -> dict:
    return _load(SENTINELS_PATH)[0]


def _sentinel_values(data: dict) -> list:
    return [
        data["sentinel_expected"],
        data["sentinel_secret_token"],
        data["host_sentinel_content"],
    ]


def _function_arity(solution: str, function_name: str) -> int:
    tree = ast.parse(solution)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            arguments = node.args
            assert not arguments.vararg and not arguments.kwarg and not arguments.kwonlyargs
            assert not arguments.defaults and not arguments.kw_defaults
            return len(arguments.args)
    raise AssertionError(f"reference solution does not define {function_name!r}")


def _exec_reference(solution: str, function_name: str):
    # Trusted fixture code only: reference solutions copied from CC0 synthetic
    # m1_offline fixtures.  Never use this helper for TLE/negative payloads.
    namespace = {"__name__": "m1b_reference_fixture"}
    exec(compile(solution, "<reference-solution>", "exec"), namespace)  # noqa: S102
    function = namespace.get(function_name)
    assert callable(function), f"reference solution does not define callable {function_name!r}"
    return function


class _TimeLimit:
    """Fail-safe: trusted fixture execution must never hang the test session."""

    def __init__(self, seconds: int) -> None:
        self._seconds = seconds
        self._armed = False

    def __enter__(self):
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, self._on_alarm)
            signal.alarm(self._seconds)
            self._armed = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._armed:
            signal.alarm(0)
        return False

    @staticmethod
    def _on_alarm(signum, frame):  # pragma: no cover - fail-safe path
        raise TimeoutError("trusted fixture execution exceeded the local integrity-test time limit")


# ---------------------------------------------------------------------------
# 1. Layout / hidden separation
# ---------------------------------------------------------------------------


def test_judge_corpus_layout_is_complete_and_isolated():
    assert JUDGE_DIR.is_dir(), "missing judge fixture directory"
    for path in (README_PATH, CASES_PATH, NEGATIVES_PATH, SENTINELS_PATH):
        assert path.is_file(), f"missing judge certification fixture: {path.name}"
    expected_files = {README_PATH, CASES_PATH, NEGATIVES_PATH, SENTINELS_PATH}
    actual_files = {path for path in JUDGE_DIR.rglob("*") if path.is_file()}
    assert actual_files == expected_files, "unexpected or missing files in judge corpus"

    # The teacher-visible DomainAdapter must not be able to read judge material.
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    assert not _present(source, "judge/"), "domain adapter references the judge corpus path"
    assert not _present(source, "attack_templates"), "domain adapter references attack templates"
    assert not _present(source, "sentinels"), "domain adapter references sentinel assets"


# ---------------------------------------------------------------------------
# 2. Strict synthetic JSON documents
# ---------------------------------------------------------------------------


def test_certification_documents_are_strict_synthetic_json():
    cases_doc, cases_raw = _load(CASES_PATH)
    negatives_doc, negatives_raw = _load(NEGATIVES_PATH)
    sentinels_doc, sentinels_raw = _load(SENTINELS_PATH)

    _assert_exact_keys(cases_doc, ALLOWED_CASE_FILE_KEYS, "cases.json")
    _assert_exact_keys(negatives_doc, ALLOWED_NEGATIVE_FILE_KEYS, "negatives.json")
    _assert_exact_keys(sentinels_doc, ALLOWED_SENTINEL_FILE_KEYS, "sentinels.json")

    assert cases_doc["schema_version"] == SCHEMA_CASES
    assert negatives_doc["schema_version"] == SCHEMA_NEGATIVES
    assert sentinels_doc["schema_version"] == SCHEMA_SENTINELS
    for document in (cases_doc, negatives_doc, sentinels_doc):
        assert document["evidence_class"] == EVIDENCE_CLASS
        assert document["synthetic"] is True
        assert document["license"] == LICENSE_ID
    assert isinstance(cases_doc["provenance"], str) and cases_doc["provenance"].strip()
    assert isinstance(sentinels_doc["purpose"], str) and sentinels_doc["purpose"].strip()

    for raw in (cases_raw, negatives_raw, sentinels_raw):
        assert "\r" not in raw, "judge fixtures must use LF line endings"
        assert raw.endswith("\n"), "judge fixtures must end with a newline"


# ---------------------------------------------------------------------------
# 3. Cases: uniqueness / completeness / boundary notes
# ---------------------------------------------------------------------------


def test_cases_are_unique_complete_and_stably_ordered():
    cases = _cases()
    case_ids = [case["case_id"] for case in cases]
    assert len(cases) == 14
    assert len(set(case_ids)) == 14
    assert set(case_ids) == EXPECTED_CASE_IDS
    assert case_ids == sorted(case_ids), "cases must be stably sorted by case_id"
    titles = [case["title"] for case in cases]
    assert all(isinstance(title, str) and title.strip() for title in titles)
    assert len(set(titles)) == 14

    for case in cases:
        case_id = case["case_id"]
        _assert_exact_keys(case, ALLOWED_CASE_KEYS, f"case {case_id}")
        assert case["function_name"] == EXPECTED_FUNCTION_NAMES[case_id]
        timeout = case["timeout_s"]
        assert isinstance(timeout, (int, float)) and not isinstance(timeout, bool)
        assert 0 < float(timeout) <= 10.0
        assert case["expected_classification"] == "PASS"
        assert isinstance(case["reference_solution"], str) and case["reference_solution"].strip()
        boundary_note = case["boundary_note"]
        assert isinstance(boundary_note, str) and len(boundary_note) >= 20
        assert any(keyword in boundary_note for keyword in BOUNDARY_KEYWORDS), (
            f"case {case_id}: boundary_note does not describe an edge condition"
        )


# ---------------------------------------------------------------------------
# 4. Cases: hidden test completeness and shapes
# ---------------------------------------------------------------------------


def test_case_tests_are_complete_boundary_rich_and_arity_consistent():
    total = 0
    for case in _cases():
        case_id = case["case_id"]
        tests = case["tests"]
        assert isinstance(tests, list) and len(tests) >= MIN_TESTS_PER_CASE
        arity = _function_arity(case["reference_solution"], case["function_name"])
        kinds = set()
        for index, test in enumerate(tests):
            _assert_exact_keys(test, ALLOWED_TEST_KEYS, f"{case_id} test[{index}]")
            kind = test["kind"]
            assert kind in ALLOWED_TEST_KINDS
            kinds.add(kind)
            args = test["args"]
            assert isinstance(args, list) and len(args) == arity, (
                f"{case_id} test[{index}]: args count must match reference solution arity"
            )
            assert all(_is_json_value(arg) for arg in args)
            expected = test["expected"]
            assert type(expected) in (bool, int, float, str, list), (
                f"{case_id} test[{index}]: unsupported expected type"
            )
            if isinstance(expected, list):
                assert all(_is_json_value(item) for item in expected)
            json.dumps(test, ensure_ascii=False)
        assert kinds == ALLOWED_TEST_KINDS, (
            f"{case_id}: hidden tests must cover normal, edge and large kinds"
        )
        total += len(tests)
    assert total == EXPECTED_HIDDEN_TEST_TOTAL, "frozen hidden test corpus changed size"


# ---------------------------------------------------------------------------
# 5. Reference solutions: compile / define target / match every expected value
# ---------------------------------------------------------------------------


def test_reference_solutions_compile_and_define_target_function():
    for case in _cases():
        solution = case["reference_solution"]
        tree = ast.parse(solution)
        defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        assert case["function_name"] in defined, (
            f"{case['case_id']}: reference solution does not define the target function"
        )
        assert _function_arity(solution, case["function_name"]) >= 1


def test_reference_solutions_match_every_hidden_expected_value():
    total = 0
    with _TimeLimit(120):
        for case in _cases():
            function = _exec_reference(case["reference_solution"], case["function_name"])
            for index, test in enumerate(case["tests"]):
                actual = function(*test["args"])
                assert _matches(actual, test["expected"]), (
                    f"{case['case_id']}: reference solution mismatch at hidden test index "
                    f"{index} (kind={test['kind']})"
                )
                total += 1
    assert total == EXPECTED_HIDDEN_TEST_TOTAL


# ---------------------------------------------------------------------------
# 6. Negatives: schema / coverage / declared classification
# ---------------------------------------------------------------------------


def test_negatives_cover_required_failure_modes_with_valid_classification():
    cases = {case["case_id"]: case for case in _cases()}
    negatives = _negatives()
    negative_ids = [negative["negative_id"] for negative in negatives]
    assert len(negative_ids) == len(set(negative_ids))
    assert negative_ids == sorted(negative_ids), "negatives must be stably sorted by id"

    observed_modes = set()
    observed_classifications = set()
    for negative in negatives:
        negative_id = negative["negative_id"]
        _assert_exact_keys(negative, ALLOWED_NEGATIVE_KEYS, f"negative {negative_id}")
        assert negative["case_id"] in cases, f"{negative_id}: unknown case reference"
        assert isinstance(negative["title"], str) and negative["title"].strip()
        assert isinstance(negative["description"], str) and negative["description"].strip()
        code = negative["code"]
        assert isinstance(code, str) and code.strip()
        assert len(code) <= 4000, f"{negative_id}: negative code fixture is too large"

        mode = negative["failure_mode"]
        assert mode in FAILURE_MODE_CLASSIFICATION, f"{negative_id}: unknown failure mode"
        observed_modes.add(mode)
        classification = negative["expected_classification"]
        assert classification in ALLOWED_CLASSIFICATIONS
        assert classification == FAILURE_MODE_CLASSIFICATION[mode], (
            f"{negative_id}: classification does not match its failure mode"
        )
        observed_classifications.add(classification)

    assert observed_modes == set(FAILURE_MODE_CLASSIFICATION)
    assert observed_classifications == ALLOWED_CLASSIFICATIONS


# ---------------------------------------------------------------------------
# 7. Negatives: real local execution matches declared classification
# ---------------------------------------------------------------------------


def test_negative_classifications_match_real_local_execution():
    cases = {case["case_id"]: case for case in _cases()}
    with _TimeLimit(120):
        for negative in _negatives():
            negative_id = negative["negative_id"]
            mode = negative["failure_mode"]
            code = negative["code"]
            case = cases[negative["case_id"]]
            function_name = case["function_name"]
            classification = negative["expected_classification"]

            if mode == "infinite_loop":
                # Never execute TLE payloads: a hanging fixture would hang this suite.
                # Certification of TLE belongs to the isolated judge harness only.
                assert classification == "TLE"
                assert _present(code, "while True")
                continue

            if mode == "syntax_error":
                try:
                    compile(code, "<negative-fixture>", "exec")
                except SyntaxError:
                    assert classification == "RE"
                else:
                    raise AssertionError(f"{negative_id}: syntax_error fixture unexpectedly compiles")
                continue

            namespace = {"__name__": "m1b_negative_fixture"}
            exec(compile(code, "<negative-fixture>", "exec"), namespace)  # noqa: S102

            if mode == "missing_function":
                assert not callable(namespace.get(function_name)), (
                    f"{negative_id}: missing_function fixture unexpectedly defines the target"
                )
                assert classification == "RE"
                continue

            function = namespace[function_name]
            if mode == "runtime_exception":
                raised = False
                for test in case["tests"]:
                    try:
                        function(*test["args"])
                    except Exception:
                        raised = True
                        break
                assert raised, f"{negative_id}: runtime_exception fixture did not raise"
                assert classification == "RE"
                continue

            mismatches = 0
            for test in case["tests"]:
                actual = function(*test["args"])
                if not _matches(actual, test["expected"]):
                    mismatches += 1
            if mode == "edge_correct":
                assert mismatches == 0, f"{negative_id}: edge_correct fixture does not pass"
                assert classification == "PASS"
            else:
                assert mismatches > 0, f"{negative_id}: wrong fixture unexpectedly passes"
                assert classification == "WA"


# ---------------------------------------------------------------------------
# 8. Sentinels: unique synthetic values and safe host path
# ---------------------------------------------------------------------------


def test_sentinels_are_unique_synthetic_values_with_safe_relative_host_path():
    sentinels = _sentinels()
    values = _sentinel_values(sentinels)
    for value in values:
        assert isinstance(value, str) and value
        assert _matches_sentinel_pattern(value)
        assert _present(value, "DO_NOT_LEAK")
    assert len(set(values)) == len(values), "sentinel values must be unique"

    host_path = sentinels["host_sentinel_relative_path"]
    assert isinstance(host_path, str) and host_path.strip()
    assert "\\" not in host_path, "host sentinel path must use POSIX separators"
    pure = PurePosixPath(host_path)
    assert not pure.is_absolute(), "host sentinel path must be relative"
    assert ".." not in pure.parts, "host sentinel path must not traverse upwards"
    assert pure.parts[0] == "host_secret"
    assert len(pure.parts) >= 2
    assert pure.suffix == ".txt"


# ---------------------------------------------------------------------------
# 9. Sentinels: attack templates complete, synthetic-only, no PASS expectations
# ---------------------------------------------------------------------------


def test_attack_templates_cover_required_trust_boundary_families():
    sentinels = _sentinels()
    attacks = sentinels["attack_templates"]
    assert isinstance(attacks, list) and attacks
    attack_ids = [attack["attack_id"] for attack in attacks]
    assert len(attack_ids) == len(set(attack_ids))
    assert attack_ids == sorted(attack_ids), "attack templates must be stably sorted by id"

    families = set()
    classifications = set()
    for attack in attacks:
        attack_id = attack["attack_id"]
        _assert_exact_keys(attack, ALLOWED_ATTACK_KEYS, f"attack {attack_id}")
        assert isinstance(attack["description"], str) and attack["description"].strip()
        code = attack["code"]
        assert isinstance(code, str) and code.strip()
        assert len(code) <= 2000, f"{attack_id}: attack code fixture is too large"
        assert _present(code, "SYNTHETIC_TEST_ONLY"), (
            f"{attack_id}: attack template must be marked SYNTHETIC_TEST_ONLY"
        )
        assert attack["expected_blocked"] is True
        assert attack["synthetic_test_only"] is True
        assert attack["expected_classification"] in {"WA", "RE", "TLE"}, (
            f"{attack_id}: a blocked attack must never be expected to PASS"
        )
        families.add(attack["attack_family"])
        classifications.add(attack["expected_classification"])

    assert families == REQUIRED_ATTACK_FAMILIES
    assert classifications == {"WA", "RE", "TLE"}


# ---------------------------------------------------------------------------
# 10. Synthetic corpus: no sentinel embedding, credentials, network payloads
# ---------------------------------------------------------------------------


def test_attack_templates_embed_no_sentinel_values_or_real_payloads():
    sentinels = _sentinels()
    values = _sentinel_values(sentinels)
    attacks = sentinels["attack_templates"]
    for value in values:
        for attack in attacks:
            assert not _present(attack["code"], value), (
                f"{attack['attack_id']}: attack template embeds a sentinel value"
            )

    case_doc, cases_raw = _load(CASES_PATH)
    _, negatives_raw = _load(NEGATIVES_PATH)
    _, sentinels_raw = _load(SENTINELS_PATH)
    readme_raw = README_PATH.read_text(encoding="utf-8")
    for name, raw in (
        ("cases.json", cases_raw),
        ("negatives.json", negatives_raw),
        ("sentinels.json", sentinels_raw),
        ("README.md", readme_raw),
    ):
        lowered = raw.lower()
        for token in FORBIDDEN_CORPUS_TOKENS:
            assert not _present(lowered, token), (
                f"{name}: synthetic corpus contains a credential/payload token"
            )
        assert not EMAIL_RE.search(raw), f"{name}: synthetic corpus contains an email shape"
        assert not IPV4_RE.search(raw), f"{name}: synthetic corpus contains an IP address"
    assert case_doc  # doc loaded for the raw scan above


# ---------------------------------------------------------------------------
# 11. Determinism: no timestamps, no absolute paths, stable ordering
# ---------------------------------------------------------------------------


def test_corpus_is_path_free_timestamp_free_and_stably_ordered():
    for path in (CASES_PATH, NEGATIVES_PATH, SENTINELS_PATH, README_PATH):
        raw = path.read_text(encoding="utf-8")
        lowered = raw.lower()
        assert "\r" not in raw
        assert raw.endswith("\n")
        for needle in TIMESTAMP_KEY_TOKENS:
            assert not _present(lowered, needle), f"{path.name}: synthetic corpus has a timestamp field"
        assert not ISO_DATETIME_RE.search(raw), f"{path.name}: synthetic corpus has an ISO datetime"
        for token in ("/root/", "/home/", "/users/", "/etc/", "c:\\"):
            assert not _present(lowered, token), f"{path.name}: synthetic corpus has an absolute path"

    assert [case["case_id"] for case in _cases()] == sorted(case["case_id"] for case in _cases())
    assert [negative["negative_id"] for negative in _negatives()] == sorted(
        negative["negative_id"] for negative in _negatives()
    )
    assert [attack["attack_id"] for attack in _sentinels()["attack_templates"]] == sorted(
        attack["attack_id"] for attack in _sentinels()["attack_templates"]
    )


# ---------------------------------------------------------------------------
# 12. Teacher-visible fixtures never reference judge material
# ---------------------------------------------------------------------------


def test_teacher_visible_fixtures_never_reference_judge_material():
    sentinels = _sentinels()
    values = _sentinel_values(sentinels)
    visible_paths = [FIXTURES_ROOT / "README.md"] + sorted(
        (FIXTURES_ROOT / "domains").rglob("*.json")
    )
    assert len(visible_paths) > 1
    for path in visible_paths:
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        for value in values:
            assert not _present(text, value), (
                "teacher-visible fixture leaks judge sentinel material"
            )
        assert not _present(text, "judge/"), "teacher-visible fixture references judge corpus"
        assert not _present(text, "attack_templates"), (
            "teacher-visible fixture references judge attack templates"
        )


# ---------------------------------------------------------------------------
# 13. This test module: offline, stdlib only, no hardcoded sentinels
# ---------------------------------------------------------------------------


def test_test_module_is_offline_and_does_not_hardcode_sentinel_values():
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in ALLOWED_TEST_MODULE_IMPORTS, (
                    "integrity test imports a non-stdlib/side-effecting module"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            root = (node.module or "").split(".")[0]
            assert root in ALLOWED_TEST_MODULE_IMPORTS, (
                "integrity test imports a non-stdlib/side-effecting module"
            )

    for value in _sentinel_values(_sentinels()):
        assert not _present(source, value), (
            "integrity test hardcodes a sentinel value (no log/assert leakage)"
        )
    assert not _present(source, _rev("tsetfnoc")), (
        "integrity test must stay independent of shared fixture modules"
    )


# ---------------------------------------------------------------------------
# 14. README: evidence class, provenance, visibility and safety statements
# ---------------------------------------------------------------------------


def test_readme_documents_evidence_class_provenance_and_boundaries():
    text = README_PATH.read_text(encoding="utf-8")
    required_statements = (
        LICENSE_ID,
        "synthetic",
        EVIDENCE_CLASS,
        "DETERMINISTIC",
        "sentinel",
        "Teacher",
        "DomainAdapter",
        "provenance",
        "无网络",
        "mastery",
        "host_sentinel",
        "SYNTHETIC_TEST_ONLY",
    )
    for needle in required_statements:
        assert needle in text, f"judge README is missing required statement: {needle!r}"
    assert "无真实" in text, "judge README must state the no-real-credential rule"
    for value in _sentinel_values(_sentinels()):
        assert not _present(text, value), "judge README leaks a sentinel value"
