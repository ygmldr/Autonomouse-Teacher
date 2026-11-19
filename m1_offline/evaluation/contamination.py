"""Public/hidden fixture separation and contamination scanning (stdlib only).

M1 offline evaluation: teacher-visible surfaces must never contain hidden
problem statements, hidden answers, real personal data or network client
usage.  All scans here are purely local: no network, no external services.

Design notes
------------
* Hidden fixtures are identified by the path segment ``hidden`` (e.g.
  ``fixtures/m1/cf/hidden.json``).  Everything else under ``fixtures/m1`` is
  treated as the public surface.
* Leak detection uses (a) normalized substring needles and (b) sliding-window
  SHA-256 hashes.  The report never echoes hidden text: only hashes, byte
  offsets and the *public* file path where a hit occurred are recorded.
* ``status`` is one of ``PASS`` / ``FAIL`` / ``NOT_RUN``.  ``NOT_RUN`` means
  the required inputs do not exist yet, never a silent pass.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

# ``m1_offline/evaluation/contamination.py`` -> repo root
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]

PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT_RUN"

#: Path segment that marks a fixture as hidden (never teacher visible).
HIDDEN_PATH_MARKER = "hidden"

#: Public / teacher-visible surfaces scanned for hidden leaks.
PUBLIC_GLOBS: tuple[str, ...] = (
    "docs/m1/**/*.md",
    "docs/m1/traces/**/*.jsonl",
    "docs/m1/reports/**/*.json",
    "docs/m1/reports/**/*.md",
    "fixtures/m1/**/*.json",
    "fixtures/m1/**/*.jsonl",
    "fixtures/m1/**/*.md",
    "m1_offline/**/*.py",
)

#: Hidden fixture files (must exist for the separation check to be assessable).
HIDDEN_GLOBS: tuple[str, ...] = (
    "fixtures/m1/**/hidden*.json",
    "fixtures/m1/**/hidden*.jsonl",
    "fixtures/m1/**/hidden/**/*.json",
    "fixtures/m1/**/hidden/**/*.jsonl",
    "fixtures/m1/**/hidden/**/*.md",
)

#: Directories scanned for real data / network usage.
SAFETY_GLOBS: tuple[str, ...] = (
    "m1_offline/**/*.py",
    "fixtures/m1/**/*.json",
    "fixtures/m1/**/*.jsonl",
    "fixtures/m1/**/*.md",
    "tests/m1_offline/**/*.py",
    "docs/m1/**/*.md",
)

NETWORK_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+(httpx|requests|urllib|urllib3|aiohttp|socket|http\.client|ssl)\b",
    re.MULTILINE,
)
API_KEY_RES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}"),
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
#: Reserved documentation domains are allowed in synthetic fixtures.
SYNTHETIC_EMAIL_DOMAINS = frozenset(
    {"example.com", "example.org", "example.net", "example.invalid", "test.invalid"}
)
# Mainland China mobile numbers and US SSN-like patterns (synthetic fixtures
# must not contain these shapes).
CN_MOBILE_RE = re.compile(r"\b1[3-9]\d{9}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

MIN_NEEDLE_LEN = 24
#: Window matching uses stride 1 so a reformatted copy at any offset matches.
WINDOW_WIDTH = 40
WINDOW_STRIDE = 1
MAX_WINDOWS_PER_FILE = 200_000

#: JSON keys whose values are identifiers/labels, not secret content.
_IDENTIFIER_KEYS = frozenset(
    {
        "id",
        "case_id",
        "task_id",
        "problem_id",
        "question_id",
        "learner_id",
        "scorer_id",
        "source_id",
        "jd_id",
        "kind",
        "type",
        "name",
        "language",
        "difficulty",
    }
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """One structured check result (no hidden text in evidence)."""

    check_id: str
    description: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "description": self.description,
            "status": self.status,
            "details": self.details,
            "evidence": self.evidence,
        }


@dataclass
class ContaminationReport:
    checks: list[CheckResult] = field(default_factory=list)
    corpus: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """True only when every check is PASS (NOT_RUN is not OK)."""
        return bool(self.checks) and all(c.status == PASS for c in self.checks)

    @property
    def status_counts(self) -> dict[str, int]:
        counts = {PASS: 0, FAIL: 0, NOT_RUN: 0}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return counts

    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == FAIL]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "m1.contamination.v0",
            "ok": self.ok,
            "status_counts": self.status_counts,
            "corpus": self.corpus,
            "checks": [c.to_dict() for c in self.checks],
            "disclaimer": (
                "Offline synthetic leakage scan on local files only; "
                "not a security audit and not real teaching evidence."
            ),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_files(root: Path, globs: Iterable[str]) -> list[Path]:
    seen: dict[str, Path] = {}
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                seen[str(path)] = path
    return [seen[key] for key in sorted(seen)]


def is_hidden_path(path: Path) -> bool:
    """True when the path names a hidden fixture.

    Only the part *below* the nearest ``fixtures`` directory is inspected so a
    temporary directory whose name happens to contain "hidden" (e.g. a pytest
    ``tmp_path`` for a test called ``test_hidden_leak...``) can never be
    mistaken for a hidden fixture tree.
    """
    parts = [part.lower() for part in Path(path).parts]
    if "fixtures" in parts:
        index = len(parts) - 1 - parts[::-1].index("fixtures")
        candidates = parts[index + 1 :]
    else:
        candidates = parts
    for part in candidates:
        if part == HIDDEN_PATH_MARKER:
            return True
        if (
            part.startswith(f"{HIDDEN_PATH_MARKER}.")
            or part.startswith(f"{HIDDEN_PATH_MARKER}_")
            or part.startswith(f"{HIDDEN_PATH_MARKER}-")
        ):
            return True
    return False


def hidden_fixture_files(root: Path | str = DEFAULT_REPO_ROOT) -> list[Path]:
    root = Path(root)
    return [p for p in _iter_files(root, HIDDEN_GLOBS) if is_hidden_path(p)]


def public_surface_files(root: Path | str = DEFAULT_REPO_ROOT) -> list[Path]:
    root = Path(root)
    return [p for p in _iter_files(root, PUBLIC_GLOBS) if not is_hidden_path(p)]


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def normalize_text(text: str) -> str:
    """Normalize for substring matching: collapse whitespace, casefold."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _compact(text: str) -> str:
    """Remove all whitespace for hash-window matching."""
    return re.sub(r"\s+", "", text).casefold()


