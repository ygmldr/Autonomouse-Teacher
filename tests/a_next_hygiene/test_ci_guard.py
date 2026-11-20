"""Tests for scripts/a_next/ci_guard.py using throw-away git repositories."""

from __future__ import annotations

from pathlib import Path

from conftest import commit, git, make_tree, output_json, run_script


def _write_and_commit(repo: Path, relative: str, content: str, message: str) -> str:
    make_tree(repo, {relative: content})
    return commit(repo, message)


def test_branch_from_main_passes(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "chore/x")
    _write_and_commit(repo, "docs/x.md", "x\n", "docs: x")
    proc = run_script(
        "ci_guard.py", "branch", "--repo", repo, "--source", "main", "--base", base
    )
    assert proc.returncode == 0, proc.stderr
    document = output_json(proc)
    assert document["ok"] is True
    assert document["commits_ahead_of_base"] == 1


def test_branch_wrong_base_fails(git_repo):
    repo = git_repo["repo"]
    git(repo, "checkout", "-q", "-b", "chore/y")
    feature = _write_and_commit(repo, "docs/y.md", "y\n", "docs: y")
    proc = run_script(
        "ci_guard.py", "branch", "--repo", repo, "--source", "main", "--base", feature
    )
    assert proc.returncode == 31
    problems = output_json(proc)["problems"]
    assert "merge_base_with_source_is_" in " ".join(problems) or "base_not_ancestor" in " ".join(problems)


