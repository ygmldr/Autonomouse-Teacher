"""M1 Offline Teacher -- self-contained, offline, mock-only teaching package.

Import surfaces owned by this package (``m1_offline``):

* :data:`REPO_ROOT` -- absolute path of the worktree root (``parents[1]``).
* :data:`FIXTURES_DIR` -- ``REPO_ROOT / "fixtures" / "m1"`` (synthetic/CC0
  fixtures only; may be created by the fixtures owner, not by this module).
* :func:`load_json` -- read a JSON object from an absolute path or one relative
  to :data:`REPO_ROOT`; fail closed when the root is not a JSON object.
* :func:`now_utc` -- UTC ISO-8601 clock shared with :mod:`m1_offline.types`.
* :data:`SCHEMA_VERSION` -- shared schema version (``m1.offline.v0``).

This package is intentionally isolated from M0: it never imports
``autoteacher_m0`` (or any other ``src`` package), never touches the network,
and never calls a real provider.  M0 runtime capabilities are UNVERIFIED from
here; :mod:`m1_offline.runtime_port` defines a mock-only abstract port.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

from .types import SCHEMA_VERSION, now_utc

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
FIXTURES_DIR: Path = REPO_ROOT / "fixtures" / "m1"

__all__ = [
    "REPO_ROOT",
    "FIXTURES_DIR",
    "SCHEMA_VERSION",
    "load_json",
    "now_utc",
]

PathLike = Union[str, Path]


def load_json(path: PathLike) -> dict[str, Any]:
    """Load a JSON object from ``path`` (relative paths resolve from REPO_ROOT).

    Raises:
        FileNotFoundError: when the file does not exist.
        ValueError: when the file content is not a JSON object.
    """

    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = REPO_ROOT / resolved
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{resolved}: expected a JSON object at the top level")
    return data