def extract_hidden_strings(value: Any, *, key: str | None = None) -> list[str]:
    """Recursively collect candidate hidden needles from parsed fixtures."""
    found: list[str] = []
    if isinstance(value, str):
        if key is not None and key.lower() in _IDENTIFIER_KEYS:
            return found
        normalized = normalize_text(value)
        if len(normalized) >= MIN_NEEDLE_LEN and not normalized.isdigit():
            found.append(normalized)
    elif isinstance(value, dict):
        for child_key, child in value.items():
            found.extend(extract_hidden_strings(child, key=str(child_key)))
    elif isinstance(value, list):
        for child in value:
            found.extend(extract_hidden_strings(child))
    return found


def _sampled_window_hashes(text: str, *, max_windows: int = 2000) -> set[str]:
    """Bounded sliding-window hashes sampled across a (possibly large) text.

    Hidden CF fixtures embed very large numeric arrays; hashing every offset
    would be too slow, so the stride adapts to keep at most ``max_windows``
    windows per file.  String needles still cover exact copy-paste leaks.
    """
    compact = _compact(text)
    if len(compact) < WINDOW_WIDTH:
        return set()
    step = max(WINDOW_STRIDE, (len(compact) - WINDOW_WIDTH) // max_windows or 1)
    hashes: set[str] = set()
    for start in range(0, len(compact) - WINDOW_WIDTH + 1, step):
        window = compact[start : start + WINDOW_WIDTH]
        hashes.add(hashlib.sha256(window.encode("utf-8")).hexdigest()[:16])
        if len(hashes) >= max_windows:
            break
    return hashes


def _hidden_strings_for(path: Path, text: str) -> list[str]:
    """Candidate hidden needles for one hidden fixture file (no raw echo)."""
    strings: list[str] = []
    if path.suffix == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            strings.extend(extract_hidden_strings(parsed))
    elif path.suffix == ".jsonl":
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            strings.extend(extract_hidden_strings(parsed))
    elif path.suffix == ".md":
        normalized = normalize_text(text)
        if len(normalized) >= MIN_NEEDLE_LEN:
            strings.append(normalized)
    return strings


def hidden_corpus(
    root: Path | str = DEFAULT_REPO_ROOT,
) -> tuple[list[str], set[str], dict[str, Any]]:
    """Collect (needles, window-hashes, corpus_meta) from hidden fixtures.

    corpus_meta contains only counts/hashes — never hidden text.
    """
    root = Path(root)
    needles: list[str] = []
    windows: set[str] = set()
    files: list[dict[str, Any]] = []
    for path in hidden_fixture_files(root):
        raw = path.read_bytes()
        text = _decode(raw)
        strings = _hidden_strings_for(path, text)
        needles.extend(strings)
        for needle in strings:
            windows.update(window_hashes(needle))
        windows.update(_sampled_window_hashes(text))
        files.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(raw).hexdigest()[:16],
                "candidate_needles": len(strings),
            }
        )
    # De-duplicate, longest first so evidence is stable.
    unique = sorted(set(needles), key=lambda s: (-len(s), s))
    meta = {
        "hidden_files": files,
        "needle_count": len(unique),
        "window_hash_count": len(windows),
    }
    return unique, windows, meta


