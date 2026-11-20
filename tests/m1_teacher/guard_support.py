"""Static guard helpers for hidden-scoring material isolation (B-PR4 P1-2).

The hidden interview scoring tree is read by exactly two scorer-side modules
(:mod:`m1_teacher.assessment.scorer` and
:mod:`m1_teacher.assessment.interview_judge`).  String matching on the literal
``"scoring/"`` is not enough to enforce that boundary (e.g. path fragments such
as ``Path("rubrics") / "scoring" / "q.json"`` or f-string pieces evade it), so
these helpers parse the AST and match **path components**.

They are test support only (not shipped runtime code) and perform no I/O beyond
reading the Python sources they are given.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from pathlib import Path

HIDDEN_DIR_NAME = "scoring"
HIDDEN_PATH_MARKER = HIDDEN_DIR_NAME + "/"

#: The only modules allowed to read hidden scoring material (scorer-side).
DEFAULT_HIDDEN_READERS = frozenset({"scorer.py", "interview_judge.py"})

_RAW_HIDDEN_COMPONENT_RE = re.compile(
    r"(?:^|[/\\\"'])" + re.escape(HIDDEN_DIR_NAME) + r"(?:[/\\\"']|$)"
)


def _normalise(value: str) -> str:
    return value.replace("\\", "/")


def _has_hidden_path_component(value: str) -> bool:
    """True when a string literal constructs/embeds a ``**/scoring/**`` path."""

    normalised = _normalise(value)
    parts = [part for part in normalised.split("/") if part]
    if HIDDEN_DIR_NAME in parts:
        return True
    # A single literal that embeds the component between separators
    # (e.g. "vertical/interview/rubrics/scoring/q.json") is covered by the
    # component check above; this catches unusual spacing/punctuation variants.
    return bool(_RAW_HIDDEN_COMPONENT_RE.search(normalised))


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def scan_hidden_scoring_references(
    paths: Iterable[Path], *, allowlist: frozenset[str] = DEFAULT_HIDDEN_READERS
) -> list[str]:
    """Return source paths that reference a hidden ``**/scoring/**`` path.

    Detection is AST/path-component based (string constants, including path
    join fragments), not a single literal-substring scan.  Files whose *name* is
    in ``allowlist`` are skipped (the scorer-side readers).  ``allowlist`` must
    be exactly the intended reader set; callers should assert that explicitly.
    """

    offenders: list[str] = []
    for path in paths:
        if path.name in allowlist:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover - repository sources are valid
            offenders.append(f"{path}: SYNTAX_ERROR")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _has_hidden_path_component(node.value):
                    offenders.append(str(path))
                    break
            elif isinstance(node, ast.JoinedStr):
                for value in node.values:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        if _has_hidden_path_component(value.value):
                            offenders.append(str(path))
                            break
    return sorted(set(offenders))


def scan_hidden_reader_allowlist(
    package_root: Path, *, allowlist: frozenset[str] = DEFAULT_HIDDEN_READERS
) -> list[str]:
    """Scan ``package_root`` for hidden readers and return offending paths."""

    return scan_hidden_scoring_references(_python_files(package_root), allowlist=allowlist)
