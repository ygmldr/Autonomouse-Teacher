"""A-NEXT CI static validation: branch provenance, protected files, H0 cherry-picks.

This tool is a *static, read-only* gate.  It never modifies the repository and
never writes outside ``--json-out``.  It is meant to run in CI before a PR is
accepted into the G4-R/A-NEXT integration branch.

Subcommands
-----------
branch        HEAD must descend from the declared source (main vs work/g4r) at
              the declared base, and must not smuggle the other lineage in.
protected     list (and by default fail on) changes under protected security
              paths relative to the base.
cherry-pick   detect H0 (``work/m0-g4h0``) merges/cherry-picks: ancestor check,
              patch-id comparison and commit-subject hints.
merges        reject merge commits that are not explicitly allow-listed.
all           run every check and emit one JSON summary.

Exit codes
----------
0  OK
2  usage error
31 branch provenance/lineage violation
32 unauthorized merge commit
33 protected file change without an explicit allow entry
34 H0 cherry-pick / merge risk detected
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as common  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BRANCH = 31
EXIT_UNAUTHORIZED_MERGE = 32
EXIT_PROTECTED = 33
EXIT_CHERRY_PICK = 34

PROTECTED_PREFIXES = (
    "src/autoteacher_m0/security/",
    "src/autoteacher_m0/bridge/controller.py",
    "src/autoteacher_m0/bridge/recovery_diagnostics.py",
    "src/autoteacher_m0/bridge/request_lifecycle.py",
    "src/autoteacher_m0/runtime/dsh_adapter.py",
    "src/autoteacher_m0/cli.py",
    "scripts/run_live.sh",
    "config/g4/runtime-policy.json",
    "config/g4/",
)

H0_HINT_PATTERN = re.compile(r"(?i)(?:g4-?h0|m0-g4h0|h0[-_ ]?(?:impl|fix|cherry))")
DEFAULT_H0_REF = "work/m0-g4h0"


def utc_now() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def is_protected(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def resolve_ref(repo: Path, name: str) -> str | None:
    proc = common.git(repo, "rev-parse", "--verify", f"{name}^{{commit}}", check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def emit(document: dict, json_out: str | None) -> None:
    if json_out:
        Path(json_out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    json.dump(document, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# branch
# ---------------------------------------------------------------------------
def check_branch(args: argparse.Namespace) -> tuple[int, dict]:
    repo = Path(args.repo).resolve()
    document: dict = {"command": "branch", "utc": utc_now(), "repo": str(repo)}
    try:
        head = common.git(repo, "rev-parse", "HEAD").stdout.strip()
        base = common.git(repo, "rev-parse", "--verify", f"{args.base}^{{commit}}").stdout.strip()
        branch = common.git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        source_ref = resolve_ref(repo, args.source)
        g4r_ref = resolve_ref(repo, "work/g4r")
        main_ref = resolve_ref(repo, "main")
        document.update(
            {
                "head": head,
                "branch": branch,
                "base": base,
                "source": args.source,
                "source_ref": source_ref,
                "g4r_ref": g4r_ref,
                "main_ref": main_ref,
            }
        )
        problems: list[str] = []
        if source_ref is None:
            problems.append(f"source_ref_missing:{args.source}")
        else:
            # base must be an ancestor of HEAD and HEAD must branch from source at base
            ancestor = common.git(repo, "merge-base", "--is-ancestor", base, head, check=False)
            if ancestor.returncode != 0:
                problems.append("base_not_ancestor_of_head")
            merge_base = common.git(repo, "merge-base", head, source_ref).stdout.strip()
            document["merge_base_with_source"] = merge_base
            if merge_base != base:
                problems.append(f"merge_base_with_source_is_{merge_base[:12]}_not_base")
            if args.source == "main" and g4r_ref is not None:
                g4r_mb = common.git(repo, "merge-base", head, g4r_ref).stdout.strip()
                document["merge_base_with_g4r"] = g4r_mb
                if g4r_mb != base:
                    problems.append("main_sourced_branch_contains_g4r_lineage")
        if args.expect_branch and not re.fullmatch(args.expect_branch, branch):
            problems.append(f"branch_name_does_not_match:{args.expect_branch}")
        if main_ref is not None and g4r_ref is not None:
            g4r_vs_main = common.git(repo, "merge-base", "--is-ancestor", g4r_ref, main_ref, check=False)
            document["g4r_is_ancestor_of_main"] = g4r_vs_main.returncode == 0
        commits_ahead = common.git(repo, "rev-list", "--count", f"{base}..{head}", check=False)
        document["commits_ahead_of_base"] = (
            int(commits_ahead.stdout.strip()) if commits_ahead.returncode == 0 else None
        )
        document["problems"] = problems
        document["ok"] = not problems
        return (EXIT_BRANCH if problems else EXIT_OK), document
    except common.GuardError as exc:
        document.update({"ok": False, "problems": [str(exc)]})
        return EXIT_BRANCH, document


# ---------------------------------------------------------------------------
# protected
# ---------------------------------------------------------------------------
def check_protected(args: argparse.Namespace) -> tuple[int, dict]:
    repo = Path(args.repo).resolve()
    document: dict = {"command": "protected", "utc": utc_now(), "repo": str(repo)}
    try:
        base = common.git(repo, "rev-parse", "--verify", f"{args.base}^{{commit}}").stdout.strip()
        head = common.git(repo, "rev-parse", args.head).stdout.strip()
        status = common.git(repo, "diff", "--name-status", base, head).stdout.splitlines()
        allow = {item.strip() for item in args.allow if item.strip()}
        changed, violations = [], []
        for line in status:
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            path = parts[-1]
            if not is_protected(path):
                continue
            entry = {"status": parts[0], "path": path}
            changed.append(entry)
            if path not in allow:
                violations.append(entry)
        document.update(
            {
                "base": base,
                "head": head,
                "protected_patterns": list(PROTECTED_PREFIXES),
                "changed_protected": changed,
                "allow_list": sorted(allow),
                "violations": violations,
                "ok": not violations or args.warn_only,
                "warn_only": args.warn_only,
            }
        )
        code = EXIT_OK if document["ok"] else EXIT_PROTECTED
        return code, document
    except common.GuardError as exc:
        document.update({"ok": False, "problems": [str(exc)]})
        return EXIT_PROTECTED, document


# ---------------------------------------------------------------------------
# merges
# ---------------------------------------------------------------------------
def check_merges(args: argparse.Namespace) -> tuple[int, dict]:
    repo = Path(args.repo).resolve()
    document: dict = {"command": "merges", "utc": utc_now(), "repo": str(repo)}
    try:
        base = common.git(repo, "rev-parse", "--verify", f"{args.base}^{{commit}}").stdout.strip()
        head = common.git(repo, "rev-parse", args.head).stdout.strip()
        commits = common.git_lines(repo, "rev-list", "--merges", f"{base}..{head}")
        allow = {item.strip() for item in args.allow_merge if item.strip()}
        subject_re = re.compile(args.allow_subject_regex) if args.allow_subject_regex else None
        entries, violations = [], []
        for sha in commits:
            subject = common.git(repo, "show", "-s", "--format=%s", sha).stdout.strip()
            authorized = sha in allow or bool(subject_re and subject_re.search(subject))
            entry = {"sha": sha, "subject": subject, "authorized": authorized}
            entries.append(entry)
            if not authorized:
                violations.append(entry)
        document.update(
            {
                "base": base,
                "head": head,
                "merge_commits": entries,
                "violations": violations,
                "allow_merge": sorted(allow),
                "ok": not violations,
            }
        )
        return (EXIT_OK if not violations else EXIT_UNAUTHORIZED_MERGE), document
    except common.GuardError as exc:
        document.update({"ok": False, "problems": [str(exc)]})
        return EXIT_UNAUTHORIZED_MERGE, document


# ---------------------------------------------------------------------------
# cherry-pick / H0
# ---------------------------------------------------------------------------
def patch_id(repo: Path, sha: str) -> str | None:
    shown = common.git(repo, "show", "--patch", "--format=", sha, check=False)
    if shown.returncode != 0:
        return None
    proc = common.subprocess.run(
        ["git", "-C", str(repo), "patch-id", "--stable"],
        input=shown.stdout.encode("utf-8"),
        stdout=common.subprocess.PIPE,
        stderr=common.subprocess.PIPE,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.decode("utf-8", "replace").split()[0]


def commit_subjects(repo: Path, start: str, head: str) -> list[tuple[str, str]]:
    lines = common.git_lines(repo, "log", "--no-merges", "--format=%H\t%s", f"{start}..{head}")
    result = []
    for line in lines:
        sha, _, subject = line.partition("\t")
        result.append((sha, subject))
    return result


def check_cherry_pick(args: argparse.Namespace) -> tuple[int, dict]:
    repo = Path(args.repo).resolve()
    document: dict = {"command": "cherry-pick", "utc": utc_now(), "repo": str(repo)}
    try:
        base = common.git(repo, "rev-parse", "--verify", f"{args.base}^{{commit}}").stdout.strip()
        head = common.git(repo, "rev-parse", args.head).stdout.strip()
        h0_ref = resolve_ref(repo, args.h0_ref)
        document.update({"base": base, "head": head, "h0_ref": args.h0_ref, "h0_sha": h0_ref})
        problems: list[str] = []
        hints: list[str] = []
        if h0_ref is None:
            document["status"] = "H0_REF_ABSENT"
            document["ok"] = True
            document["problems"] = []
            document["hints"] = []
            return EXIT_OK, document
        merged = common.git(repo, "merge-base", "--is-ancestor", h0_ref, head, check=False)
        document["h0_is_ancestor_of_head"] = merged.returncode == 0
        if merged.returncode == 0:
            problems.append("h0_lineage_merged_into_head")
        head_commits = commit_subjects(repo, base, head)
        h0_commits = common.git_lines(
            repo, "log", "--no-merges", "--format=%H", f"-n{args.max_h0_commits}", h0_ref
        )
        h0_patch_ids: dict[str, str] = {}
        truncated = False
        for index, sha in enumerate(h0_commits):
            if index >= args.max_h0_commits:
                truncated = True
                break
            pid = patch_id(repo, sha)
            if pid:
                h0_patch_ids[pid] = sha
        document["h0_commits_scanned"] = len(h0_patch_ids)
        document["h0_scan_truncated"] = truncated
        matched: list[dict] = []
        for sha, subject in head_commits:
            if H0_HINT_PATTERN.search(subject) or is_protected_subject(repo, base, head, sha):
                hints.append(f"subject_hint:{sha[:12]}:{subject}")
            if not h0_patch_ids:
                continue
            pid = patch_id(repo, sha)
            if pid and pid in h0_patch_ids:
                matched.append(
                    {"head_commit": sha, "subject": subject, "h0_commit": h0_patch_ids[pid]}
                )
        if matched:
            problems.append("h0_patch_id_match")
        document.update(
            {
                "patch_id_matches": matched,
                "hints": hints[:50],
                "problems": problems,
                "ok": not problems and not (args.strict_hints and hints),
            }
        )
        if args.strict_hints and hints and not problems:
            problems.append("subject_hints_under_strict_mode")
            document["problems"] = problems
            document["ok"] = False
        code = EXIT_OK if document["ok"] else EXIT_CHERRY_PICK
        return code, document
    except common.GuardError as exc:
        document.update({"ok": False, "problems": [str(exc)]})
        return EXIT_CHERRY_PICK, document


def is_protected_subject(repo: Path, base: str, head: str, sha: str) -> bool:
    files = common.git_lines(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
    return any(is_protected(path) for path in files)


# ---------------------------------------------------------------------------
# all
# ---------------------------------------------------------------------------
def run_all(args: argparse.Namespace) -> tuple[int, dict]:
    steps = [
        ("branch", check_branch),
        ("protected", check_protected),
        ("merges", check_merges),
        ("cherry-pick", check_cherry_pick),
    ]
    results: dict = {"command": "all", "utc": utc_now(), "repo": str(Path(args.repo).resolve())}
    codes: dict[str, int] = {}
    for name, checker in steps:
        code, document = checker(args)
        codes[name] = code
        results[name] = {"exit_code": code, "ok": document.get("ok"), "detail": document}
    results["exit_codes"] = codes
    results["ok"] = all(code == EXIT_OK for code in codes.values())
    return (EXIT_OK if results["ok"] else next(code for code in codes.values() if code != EXIT_OK)), results


# ---------------------------------------------------------------------------
# parser / main
# ---------------------------------------------------------------------------
def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--json-out", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A-NEXT CI static validation guard")
    sub = parser.add_subparsers(dest="command", required=True)

    branch = sub.add_parser("branch", help="branch provenance check")
    add_common(branch)
    branch.add_argument("--source", choices=("main", "work/g4r"), required=True)
    branch.add_argument("--expect-branch", default=None, help="regex for allowed branch name")

    protected = sub.add_parser("protected", help="protected file change check")
    add_common(protected)
    protected.add_argument("--allow", action="append", default=[])
    protected.add_argument("--warn-only", action="store_true")

    merges = sub.add_parser("merges", help="unauthorized merge commit check")
    add_common(merges)
    merges.add_argument("--allow-merge", action="append", default=[], help="allowed merge SHA")
    merges.add_argument("--allow-subject-regex", default=None)

    cherry = sub.add_parser("cherry-pick", help="H0 lineage/cherry-pick risk check")
    add_common(cherry)
    cherry.add_argument("--h0-ref", default=DEFAULT_H0_REF)
    cherry.add_argument("--max-h0-commits", type=int, default=120)
    cherry.add_argument("--strict-hints", action="store_true")

    everything = sub.add_parser("all", help="run all checks")
    add_common(everything)
    everything.add_argument("--source", choices=("main", "work/g4r"), required=True)
    everything.add_argument("--expect-branch", default=None)
    everything.add_argument("--allow", action="append", default=[])
    everything.add_argument("--warn-only", action="store_true")
    everything.add_argument("--allow-merge", action="append", default=[])
    everything.add_argument("--allow-subject-regex", default=None)
    everything.add_argument("--h0-ref", default=DEFAULT_H0_REF)
    everything.add_argument("--max-h0-commits", type=int, default=120)
    everything.add_argument("--strict-hints", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "branch": check_branch,
        "protected": check_protected,
        "merges": check_merges,
        "cherry-pick": check_cherry_pick,
        "all": run_all,
    }
    code, document = handlers[args.command](args)
    emit(document, args.json_out)
    return code


if __name__ == "__main__":
    sys.exit(main())