def hidden_needles(root: Path | str = DEFAULT_REPO_ROOT) -> tuple[list[str], dict[str, Any]]:
    """Collect (needles, corpus_meta) from hidden fixture files."""
    needles, _windows, meta = hidden_corpus(root)
    return needles, meta


def window_hashes(text: str) -> dict[str, int]:
    """Sliding-window SHA-256 hashes of whitespace-stripped normalized text."""
    compact = _compact(text)
    hashes: dict[str, int] = {}
    if len(compact) < WINDOW_WIDTH:
        return hashes
    max_windows = MAX_WINDOWS_PER_FILE
    for start in range(0, len(compact) - WINDOW_WIDTH + 1, WINDOW_STRIDE):
        if len(hashes) >= max_windows:
            break
        window = compact[start : start + WINDOW_WIDTH]
        digest = hashlib.sha256(window.encode("utf-8")).hexdigest()[:16]
        hashes.setdefault(digest, start)
    return hashes


def _scan_text_for_needles(
    path: Path, text: str, needles: Sequence[str], *, max_hits: int = 50
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    normalized = normalize_text(text)
    for needle in needles:
        index = normalized.find(needle)
        if index >= 0:
            hits.append(
                {
                    "path": str(path),
                    "needle_sha256": hashlib.sha256(needle.encode("utf-8")).hexdigest()[:16],
                    "needle_len": len(needle),
                    "offset": index,
                }
            )
            if len(hits) >= max_hits:
                break
    return hits


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_hidden_public_separation(root: Path | str = DEFAULT_REPO_ROOT) -> CheckResult:
    """Hidden fixtures exist and are disjoint from the scanned public surface."""
    root = Path(root)
    hidden = hidden_fixture_files(root)
    public = public_surface_files(root)
    hidden_public_overlap = [str(p) for p in hidden if p in set(public)]
    details = {
        "hidden_file_count": len(hidden),
        "public_file_count": len(public),
        "hidden_paths": [str(p.relative_to(root)) for p in hidden],
        "overlap": hidden_public_overlap,
    }
    if not hidden:
        return CheckResult(
            "C1_hidden_public_separation",
            "hidden fixtures exist and are not part of the public surface",
            NOT_RUN,
            details,
        )
    status = FAIL if hidden_public_overlap else PASS
    return CheckResult(
        "C1_hidden_public_separation",
        "hidden fixtures exist and are not part of the public surface",
        status,
        details,
    )


def check_hidden_leakage(
    root: Path | str = DEFAULT_REPO_ROOT,
) -> tuple[CheckResult, dict[str, Any]]:
    """No hidden-only needle / hidden text window appears on the public surface.

    A hidden fixture may legitimately repeat public problem statements (the
    hidden set is a superset of the public task).  Those shared strings are
    subtracted from the needle/window sets so only *hidden-only* content is
    checked.  Hidden-only content must not appear in public docs, public
    traces, public fixtures or teacher-visible prompt sources.
    """
    root = Path(root)
    needles, hidden_window_hashes, corpus_meta = hidden_corpus(root)
    public_files = public_surface_files(root)
    hidden_files = hidden_fixture_files(root)

    # Public fixtures are the legitimate baseline; subtract them.
    fixture_blob_parts: list[str] = []
    public_fixture_windows: set[str] = set()
    for path in _iter_files(root, ("fixtures/m1/**/*",)):
        if not path.is_file() or is_hidden_path(path):
            continue
        text = _decode(path.read_bytes())
        fixture_blob_parts.append(normalize_text(text))
        public_fixture_windows.update(window_hashes(text).keys())
    fixture_blob = "\n".join(fixture_blob_parts)

    hidden_only_needles = [n for n in needles if n not in fixture_blob]
    hidden_windows = set(hidden_window_hashes) - public_fixture_windows

    needles = hidden_only_needles
    substring_hits: list[dict[str, Any]] = []
    hash_hits: list[dict[str, Any]] = []

    for path in public_files:
        text = _decode(path.read_bytes())
        substring_hits.extend(_scan_text_for_needles(path.relative_to(root), text, needles))
        if hidden_windows:
            for digest, offset in window_hashes(text).items():
                if digest in hidden_windows:
                    hash_hits.append(
                        {
                            "path": str(path.relative_to(root)),
                            "window_sha256": digest,
                            "offset": offset,
                        }
                    )
                    if len(hash_hits) >= 50:
                        break
        if len(substring_hits) >= 100:
            break

    details = {
        "scanned_public_files": len(public_files),
        "substring_hits": len(substring_hits),
        "hash_window_hits": len(hash_hits),
        "needles_checked": len(needles),
    }
    evidence = [{"kind": "substring", **hit} for hit in substring_hits[:20]]
    evidence += [{"kind": "hash_window", **hit} for hit in hash_hits[:20]]
    if not hidden_files:
        return (
            CheckResult(
                "C2_hidden_leakage",
                "hidden-only fixture text does not appear in public docs/traces/fixtures/teacher sources",
                NOT_RUN,
                details,
                evidence,
            ),
            corpus_meta,
        )
    if not public_files:
        return (
            CheckResult(
                "C2_hidden_leakage",
                "hidden-only fixture text does not appear in public docs/traces/fixtures/teacher sources",
                NOT_RUN,
                details,
                evidence,
            ),
            corpus_meta,
        )
    status = FAIL if (substring_hits or hash_hits) else PASS
    return (
        CheckResult(
            "C2_hidden_leakage",
            "hidden-only fixture text does not appear in public docs/traces/fixtures/teacher sources",
            status,
            details,
            evidence,
        ),
        corpus_meta,
    )


def check_injection_not_in_system_prompt(
    injection_texts: Sequence[str], system_instructions: Sequence[str]
) -> CheckResult:
    """Prompt-injection documents must not be pasted into system instructions.

    The injection payload is untrusted *data*; if (a normalized chunk of it)
    appears verbatim in the system prompt it has been promoted to trusted
    instructions and the check fails.
    """
    system_blob = normalize_text("\n".join(system_instructions))
    needles: list[str] = []
    for text in injection_texts:
        normalized = normalize_text(text)
        for paragraph in re.split(r"[\n。.!?！？]+", normalized):
            paragraph = paragraph.strip()
            if len(paragraph) >= MIN_NEEDLE_LEN:
                needles.append(paragraph)
    hits = [
        {
            "needle_sha256": hashlib.sha256(needle.encode("utf-8")).hexdigest()[:16],
            "needle_len": len(needle),
        }
        for needle in dict.fromkeys(needles)
        if needle in system_blob
    ]
    details = {
        "injection_documents": len(injection_texts),
        "system_instruction_chunks": len(system_instructions),
        "needles_checked": len(set(needles)),
    }
    if not injection_texts or not system_instructions:
        return CheckResult(
            "C3_injection_not_in_system_prompt",
            "untrusted injection documents never appear verbatim in system instructions",
            NOT_RUN,
            details,
            hits,
        )
    return CheckResult(
        "C3_injection_not_in_system_prompt",
        "untrusted injection documents never appear verbatim in system instructions",
        FAIL if hits else PASS,
        details,
        hits,
    )


def check_no_network_or_real_data(
    root: Path | str = DEFAULT_REPO_ROOT, allowed_imports: Sequence[str] = ()
) -> CheckResult:
    """Scoped files contain no network-client imports, keys or real-data shapes."""
    root = Path(root)
    allowed = {name.casefold() for name in allowed_imports}
    findings: list[dict[str, Any]] = []
    scanned = 0
    for path in _iter_files(root, SAFETY_GLOBS):
        scanned += 1
        text = _decode(path.read_bytes())
        rel = str(path.relative_to(root))
        for match in NETWORK_IMPORT_RE.finditer(text):
            module = match.group(1).casefold()
            if module in allowed:
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append({"path": rel, "line": line, "kind": "network_import", "module": module})
        for pattern in API_KEY_RES:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    {
                        "path": rel,
                        "line": line,
                        "kind": "api_key_shape",
                        "sha256": hashlib.sha256(match.group(0).encode()).hexdigest()[:16],
                    }
                )
        for label, pattern in (
            ("email_address", EMAIL_RE),
            ("cn_mobile_number", CN_MOBILE_RE),
            ("ssn_shape", SSN_RE),
        ):
            for match in pattern.finditer(text):
                if label == "email_address":
                    domain = match.group(0).rsplit("@", 1)[-1].casefold()
                    if domain in SYNTHETIC_EMAIL_DOMAINS:
                        continue
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    {
                        "path": rel,
                        "line": line,
                        "kind": label,
                        "sha256": hashlib.sha256(match.group(0).encode()).hexdigest()[:16],
                    }
                )
    details = {
        "scanned_files": scanned,
        "findings": len(findings),
        "allowed_imports": sorted(allowed),
    }
    return CheckResult(
        "C4_no_network_or_real_data",
        "scoped code/fixtures/docs contain no network imports, API keys or real-data shapes",
        FAIL if findings else (PASS if scanned else NOT_RUN),
        details,
        findings[:50],
    )


