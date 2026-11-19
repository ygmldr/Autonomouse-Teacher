# M1 offline evaluation baseline (demo run)

> **Boundary:** Offline synthetic evaluation only. These numbers describe a deterministic local simulator over synthetic fixtures; they are not real teaching effectiveness, not real learner outcomes and must not be extrapolated.

## Provenance

| field | value |
| --- | --- |
| UTC date | `2026-11-19` |
| base commit (worktree baseline) | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| implementation commit (reviewed, artifact generated on top) | `0bb13d27b069dfb71b31ce7e02f9cde41f9bb071` |
| working tree dirty at generation | `True` |
| branch | `work/m1-offline-design` |
| dependency fingerprint | `ad30fbdae1d7318d346b0625a1157df20f9139ef2ece00f7f118a1c9ced6abd0` |
| python | `3.11.15` |
| pytest | `9.2.0` |
| command | `cd /root/at-m1-offline && "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo` |

> Note: frozen reviewed implementation commit; post-review report/doc fixes were generated on top of it -- the final commit SHA is recorded in docs/parallel/STATUS.md (Lead-owned), never implied to be this base SHA

## Metrics (planned vs measured)

| metric | planned | actual | evidence | source |
| --- | --- | --- | --- | --- |
| closed_loop_rounds_v1 | >=3 | 3 | MEASURED | `m1_offline.demo` |
| closed_loop_trace_events | >=19 (4 baseline + 5 steps x 3 rounds) | 19 | MEASURED | `m1_offline.demo` |
| replay_equivalence | 100% | PASS | MEASURED | `m1_offline.demo` |
| v0v1_cases_assessed | fixed catalog >=12 cases | 12 assessed / 14 catalog | MEASURED | `m1_offline.demo` |
| v0v1_rounds | >=12 | 72 | MEASURED | `m1_offline.demo` |
| v0v1_failure_cases | >=1 | 58 | MEASURED | `m1_offline.demo` |
| contamination_status | all PASS | {"FAIL": 0, "NOT_RUN": 0, "PASS": 4} | MEASURED | `m1_offline.demo` |
| demo_determinism | byte-identical trace across two runs | PASS | MEASURED | `m1_offline.demo (in-process double run)` |
| teacher_v0_correctness | record mean/variance | mean=0.248512 var=0.004634 | MEASURED | `m1_offline.demo` |
| teacher_v0_rounds_to_first_success | record mean/variance | mean=0.916667 var=0.00463 | MEASURED | `m1_offline.demo` |
| teacher_v0_hint_efficiency | record mean/variance | mean=0.75 var=0.0 | MEASURED | `m1_offline.demo` |
| teacher_v0_independence | record mean/variance | mean=1.0 var=0.0 | MEASURED | `m1_offline.demo` |
| teacher_v1_correctness | record mean/variance | mean=0.304067 var=0.001465 | MEASURED | `m1_offline.demo` |
| teacher_v1_rounds_to_first_success | record mean/variance | mean=0.916667 var=0.00463 | MEASURED | `m1_offline.demo` |
| teacher_v1_hint_efficiency | record mean/variance | mean=0.522222 var=0.000189 | MEASURED | `m1_offline.demo` |
| teacher_v1_independence | record mean/variance | mean=0.5 var=0.018519 | MEASURED | `m1_offline.demo` |

## Checks

| check | description | status |
| --- | --- | --- |
| C1_hidden_public_separation | hidden fixtures exist and are not part of the public surface | PASS |
| C2_hidden_leakage | hidden-only fixture text does not appear in public docs/traces/fixtures/teacher sources | PASS |
| C3_injection_not_in_system_prompt | untrusted injection documents never appear verbatim in system instructions | PASS |
| C4_no_network_or_real_data | scoped code/fixtures/docs contain no network imports, API keys or real-data shapes | PASS |

## Structured sections

### comparison

