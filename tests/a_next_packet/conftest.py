"""Fixtures for A-NEXT packet v3 tests (synthetic trees only)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from a_next_packet_helpers import IMPL, canonical_sha, make_tree, output_json, run_script

@pytest.fixture()
def staging(tmp_path: Path) -> Path:
    return make_tree(
        tmp_path / "staging",
        {
            "README.txt": "packet payload\n",
            "cases/r1/index.json": '{"case":"r1"}\n',
            "review/summary.md": "summary\n",
        },
    )


@pytest.fixture()
def frozen_rootfs(tmp_path: Path) -> Path:
    return make_tree(tmp_path / "frozen-rootfs", {"etc/os-release": "ID=test\n"})


@pytest.fixture()
def built_packet(tmp_path: Path, staging: Path, frozen_rootfs: Path) -> dict:
    """Build a final-phase synthetic packet and return paths/identity."""
    expected = canonical_sha(frozen_rootfs)
    impl = IMPL
    out = tmp_path / "artifacts" / f"review-packet-a-next-v3-{impl}"
    proc = run_script(
        "build_packet_v3.py",
        "--staging-dir",
        staging,
        "--impl-sha",
        impl,
        "--no-git-check",
        "--out-dir",
        out,
        "--frozen-rootfs",
        frozen_rootfs,
        "--expected-rootfs-sha",
        expected,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = output_json(proc)
    return {
        "packet": out,
        "staging": staging,
        "frozen": frozen_rootfs,
        "frozen_sha": expected,
        "impl": impl,
        "summary": summary,
        "manifest": __import__("json").loads((out / "manifest.json").read_text()),
    }


@pytest.fixture(autouse=True)
def _no_real_env_leak() -> None:
    for name in list(os.environ):
        if any(part in name.upper() for part in ("API_KEY", "TOKEN", "SECRET")):
            os.environ.pop(name, None)
    yield