# ---------------------------------------------------------------------------
# Suite entry points
# ---------------------------------------------------------------------------


def run_contamination_suite(
    root: Path | str = DEFAULT_REPO_ROOT,
    *,
    injection_texts: Sequence[str] = (),
    system_instructions: Sequence[str] = (),
    allowed_imports: Sequence[str] = (),
) -> ContaminationReport:
    """Run all checks and return a structured report (never echoes hidden text)."""
    root = Path(root)
    separation = check_hidden_public_separation(root)
    leakage, corpus_meta = check_hidden_leakage(root)
    injection = check_injection_not_in_system_prompt(injection_texts, system_instructions)
    safety = check_no_network_or_real_data(root, allowed_imports=allowed_imports)
    return ContaminationReport(
        checks=[separation, leakage, injection, safety],
        corpus={"repo_root": str(root), **corpus_meta},
    )


def load_injection_texts(root: Path | str = DEFAULT_REPO_ROOT) -> list[str]:
    """Best-effort load of interview prompt-injection fixture texts (public data).

    Injection documents are untrusted *data*: the check verifies they are never
    promoted into trusted system instructions.
    """
    root = Path(root)
    texts: list[str] = []
    interview_dir = root / "fixtures/m1/interview"
    if not interview_dir.is_dir():
        return texts
    for path in sorted(interview_dir.rglob("*.json")):
        if "injection" not in str(path.relative_to(interview_dir)).casefold():
            continue
        try:
            parsed = json.loads(_decode(path.read_bytes()))
        except json.JSONDecodeError:
            continue
        texts.extend(extract_hidden_strings(parsed))
    return texts