def test_branch_missing_source_ref_fails(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    proc = run_script(
        "ci_guard.py", "branch", "--repo", repo, "--source", "work/g4r", "--base", base
    )
    assert proc.returncode == 31
    assert any("source_ref_missing" in item for item in output_json(proc)["problems"])


def test_branch_main_sourced_with_g4r_lineage_fails(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "work/g4r")
    g4r_head = _write_and_commit(repo, "docs/g4r.md", "g4r\n", "docs: g4r")
    git(repo, "checkout", "-q", "-b", "chore/leak", g4r_head)
    _write_and_commit(repo, "docs/leak.md", "leak\n", "docs: leak")
    proc = run_script(
        "ci_guard.py", "branch", "--repo", repo, "--source", "main", "--base", base
    )
    assert proc.returncode == 31
    assert "main_sourced_branch_contains_g4r_lineage" in output_json(proc)["problems"]


def test_protected_change_flagged(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "chore/prot")
    _write_and_commit(
        repo, "src/autoteacher_m0/security/gates.py", "# changed\n", "fix: gates"
    )
    proc = run_script("ci_guard.py", "protected", "--repo", repo, "--base", base)
    assert proc.returncode == 33
    document = output_json(proc)
    assert [entry["path"] for entry in document["violations"]] == [
        "src/autoteacher_m0/security/gates.py"
    ]


def test_protected_change_allowed_when_explicit(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "chore/prot2")
    _write_and_commit(
        repo, "src/autoteacher_m0/security/gates.py", "# changed\n", "fix: gates"
    )
    proc = run_script(
        "ci_guard.py",
        "protected",
        "--repo",
        repo,
        "--base",
        base,
        "--allow",
        "src/autoteacher_m0/security/gates.py",
    )
    assert proc.returncode == 0, proc.stderr
    assert output_json(proc)["ok"] is True


def test_non_protected_change_not_flagged(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "chore/docs")
    _write_and_commit(repo, "docs/notes.md", "notes\n", "docs: notes")
    proc = run_script("ci_guard.py", "protected", "--repo", repo, "--base", base)
    assert proc.returncode == 0
    assert output_json(proc)["changed_protected"] == []


def test_unauthorized_merge_detected(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "side")
    _write_and_commit(repo, "docs/side.md", "side\n", "docs: side")
    git(repo, "checkout", "-q", "-b", "chore/merge", base)
    _write_and_commit(repo, "docs/main-line.md", "main\n", "docs: main")
    git(repo, "merge", "--no-ff", "-q", "-m", "merge(side): unauthorized", "side")
    proc = run_script("ci_guard.py", "merges", "--repo", repo, "--base", base)
    assert proc.returncode == 32
    document = output_json(proc)
    assert len(document["violations"]) == 1


def test_allowed_merge_passes(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "side2")
    _write_and_commit(repo, "docs/side2.md", "side2\n", "docs: side2")
    git(repo, "checkout", "-q", "-b", "chore/merge2", base)
    _write_and_commit(repo, "docs/main2.md", "main2\n", "docs: main2")
    git(repo, "merge", "--no-ff", "-q", "-m", "merge(side2): allowed", "side2")
    merge_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    proc = run_script(
        "ci_guard.py",
        "merges",
        "--repo",
        repo,
        "--base",
        base,
        "--allow-merge",
        merge_sha,
    )
    assert proc.returncode == 0, proc.stderr


def test_cherry_pick_from_h0_detected(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "work/m0-g4h0")
    h0_commit = _write_and_commit(
        repo, "docs/h0-change.md", "h0 prepared change\n", "docs(g4h0): prepared"
    )
    git(repo, "checkout", "-q", "-b", "chore/cherry", base)
    git(repo, "cherry-pick", h0_commit)
    proc = run_script(
        "ci_guard.py",
        "cherry-pick",
        "--repo",
        repo,
        "--base",
        base,
        "--h0-ref",
        "work/m0-g4h0",
    )
    assert proc.returncode == 34, proc.stderr
    document = output_json(proc)
    assert "h0_patch_id_match" in document["problems"]


def test_h0_merged_lineage_detected(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "work/m0-g4h0")
    _write_and_commit(repo, "docs/h0b.md", "h0b\n", "docs(g4h0): b")
    git(repo, "checkout", "-q", "-b", "chore/merged", base)
    _write_and_commit(repo, "docs/m.md", "m\n", "docs: m")
    git(repo, "merge", "--no-ff", "-q", "-m", "merge h0", "work/m0-g4h0")
    proc = run_script(
        "ci_guard.py",
        "cherry-pick",
        "--repo",
        repo,
        "--base",
        base,
        "--h0-ref",
        "work/m0-g4h0",
    )
    assert proc.returncode == 34
    assert "h0_lineage_merged_into_head" in output_json(proc)["problems"]


def test_missing_h0_ref_is_not_a_failure(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "chore/noh0")
    _write_and_commit(repo, "docs/noh0.md", "n\n", "docs: n")
    proc = run_script(
        "ci_guard.py",
        "cherry-pick",
        "--repo",
        repo,
        "--base",
        base,
        "--h0-ref",
        "work/m0-g4h0",
    )
    assert proc.returncode == 0, proc.stderr
    assert output_json(proc)["status"] == "H0_REF_ABSENT"


def test_all_clean_branch_passes(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "chore/all")
    _write_and_commit(repo, "docs/all.md", "all\n", "docs: all")
    proc = run_script(
        "ci_guard.py",
        "all",
        "--repo",
        repo,
        "--source",
        "main",
        "--base",
        base,
    )
    assert proc.returncode == 0, proc.stderr
    document = output_json(proc)
    assert document["ok"] is True
    assert document["exit_codes"] == {
        "branch": 0,
        "protected": 0,
        "merges": 0,
        "cherry-pick": 0,
    }


def test_all_protected_violation_returns_33(git_repo):
    repo, base = git_repo["repo"], git_repo["base"]
    git(repo, "checkout", "-q", "-b", "chore/allprot")
    _write_and_commit(
        repo, "src/autoteacher_m0/bridge/controller.py", "# changed\n", "fix: controller"
    )
    proc = run_script(
        "ci_guard.py", "all", "--repo", repo, "--source", "main", "--base", base
    )
    assert proc.returncode == 33
    assert output_json(proc)["exit_codes"]["protected"] == 33
