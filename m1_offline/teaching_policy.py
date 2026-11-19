"""Teaching policy and hint ladder (M1 Teacher Core).

Two concrete, deterministic policies share the :class:`TeachingPolicy`
interface:

* :class:`FixedPolicy` (``teacher_v0``) -- non-adaptive: it emits the hint
  ladder rung requested by the caller, capped by a safety gate that only lets
  intervention intensity grow with *actual evidence*.
* :class:`AdaptivePolicy` (``teacher_v1``) -- evidence/diagnosis adaptive: it
  reacts to a :class:`~m1_offline.types.DiagnosticResult` and to repeated
  errors, emits socratic/explanatory/review actions where appropriate, and may
  escalate one rung above the requested level once there is evidence.

Hint ladder safety (mandatory contract):

* Default intervention is the lowest rung: ``LIGHT_HINT``.
* The ladder order is ``LIGHT_HINT -> INVARIANT_HINT -> STRUCTURE_HINT ->
  FULL_SOLUTION``; ``FULL_SOLUTION`` is last resort and can never be emitted
  without evidence (``hint_level=4`` **and** a satisfied evidence gate).
* A brand-new learner (``evidence_count == 0``) is always capped at
  ``LIGHT_HINT`` regardless of the requested level.
* Every emitted :class:`~m1_offline.types.TeacherAction` carries a human
  readable ``rationale`` that names the requested rung, the safety cap and the
  evidence basis, so policy decisions are auditable in traces.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar

from .types import (
    HINT_LADDER,
    HINT_LEVEL_MAX,
    HINT_LEVEL_MIN,
    DiagnosticResult,
    LearnerState,
    TeacherAction,
)

__all__ = [
    "TeachingPolicy",
    "FixedPolicy",
    "AdaptivePolicy",
    "EvidenceGate",
    "hint_kind_for_level",
]

#: Hint rungs keyed by 1-based level.
hint_kind_for_level = {level: HINT_LADDER[level - 1] for level in range(HINT_LEVEL_MIN, HINT_LEVEL_MAX + 1)}


class EvidenceGate:
    """Maps learner evidence onto the maximum intervention level allowed.

    The gate is a conservative, monotone function of the number of observed
    evidence events.  It deliberately does **not** require success/mastery:
    a learner who has repeatedly failed has plenty of evidence that they are
    stuck, so a strong intervention may be appropriate -- but only when the
    caller explicitly requests it (see :class:`AdaptivePolicy`).  Thin evidence
    never unlocks stronger intervention, and no evidence is always floored at
    :class:`~m1_offline.types.HINT_LADDER` rung 1 (``LIGHT_HINT``).

    =========================  ==========================================
    evidence basis             max hint level
    =========================  ==========================================
    no evidence at all         1 (``LIGHT_HINT``)
    1 event                    2 (``INVARIANT_HINT``)
    2-4 events                 3 (``STRUCTURE_HINT``)
    >= 5 events                4 (``FULL_SOLUTION``, explicit request only)
    =========================  ==========================================
    """

    LIGHT_MAX_EVIDENCE = 0
    STRUCTURE_MIN_EVIDENCE = 2
    FULL_MIN_EVIDENCE = 5

    @classmethod
    def max_level(cls, state: LearnerState, skill_ids: list[str] | None = None) -> int:
        if not isinstance(state, LearnerState):
            raise TypeError(f"learner_state must be LearnerState, got {type(state).__name__}")
        if state.evidence_count <= cls.LIGHT_MAX_EVIDENCE:
            return 1
        if state.evidence_count < cls.STRUCTURE_MIN_EVIDENCE:
            return 2
        if state.evidence_count < cls.FULL_MIN_EVIDENCE:
            return 3
        return 4

    @classmethod
    def describe(cls, state: LearnerState, skill_ids: list[str] | None = None) -> str:
        best = (
            max((state.mastery.get(skill, 0.0) for skill in skill_ids), default=0.0)
            if skill_ids
            else max(state.mastery.values(), default=0.0)
        )
        return (
            f"evidence_count={state.evidence_count}, best_mastery={best:.2f}, "
            f"safety_cap=L{cls.max_level(state, skill_ids)}"
        )


def _task_id(task: dict) -> str:
    if not isinstance(task, dict):
        raise TypeError(f"task must be dict, got {type(task).__name__}")
    task_id = task.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task['task_id'] must be a non-empty str")
    return task_id


def _task_skill_ids(task: dict) -> list[str]:
    skills = task.get("skill_ids", [])
    if isinstance(skills, str):
        skills = [skills]
    if not isinstance(skills, list) or not all(
        isinstance(skill, str) and skill.strip() for skill in skills
    ):
        raise ValueError("task['skill_ids'] must be a list[str]")
    return list(skills)


def _coerce_hint_level(hint_level: int) -> int:
    if isinstance(hint_level, bool) or not isinstance(hint_level, int):
        raise ValueError(f"hint_level must be int, got {type(hint_level).__name__}")
    if not HINT_LEVEL_MIN <= hint_level <= HINT_LEVEL_MAX:
        raise ValueError(
            f"hint_level must be within [{HINT_LEVEL_MIN}, {HINT_LEVEL_MAX}], got {hint_level}"
        )
    return hint_level


def _action_id(policy_version: str, task_id: str, kind: str, hint_level: int | None, basis: str) -> str:
    digest = hashlib.sha256(
        "\x1f".join([policy_version, task_id, kind, str(hint_level), basis]).encode("utf-8")
    ).hexdigest()
    return f"act_{digest[:16]}"


def _render_hint_content(task: dict, kind: str, skills: list[str]) -> str:
    skill_text = ", ".join(skills) if skills else "the current problem"
    prefix = {
        "LIGHT_HINT": "narrowing question",
        "INVARIANT_HINT": "invariant reminder",
        "STRUCTURE_HINT": "structure/outline hint",
        "FULL_SOLUTION": "worked solution (last resort)",
    }[kind]
    return (
        f"[{prefix}] task={task.get('task_id')} skills=[{skill_text}]: "
        f"consider the input boundary and the stated invariant before writing code."
    )


class TeachingPolicy:
    """Abstract policy interface: choose one teaching action per call."""

    policy_version: ClassVar[str] = "teacher_base"

    def choose(
        self,
        task: dict,
        learner_state: LearnerState,
        diagnosis: DiagnosticResult | None,
        hint_level: int,
    ) -> TeacherAction:
        raise NotImplementedError

    # -- shared helpers ----------------------------------------------------
    def _validated(
        self,
        task: dict,
        learner_state: LearnerState,
        diagnosis: DiagnosticResult | None,
        hint_level: int,
    ) -> tuple[str, list[str], int]:
        task_id = _task_id(task)
        skills = _task_skill_ids(task)
        if not isinstance(learner_state, LearnerState):
            raise TypeError(
                f"learner_state must be LearnerState, got {type(learner_state).__name__}"
            )
        if diagnosis is not None and not isinstance(diagnosis, DiagnosticResult):
            raise TypeError(f"diagnosis must be DiagnosticResult | None, got {type(diagnosis).__name__}")
        level = _coerce_hint_level(hint_level)
        return task_id, skills, level

    def _build(
        self,
        *,
        kind: str,
        content: str,
        rationale: str,
        hint_level: int | None,
        source_action: str,
        target_skill_ids: list[str],
        evidence_refs: list[str] | None = None,
        task_id: str = "",
    ) -> TeacherAction:
        return TeacherAction(
            action_id=_action_id(
                self.policy_version, task_id, kind, hint_level, source_action
            ),
            kind=kind,
            content=content,
            rationale=rationale,
            hint_level=hint_level,
            target_skill_ids=list(dict.fromkeys(target_skill_ids)),
            evidence_refs=list(evidence_refs or []),
        )


class FixedPolicy(TeachingPolicy):
    """``teacher_v0``: fixed, non-adaptive hint-ladder policy.

    Always emits a hint rung (never socratic/explanatory/review actions) and
    never adapts to diagnoses.  The requested level is still capped by the
    evidence gate, so the fixed policy is safe but unresponsive.
    """

    policy_version: ClassVar[str] = "teacher_v0"

    def choose(
        self,
        task: dict,
        learner_state: LearnerState,
        diagnosis: DiagnosticResult | None,
        hint_level: int,
    ) -> TeacherAction:
        task_id, skills, requested = self._validated(task, learner_state, diagnosis, hint_level)
        cap = EvidenceGate.max_level(learner_state, skills)
        effective = min(requested, cap)
        kind = hint_kind_for_level[effective]
        rationale = (
            f"{self.policy_version} fixed hint ladder: requested L{requested}, "
            f"{EvidenceGate.describe(learner_state, skills)} -> emitted L{effective} {kind}; "
            f"non-adaptive (diagnosis ignored)."
        )
        return self._build(
            kind=kind,
            content=_render_hint_content(task, kind, skills),
            rationale=rationale,
            hint_level=effective,
            source_action=f"requested={requested};cap={cap}",
            target_skill_ids=skills,
            task_id=task_id,
        )


class AdaptivePolicy(TeachingPolicy):
    """``teacher_v1``: diagnosis/evidence adaptive policy.

    Priority order (deterministic, documented so traces are explainable):

    1. ``task_type == REVIEW`` -> ``REVIEW`` action (spaced revisiting).
    2. diagnosis ``NEEDS_REVIEW`` -> ``ASK_CLARIFICATION`` (never guess).
    3. diagnosis error codes containing ``conceptual_gap`` -> ``EXPLAIN``.
    4. any other diagnosis error codes -> ``SOCRATIC_QUESTION``.
    5. brand-new learner (no evidence) -> ``LIGHT_HINT`` (hard safety floor).
    6. repeated errors on the task skills (>= 2 recorded) -> hint one rung above
       the requested level; sustained error history (>= 4 recorded) -> two rungs
       above (both still capped by :class:`EvidenceGate`).
    7. otherwise -> hint rung ``min(requested, cap)``.
    """

    policy_version: ClassVar[str] = "teacher_v1"
    REPEAT_ERROR_THRESHOLD = 2
    SUSTAINED_ERROR_THRESHOLD = 4

    def choose(
        self,
        task: dict,
        learner_state: LearnerState,
        diagnosis: DiagnosticResult | None,
        hint_level: int,
    ) -> TeacherAction:
        task_id, skills, requested = self._validated(task, learner_state, diagnosis, hint_level)
        cap = EvidenceGate.max_level(learner_state, skills)
        task_type = task.get("task_type", "")
        evidence_refs = list(diagnosis.evidence_refs) if diagnosis is not None else []

        if task_type == "REVIEW":
            rationale = (
                f"{self.policy_version}: task_type=REVIEW -> spaced REVIEW action; "
                f"requested L{requested}, {EvidenceGate.describe(learner_state, skills)}."
            )
            return self._build(
                kind="REVIEW",
                content=(
                    f"[review] task={task_id} skills=[{', '.join(skills) or 'n/a'}]: "
                    "re-attempt the previously solved variant and articulate the invariant."
                ),
                rationale=rationale,
                hint_level=None,
                source_action="review",
                target_skill_ids=skills,
                evidence_refs=evidence_refs,
                task_id=task_id,
            )

        if diagnosis is not None and diagnosis.status == "NEEDS_REVIEW":
            rationale = (
                f"{self.policy_version}: diagnosis {diagnosis.diagnosis_id} status=NEEDS_REVIEW "
                f"-> ASK_CLARIFICATION instead of guessing; "
                f"{EvidenceGate.describe(learner_state, skills)}."
            )
            return self._build(
                kind="ASK_CLARIFICATION",
                content=(
                    f"[clarify] task={task_id}: I could not confidently classify the failure "
                    f"({'/'.join(diagnosis.error_codes) or 'no error code'}); "
                    "please restate the expected behaviour and one failing input."
                ),
                rationale=rationale,
                hint_level=None,
                source_action=f"diagnosis={diagnosis.diagnosis_id};status={diagnosis.status}",
                target_skill_ids=skills,
                evidence_refs=evidence_refs,
                task_id=task_id,
            )

        if diagnosis is not None and diagnosis.error_codes:
            if "conceptual_gap" in diagnosis.error_codes:
                kind = "EXPLAIN"
                content = (
                    f"[explain] task={task_id} skills=[{', '.join(skills) or 'n/a'}]: "
                    "restate the core concept and why the failing approach cannot satisfy it."
                )
            else:
                kind = "SOCRATIC_QUESTION"
                content = (
                    f"[socratic] task={task_id}: you hit "
                    f"[{', '.join(diagnosis.error_codes)}]; what must be true right before "
                    "the failing step, and can you construct the smallest counterexample?"
                )
            rationale = (
                f"{self.policy_version}: diagnosis {diagnosis.diagnosis_id} error_codes="
                f"{diagnosis.error_codes} -> {kind}; requested L{requested}, "
                f"{EvidenceGate.describe(learner_state, skills)}."
            )
            return self._build(
                kind=kind,
                content=content,
                rationale=rationale,
                hint_level=None,
                source_action=f"diagnosis={diagnosis.diagnosis_id};codes={'-'.join(diagnosis.error_codes)}",
                target_skill_ids=skills,
                evidence_refs=evidence_refs,
                task_id=task_id,
            )

        if learner_state.evidence_count == 0:
            kind = "LIGHT_HINT"
            rationale = (
                f"{self.policy_version}: no evidence yet -> safety floor LIGHT_HINT "
                f"(requested L{requested} suppressed); {EvidenceGate.describe(learner_state, skills)}; "
                "FULL_SOLUTION never by default."
            )
            return self._build(
                kind=kind,
                content=_render_hint_content(task, kind, skills),
                rationale=rationale,
                hint_level=1,
                source_action="no-evidence-floor",
                target_skill_ids=skills,
                task_id=task_id,
            )

        # Error history may be keyed by skill (fixture convention) or by error
        # code (LearnerModel convention); use the stronger signal so the policy
        # works with either producer without silently ignoring errors.
        skill_errors = sum(learner_state.error_counts.get(skill, 0) for skill in skills)
        total_errors = sum(learner_state.error_counts.values())
        repeated_errors = max(skill_errors, total_errors)
        # FULL_SOLUTION is a last resort and is only ever emitted on an explicit
        # L4 request; adaptive escalation itself never crosses into FULL.
        escalation_cap = cap if requested == HINT_LEVEL_MAX else min(cap, HINT_LEVEL_MAX - 1)
        if repeated_errors >= self.SUSTAINED_ERROR_THRESHOLD:
            # Sustained error history (>= 4 observations) warrants two rungs of
            # extra support, still bounded by the evidence gate.
            effective = min(requested + 2, escalation_cap)
            basis = f"repeat-errors={repeated_errors};sustained"
        elif repeated_errors >= self.REPEAT_ERROR_THRESHOLD:
            effective = min(requested + 1, escalation_cap)
            basis = f"repeat-errors={repeated_errors}"
        else:
            effective = min(requested, escalation_cap)
            basis = "no-repeat-errors"
        kind = hint_kind_for_level[effective]
        rationale = (
            f"{self.policy_version}: evidence-adaptive; requested L{requested}, "
            f"{EvidenceGate.describe(learner_state, skills)}, {basis} -> emitted L{effective} {kind}; "
            "FULL_SOLUTION requires an explicit L4 request and satisfied evidence gate "
            "(never by default)."
        )
        return self._build(
            kind=kind,
            content=_render_hint_content(task, kind, skills),
            rationale=rationale,
            hint_level=effective,
            source_action=f"requested={requested};cap={cap};{basis}",
            target_skill_ids=skills,
            task_id=task_id,
        )
