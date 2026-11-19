"""Explainable, deterministic curriculum planner (M1 Teacher Core).

The planner produces a :class:`~m1_offline.types.CurriculumPlan` from a
learning goal, the learner's evidence state and a catalog of available tasks.
It is intentionally rule-based and auditable:

* **Review/new balance.**  Tasks whose skills are already mastered
  (``mastery >= REVIEW_MASTERY_THRESHOLD``) are scheduled as *review* to fight
  forgetting; tasks on goal target skills below mastery are scheduled as *new*.
  Review occupies at most one third of the plan slots (minimum one review task
  when review material exists and there is room), the rest is new/consolidation.
* **Explainable rationale.**  Every plan carries human-readable ``rationale``
  lines naming the policy version, the goal inputs, why each task was selected
  (mastery numbers included), the balance arithmetic, and anything excluded by
  the weekly-minutes budget.
* **Rollback.**  ``policy_version`` is part of the plan (and of the
  deterministic ``plan_id``), so a plan can be attributed to a policy and a
  policy rollback is a version bump plus re-planning the same inputs.
* **Deterministic.**  Tasks are ordered by ``(ordinal, task_id)``; the same
  goal/state/catalog yields the same task sequence and ``plan_id``.  Only
  ``created_at`` reflects wall-clock time.

The planner is offline and mock-only: the task catalog comes from synthetic
fixtures supplied by the caller; no provider is called and no M0 runtime
capability is assumed.
"""

from __future__ import annotations

import hashlib

from .types import CurriculumPlan, LearnerState, LearningGoal, LearningTask

__all__ = ["CurriculumPlanner"]

#: Bucket labels used in plan rationale.
BUCKET_REVIEW = "REVIEW"
BUCKET_NEW = "NEW"
BUCKET_STRETCH = "STRETCH"


