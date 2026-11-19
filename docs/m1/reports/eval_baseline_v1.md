# M1 offline evaluation baseline (demo run)

> **Boundary:** Offline synthetic evaluation only. These numbers describe a deterministic local simulator over synthetic fixtures; they are not real teaching effectiveness, not real learner outcomes and must not be extrapolated.

## Provenance

| field | value |
| --- | --- |
| UTC date | `2026-11-19` |
| worktree SHA | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| branch | `work/m1-offline-design` |
| python | `3.11.15` |
| pytest | `9.2.0` |
| command | `cd /root/at-m1-offline && "/root/Autonomous Teacher/.venv/bin/python" -m m1_offline.demo` |

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

## NOT_RUN

- real provider / live runtime evaluation (out of scope: offline synthetic only)
- real learner outcomes (impossible offline; not claimed)

## UNVERIFIED

- M0 Runtime API capabilities (UNVERIFIED; RuntimePort is a mock abstraction)
- real teaching effectiveness (not measured; no extrapolation allowed)

## Notes

- Numbers come from a deterministic local simulator over synthetic fixtures.
- Offline synthetic simulation only. Between-policy differences (teacher_v1 minus teacher_v0: correctness: delta(v1-v0)=+0.056; rounds_to_first_success: delta(v1-v0)=+0.000; hint_efficiency: delta(v1-v0)=-0.228; independence: delta(v1-v0)=-0.500) are simulator-internal behaviour differences on fixed synthetic cases and 3 seeds. This is not real teaching effect: no significance is claimed and no real-world effectiveness is demonstrated. Conclusions are limited to this deterministic simulator.