```json
{
  "case_catalog_size": 14,
  "cases_assessed": [
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
    "cf_tp_dedupe_sorted"
  ],
  "conclusion": "Offline synthetic simulation only. Between-policy differences (teacher_v1 minus teacher_v0: correctness: delta(v1-v0)=+0.056; rounds_to_first_success: delta(v1-v0)=+0.000; hint_efficiency: delta(v1-v0)=-0.228; independence: delta(v1-v0)=-0.500) are simulator-internal behaviour differences on fixed synthetic cases and 3 seeds. This is not real teaching effect: no significance is claimed and no real-world effectiveness is demonstrated. Conclusions are limited to this deterministic simulator.",
  "delta_v1_minus_v0": {
    "correctness": 0.055555,
    "hint_efficiency": -0.227778,
    "independence": -0.5,
    "rounds_to_first_success": 0.0
  },
  "disclaimer": "offline synthetic simulation; not real teaching effect. These numbers describe a deterministic local simulator over synthetic fixtures and must not be extrapolated to real learners, real models or real teaching outcomes.",
  "failure_case_count": 58,
  "failure_cases": [
    {
      "case_id": "cf_array_max_subarray",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 9,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 1,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_array_running_sum",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 2,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_bs_first_index",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 5,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_bs_search_insert",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 6,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_dp_climb_stairs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 7,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_dp_coin_change",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 10,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 8,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_dp_lcs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 9,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_graph_bfs_dist",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 10,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_graph_count_components",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 11,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_sort_insertion",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 12,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_array_running_sum",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 2,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_array_sum_even",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 3,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_tp_dedupe_sorted",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 6,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 4,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_bs_first_index",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 5,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_bs_search_insert",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 6,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_dp_climb_stairs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 5,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 7,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_dp_coin_change",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 10,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 8,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_dp_lcs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 9,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_graph_bfs_dist",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 3,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 10,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_graph_count_components",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 11,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_sort_insertion",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 12,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_array_max_subarray",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 9,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 1,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_bs_first_index",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 5,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_bs_search_insert",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 6,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_dp_climb_stairs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 7,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_dp_coin_change",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 10,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 8,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_dp_lcs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 9,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_graph_bfs_dist",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 3,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 10,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_graph_count_components",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 5,
      "hidden_cases_total": 8,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 11,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_sort_insertion",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v0",
      "policy_version": "teacher_v0",
      "round": 12,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_array_max_subarray",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 9,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 1,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_array_running_sum",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 2,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_bs_first_index",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 5,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_bs_search_insert",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 6,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_dp_coin_change",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 10,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 8,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_dp_lcs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 9,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_graph_bfs_dist",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 10,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_graph_count_components",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 11,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_sort_insertion",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 12,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 0
    },
    {
      "case_id": "cf_array_sum_even",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 3,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_tp_dedupe_sorted",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 6,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 4,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_bs_first_index",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 5,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_bs_search_insert",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 6,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_dp_climb_stairs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 5,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 7,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_dp_coin_change",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 10,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 8,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_dp_lcs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 9,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_graph_bfs_dist",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 3,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 10,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_graph_count_components",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 11,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_sort_insertion",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 12,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 1
    },
    {
      "case_id": "cf_array_max_subarray",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 9,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 1,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_bs_first_index",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 5,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_bs_search_insert",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 6,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_dp_climb_stairs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 7,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_dp_coin_change",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 10,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 8,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_dp_lcs",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 9,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_graph_bfs_dist",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 3,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 10,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_graph_count_components",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 5,
      "hidden_cases_total": 8,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 11,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    },
    {
      "case_id": "cf_sort_insertion",
      "failure_modes": [
        "hidden_cases_failed"
      ],
      "hidden_cases_passed": 0,
      "hidden_cases_total": 7,
      "policy": "teacher_v1",
      "policy_version": "teacher_v1",
      "round": 12,
      "scorer_id": "independent_cf_judge_v0",
      "seed": 2
    }
  ],
  "max_rounds": 12,
  "protocol": {
    "blind_rubric": true,
    "case_catalog": "fixtures/m1/cf/problems (synthetic, public) + hidden judge fixtures",
    "dimensions": [
      "correctness",
      "rounds_to_first_success",
      "hint_efficiency",
      "independence"
    ],
    "fixed_cases": true,
    "fixed_seeds": [
      0,
      1,
      2
    ],
    "mastery_threshold": 1.01,
    "mastery_threshold_note": "frozen above 1.0 for the comparison only so both policies run the same fixed number of rounds; this is a protocol control, not a claim about learning.",
    "max_rounds": 12,
    "policies": {
      "teacher_v0": "FixedPolicy (fixed LIGHT_HINT ladder, non-adaptive)",
      "teacher_v1": "AdaptivePolicy (diagnosis/evidence adaptive hint ladder)"
    },
    "protocol_id": "m1.compare.v0",
    "scorer_module": "blind_rubric_v0",
    "scorer_sees_policy_identity": false,
    "teacher_self_report_used_as_truth": false
  },
  "run_digest": "cb6cb07da2a68622f2ccceac560093f36d4385ad13632c8ce12ccdff02d1645e",
  "runs": {
    "teacher_v0": [
      {
        "failure_markers": [
          "hidden_cases_failed"
        ],
        "halt_reason": null,
        "rounds": 12,
        "scores": {
          "correctness": 0.166667,
          "hint_efficiency": 0.75,
          "independence": 1.0,
          "rounds_to_first_success": 0.833333
        },
        "seed": 0,
        "trace_digest": "6983c4f1eb272ec27a48110061632531c997430ce0e0cc4c7c3c32b8ee3da113",
        "trajectory_id": "traj_d17678007b402e33"
      },
      {
        "failure_markers": [
          "hidden_cases_failed"
        ],
        "halt_reason": null,
        "rounds": 12,
        "scores": {
          "correctness": 0.245536,
          "hint_efficiency": 0.75,
          "independence": 1.0,
          "rounds_to_first_success": 1.0
        },
        "seed": 1,
        "trace_digest": "32fecc77c3ac75574124181974d3609de81d2c6bd21887d5ee5b9e3de90eb3e0",
        "trajectory_id": "traj_d17678007b402e33"
      },
      {
        "failure_markers": [
          "hidden_cases_failed"
        ],
        "halt_reason": null,
        "rounds": 12,
        "scores": {
          "correctness": 0.333333,
          "hint_efficiency": 0.75,
          "independence": 1.0,
          "rounds_to_first_success": 0.916667
        },
        "seed": 2,
        "trace_digest": "08030886c50b3907bd50e68b1a67463d5534b888c9419f15eebfd4a2e9f2166d",
        "trajectory_id": "traj_d17678007b402e33"
      }
    ],
    "teacher_v1": [
      {
        "failure_markers": [
          "hidden_cases_failed"
        ],
        "halt_reason": null,
        "rounds": 12,
        "scores": {
          "correctness": 0.25,
          "hint_efficiency": 0.5125,
          "independence": 0.666667,
          "rounds_to_first_success": 0.833333
        },
        "seed": 0,
        "trace_digest": "5632c365309b88f701f7881f90c23e09187266c2d406fb67316ae5b164f3af42",
        "trajectory_id": "traj_d17678007b402e33"
      },
      {
        "failure_markers": [
          "hidden_cases_failed"
        ],
        "halt_reason": null,
        "rounds": 12,
        "scores": {
          "correctness": 0.328869,
          "hint_efficiency": 0.541667,
          "independence": 0.5,
          "rounds_to_first_success": 1.0
        },
        "seed": 1,
        "trace_digest": "5c2645ff70b99af628464e542b52b22c72f3bc365cfcdfa55c6167de44ae2195",
        "trajectory_id": "traj_d17678007b402e33"
      },
      {
        "failure_markers": [
          "hidden_cases_failed"
        ],
        "halt_reason": null,
        "rounds": 12,
        "scores": {
          "correctness": 0.333333,
          "hint_efficiency": 0.5125,
          "independence": 0.333333,
          "rounds_to_first_success": 0.916667
        },
        "seed": 2,
        "trace_digest": "87d44093d660c543f8be2a3651efc9b7fb3ee77042fb1f099674c2c7ccdbb85a",
        "trajectory_id": "traj_d17678007b402e33"
      }
    ]
  },
  "seeds": [
    0,
    1,
    2
  ],
  "statistics": {
    "teacher_v0": {
      "correctness": {
        "mean": 0.248512,
        "n": 3,
        "stdev": 0.068074,
        "values": [
          0.166667,
          0.245536,
          0.333333
        ],
        "variance": 0.004634
      },
      "hint_efficiency": {
        "mean": 0.75,
        "n": 3,
        "stdev": 0.0,
        "values": [
          0.75,
          0.75,
          0.75
        ],
        "variance": 0.0
      },
      "independence": {
        "mean": 1.0,
        "n": 3,
        "stdev": 0.0,
        "values": [
          1.0,
          1.0,
          1.0
        ],
        "variance": 0.0
      },
      "rounds_to_first_success": {
        "mean": 0.916667,
        "n": 3,
        "stdev": 0.068042,
        "values": [
          0.833333,
          1.0,
          0.916667
        ],
        "variance": 0.00463
      }
    },
    "teacher_v1": {
      "correctness": {
        "mean": 0.304067,
        "n": 3,
        "stdev": 0.038275,
        "values": [
          0.25,
          0.328869,
          0.333333
        ],
        "variance": 0.001465
      },
      "hint_efficiency": {
        "mean": 0.522222,
        "n": 3,
        "stdev": 0.013749,
        "values": [
          0.5125,
          0.541667,
          0.5125
        ],
        "variance": 0.000189
      },
      "independence": {
        "mean": 0.5,
        "n": 3,
        "stdev": 0.136083,
        "values": [
          0.666667,
          0.5,
          0.333333
        ],
        "variance": 0.018519
      },
      "rounds_to_first_success": {
        "mean": 0.916667,
        "n": 3,
        "stdev": 0.068042,
        "values": [
          0.833333,
          1.0,
          0.916667
        ],
        "variance": 0.00463
      }
    }
  },
  "total_rounds_measured": 72
}
```

