"""M1 Offline Teacher evaluation package.

Modules (all offline, synthetic-only):

* :mod:`m1_offline.evaluation.harness` -- deterministic replayable closed loop.
* :mod:`m1_offline.evaluation.compare` -- blind-rubric teacher_v0 vs teacher_v1.
* :mod:`m1_offline.evaluation.contamination` -- public/hidden leakage scanning.
* :mod:`m1_offline.evaluation.report` -- markdown/JSON reports with NOT_RUN handling.

Boundary: everything here is an **offline synthetic simulation**, not real
teaching effect; M0 runtime capabilities remain UNVERIFIED.
"""

from __future__ import annotations

from . import compare, contamination, harness, report

__all__ = ["harness", "compare", "contamination", "report"]