class CurriculumPlanner:
    """Rule-based review/new curriculum planner (``planner_v0``)."""

    policy_version = "planner_v0"

    REVIEW_MASTERY_THRESHOLD = 0.70
    NEW_MASTERY_CEILING = 0.70
    MAX_TASKS = 8
    DEFAULT_MAX_TASKS = 5
    MINUTES_BASE = 10
    MINUTES_PER_DIFFICULTY = 10

    # -- helpers -----------------------------------------------------------
    @classmethod
    def estimate_minutes(cls, task: LearningTask) -> int:
        """Deterministic synthetic time estimate derived from difficulty."""

        return cls.MINUTES_BASE + cls.MINUTES_PER_DIFFICULTY * task.difficulty

    @classmethod
    def _classify(
        cls, task: LearningTask, goal: LearningGoal, state: LearnerState
    ) -> str:
        masteries = {skill: state.mastery.get(skill, 0.0) for skill in task.skill_ids}
        if all(value >= cls.REVIEW_MASTERY_THRESHOLD for value in masteries.values()):
            return BUCKET_REVIEW
        touches_goal = any(skill in goal.target_skills for skill in task.skill_ids)
        if touches_goal and any(value < cls.NEW_MASTERY_CEILING for value in masteries.values()):
            return BUCKET_NEW
        return BUCKET_STRETCH

    @classmethod
    def _plan_id(cls, goal: LearningGoal, selected: list[LearningTask]) -> str:
        digest = hashlib.sha256(
            "\x1f".join(
                [goal.goal_id, cls.policy_version, *(task.task_id for task in selected)]
            ).encode("utf-8")
        ).hexdigest()
        return f"plan_{digest[:16]}"

    @classmethod
    def _mastery_text(cls, task: LearningTask, state: LearnerState) -> str:
        return ", ".join(
            f"{skill}={state.mastery.get(skill, 0.0):.2f}" for skill in task.skill_ids
        )

    # -- planning ----------------------------------------------------------
    def plan(
        self,
        goal: LearningGoal,
        learner_state: LearnerState,
        available_tasks: list[LearningTask],
    ) -> CurriculumPlan:
        if not isinstance(goal, LearningGoal):
            raise TypeError(f"goal must be LearningGoal, got {type(goal).__name__}")
        if not isinstance(learner_state, LearnerState):
            raise TypeError(
                f"learner_state must be LearnerState, got {type(learner_state).__name__}"
            )
        if goal.learner_id != learner_state.learner_id:
            raise ValueError(
                f"goal learner_id={goal.learner_id!r} does not match "
                f"state learner_id={learner_state.learner_id!r}"
            )
        if not isinstance(available_tasks, list) or not all(
            isinstance(task, LearningTask) for task in available_tasks
        ):
            raise TypeError("available_tasks must be list[LearningTask]")

        policy = self.policy_version
        rationale: list[str] = [
            f"POLICY: {policy}; deterministic order (ordinal, task_id); "
            "rollback = bump policy_version and re-plan the same inputs.",
            (
                f"GOAL: goal={goal.goal_id} target_skills={sorted(goal.target_skills)} "
                f"deadline_days={goal.deadline_days} weekly_minutes={goal.weekly_minutes}; "
                f"learner evidence_count={learner_state.evidence_count}."
            ),
        ]

        ordered = sorted(available_tasks, key=lambda task: (task.ordinal, task.task_id))
        if not ordered:
            rationale.append(
                "NO_AVAILABLE_TASKS: empty task catalog; plan intentionally has zero tasks "
                "(no fabricated work items)."
            )
            return CurriculumPlan(
                plan_id=self._plan_id(goal, []),
                goal_id=goal.goal_id,
                tasks=[],
                rationale=rationale,
                policy_version=policy,
            )

        buckets: dict[str, list[LearningTask]] = {
            BUCKET_REVIEW: [],
            BUCKET_NEW: [],
            BUCKET_STRETCH: [],
        }
        for task in ordered:
            buckets[self._classify(task, goal, learner_state)].append(task)

        max_tasks = min(
            self.MAX_TASKS, goal.deadline_days if goal.deadline_days else self.DEFAULT_MAX_TASKS
        )
        review_pool = buckets[BUCKET_REVIEW]
        new_pool = buckets[BUCKET_NEW]
        stretch_pool = buckets[BUCKET_STRETCH]

        review_quota = 0
        if review_pool and max_tasks >= 2 and (new_pool or stretch_pool):
            review_quota = max(1, min(len(review_pool), max_tasks // 3))
        elif review_pool and not (new_pool or stretch_pool):
            review_quota = min(len(review_pool), max_tasks)

        # Interleave: review material is placed on 0-based slots 1, 4, 7 (every
        # third slot, never first) so the plan starts with new/consolidation
        # work; leftover slots are filled from the remaining pools.
        selected: list[LearningTask] = []
        new_index = review_index = stretch_index = 0
        for slot in range(max_tasks):
            want_review = slot % 3 == 1 and review_index < review_quota
            if want_review:
                selected.append(review_pool[review_index])
                review_index += 1
            elif new_index < len(new_pool):
                selected.append(new_pool[new_index])
                new_index += 1
            elif review_index < len(review_pool):
                selected.append(review_pool[review_index])
                review_index += 1
            elif stretch_index < len(stretch_pool):
                selected.append(stretch_pool[stretch_index])
                stretch_index += 1
            else:
                break

        # Weekly-minutes budget: keep the deterministic order, drop tasks that
        # do not fit, never fabricate time.  A plan always keeps at least one
        # task so the learner is not left without work.
        budget = goal.weekly_minutes
        kept: list[LearningTask] = []
        used = 0
        for task in selected:
            cost = self.estimate_minutes(task)
            if used + cost <= budget:
                kept.append(task)
                used += cost
            elif not kept:
                kept.append(task)
                used += cost
                rationale.append(
                    f"OVER_BUDGET_MINIMUM: kept task {task.task_id} ({cost} min) even though it "
                    f"exceeds weekly_minutes={budget}; a plan must not be empty when tasks exist."
                )
            else:
                rationale.append(
                    f"BUDGET: excluded task {task.task_id} (est {cost} min > remaining "
                    f"{budget - used} min of weekly_minutes={budget})."
                )

        review_count = sum(1 for task in kept if task in review_pool)
        new_count = sum(1 for task in kept if task in new_pool)
        stretch_count = sum(1 for task in kept if task in stretch_pool)

        for task in kept:
            bucket = (
                BUCKET_REVIEW
                if task in review_pool
                else BUCKET_NEW
                if task in new_pool
                else BUCKET_STRETCH
            )
            target_note = (
                "goal target skill" if any(s in goal.target_skills for s in task.skill_ids)
                else "outside current goal targets"
            )
            if bucket == BUCKET_REVIEW:
                rationale.append(
                    f"REVIEW: task {task.task_id} skills=[{', '.join(task.skill_ids)}] "
                    f"mastery({self._mastery_text(task, learner_state)}) >= "
                    f"{self.REVIEW_MASTERY_THRESHOLD:.2f}; revisit to prevent forgetting."
                )
            elif bucket == BUCKET_NEW:
                rationale.append(
                    f"NEW: task {task.task_id} skills=[{', '.join(task.skill_ids)}] "
                    f"mastery({self._mastery_text(task, learner_state)}) < "
                    f"{self.NEW_MASTERY_CEILING:.2f}; {target_note}."
                )
            else:
                rationale.append(
                    f"STRETCH: task {task.task_id} skills=[{', '.join(task.skill_ids)}] "
                    f"mastery({self._mastery_text(task, learner_state)}); {target_note}."
                )

        rationale.append(
            f"BALANCE: {review_count} review + {new_count} new + {stretch_count} stretch "
            f"within {max_tasks} slots; review quota={review_quota} (<= 1/3 of slots); "
            f"estimated_minutes={used}/{budget}."
        )
        if review_pool and review_quota == 0 and review_count == 0 and max_tasks >= 2:
            rationale.append(
                "REVIEW_DEFERRED: review material exists but new/consolidation slots took "
                "priority this cycle; next plan re-evaluates with fresh evidence."
            )

        return CurriculumPlan(
            plan_id=self._plan_id(goal, kept),
            goal_id=goal.goal_id,
            tasks=kept,
            rationale=rationale,
            policy_version=policy,
        )