### contamination

```json
{
  "checks": [
    {
      "check_id": "C1_hidden_public_separation",
      "counts": {
        "hidden_file_count": 21,
        "public_file_count": 105
      },
      "description": "hidden fixtures exist and are not part of the public surface",
      "status": "PASS"
    },
    {
      "check_id": "C2_hidden_leakage",
      "counts": {
        "hash_window_hits": 0,
        "needles_checked": 34,
        "scanned_public_files": 105,
        "substring_hits": 0
      },
      "description": "hidden-only fixture text does not appear in public docs/traces/fixtures/teacher sources",
      "status": "PASS"
    },
    {
      "check_id": "C3_injection_not_in_system_prompt",
      "counts": {
        "injection_documents": 4,
        "needles_checked": 9,
        "system_instruction_chunks": 1
      },
      "description": "untrusted injection documents never appear verbatim in system instructions",
      "status": "PASS"
    },
    {
      "check_id": "C4_no_network_or_real_data",
      "counts": {
        "findings": 0,
        "scanned_files": 139
      },
      "description": "scoped code/fixtures/docs contain no network imports, API keys or real-data shapes",
      "status": "PASS"
    }
  ],
  "overall_ok": true,
  "status_counts": {
    "FAIL": 0,
    "NOT_RUN": 0,
    "PASS": 4
  }
}
```

## Artifacts

- `docs/m1/traces/loop_v1_3rounds.jsonl`
- `docs/m1/traces/loop_v0_3rounds.jsonl`
- `docs/m1/reports/contamination_v1.json`

## NOT_RUN

- real provider / live runtime evaluation (out of scope: offline synthetic only)
- real learner outcomes (impossible offline; not claimed)

## UNVERIFIED

- M0 Runtime API capabilities (UNVERIFIED; RuntimePort is a mock abstraction)
- real teaching effectiveness (not measured; no extrapolation allowed)

## Notes

- Numbers come from a deterministic local simulator over synthetic fixtures.
- Offline synthetic simulation only. Between-policy differences (teacher_v1 minus teacher_v0: correctness: delta(v1-v0)=+0.056; rounds_to_first_success: delta(v1-v0)=+0.000; hint_efficiency: delta(v1-v0)=-0.228; independence: delta(v1-v0)=-0.500) are simulator-internal behaviour differences on fixed synthetic cases and 3 seeds. This is not real teaching effect: no significance is claimed and no real-world effectiveness is demonstrated. Conclusions are limited to this deterministic simulator.

