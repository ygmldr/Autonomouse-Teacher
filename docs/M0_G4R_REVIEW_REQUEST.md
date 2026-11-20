# M0 G4-R — Independent Review Request（无 Key）

- **文档 ID**：`M0-G4R-REVIEW-REQUEST-v1`
- **提出者**：Integration 子 Agent（非 Lead、非 Reviewer）；本文不构成自证
- **base**：`3e7afee077845a071cd364e93ab209cac20b2d5f`；**冻结 impl**：`d33e0aabd1714a486325b745c436cb59855d6539`（集成分支 `work/g4r`）
- **范围**：本机、无 Key、无真实 Provider/外部 HTTP/TCP/计费。**不是** E5-PreLive Full、不是 G4-H/G5/G6/Live 授权。

## 0. 冻结身份与交付物

| 对象 | 值 |
|---|---|
| impl_sha | `d33e0aabd1714a486325b745c436cb59855d6539` |
| base_sha | `3e7afee…` |
| 最终 Stage | `artifacts/g4/c/stages/stage-20261120T165407Z`；manifest **`cc7ccb61bc4df76675b14e1f73bdd9209d3a13eeda7e79193e913ea284874d03`**；stage tree **`933f2c07a6c79415183a4d3f1db1ba19249b95d96ee88334bd43e71dd40d3882`**；trusted `f10053d4…`；candidate `131ab68e…`；base/head=`d33e0aa` |
| 历史 Stage | `stage-20261119T142828Z`（manifest `82e10c6f…`）仅 HISTORICAL_REFERENCE |
| rootfs / deps | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` / `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| DSH runtime | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`（0.2.2-rc.2） |
| adapter built JS | `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba` |
| Node | `v22.23.2` |
| 矩阵 | `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`（65 cases：29 PASS / 14 PARTIAL / 12 NOT_RUN / 4 UNVERIFIED / 6 BLOCKED；sha256 见报告消息） |
| 证据根 | `artifacts/g4r/integration/`、`artifacts/g4r/integration-regressions/`、`artifacts/g4r/logs/`；核心索引 `integration-env.json`、`integration-stage.json`、`integration-regressions/{host,oci,node,ruff,scanner,livegate}.json` |

## 1. 文档与关键证据 SHA（供独立复算）

| 文件 | sha256 |
|---|---|
| impl 树 | `git rev-parse d33e0aa^{tree}`（Reviewer 自算） |
| Stage manifest | `cc7ccb61…`（`sha256sum artifacts/g4/c/stages/stage-20261120T165407Z/manifest.json`） |
| `integration-env.json` | 见 `artifacts/g4r/integration/integration-env.json` |
| `integration-stage.json` | 见 `artifacts/g4r/integration/integration-stage.json` |
| 各 `integration-regressions/*.json` | 见目录（库内不提交，Reviewer 只读复算） |

## 2. 精确命令 / Case ID / 日志路径（Owner 侧，待独立复跑）

| Case | 命令（摘要） | UTC | 结果（Owner） | 日志/证据 |
|---|---|---|---|---|
| HOST-ALL | `pytest tests -q -p no:cacheprovider --junitxml=…`（venv 3.11.15，`PYTHONPATH=src:<deps>`） | 16:52:24–17:00:55Z | 1420 collected / **1412 passed / 5 failed / 3 skipped** / 510.8s | `artifacts/g4r/logs/host-full-single-20261120T165224Z.log`、`…/host-full-junit-20261120T165224Z.xml` |
| HOST-CLASS | 5 个失败 nodeid 逐一复跑（含 `chmod 0444 config/dsh/target-runtime.patch.yml` 环境修复） | 17:09:02–17:09:15Z | 3 项通过（drift/config-mode）、1 项 stale-baseline 仍失败（预期）、1 项 flaky 单文件 9 passed | `artifacts/g4r/integration/host-failure-classification-20261120T170902Z.log` |
| MINI | `pytest tests/g4r_packet tests/integration/g4_f2`；`pytest tests/integration/g4r_auth`；`r1_independent_probe.py --rounds 50`；`pytest tests/integration/g4r_recovery`；A12 ×30 | 16:55:09–17:00:09Z | 42 passed / 26 passed / probe PASS / 19 passed / 30/30 | `artifacts/g4r/integration/minimal-rerun-20261120T165509Z.log` |
| L2-F2 | `run_f2_evidence.py --stage <final-stage> --out-dir artifacts/g4r/integration/l2/f2` | 17:05:50–17:06:20Z | `ok=true`；Echo dispatch=1、Tool two rounds dispatch=2；0 real model/HTTP/key | `artifacts/g4r/integration/l2/f2/`（summary/runs/DB 只读副本/dispatch-window） |
| L2-F5 | `run_g4_f5.py --only timeout-pre-send,revocation-post-reserve,timeout-post-send` | 17:06:21–17:06:51Z | **3/3 true**；`containers_after=[]` | `artifacts/g4r/integration/l2/f5/`（DB snapshot、receipt、gate journal、request-lifecycle） |
| OCI | `podman run --network none --read-only --user 65534:65534 --rootfs <cp -a rootfs copy> … -m pytest tests/ …`（43 legacy deselect + `--deselect=tests/integration/g4r_auth`） | 17:12:05–17:13:27Z | 1081 tests / **1052 passed / 1 failed / 28 skipped / 69 deselected** / 80.4s；冻结 rootfs 前后 `25491e45…` | `artifacts/g4r/logs/oci-filtered-deselect.{log,meta}`、`artifacts/g4r/integration/oci/junit-oci-filtered.xml` |
| NODE | adapter/guard/skill 真实 TAP（fixed rootfs） | 16:57–17:00Z | **36/36**（9+19+8） | `artifacts/g4r/integration/node/*.log` |
| RUFF | `ruff check --no-cache <changed scope>`；repo-wide 对照 | 16:48:16Z | changed scope **All checks passed**；repo-wide 5 个既有错误（旧 scripts） | `artifacts/g4r/integration/ruff-20261120T164816Z.log` |
| SCANNER | self-test / 全历史 / `--no-history` / positive control | 16:48:16Z、17:09Z | 0 findings（503 files/1070 blobs/208 commits）；正控检出伪造 `sk-`、exit 1、masked | `artifacts/g4r/integration/scanner-*.log`、`host-failure-classification-*.log` |
| LIVEGATE | inspect / require_live / run_live / CLI --live / Adapter 4 入口 / strace | 16:52:55Z、17:09Z | BLOCKED / SECURITY_BLOCKED / exit3 / exit3 / 4×SECURITY_BLOCKED / 0 network lines | `artifacts/g4r/integration/livegate-20261120T165255Z.log` |

## 3. 已证实 / UNVERIFIED / BLOCKED

**已证实（Owner 侧，待独立复跑）**：P2-03/04/05/06 修复（R1/R2 host suites + stress/probe + L2 F5）；最终 Stage 身份（base=d33e0aa、loaded src 52/52 == git）；无 Key/无真实调用；LiveGate 四入口拒绝；Host/OCI/Node/Ruff/Scanner 计数与逐项分类；独占窗口 L2 F2 ok + F5 3/3 且 canonical 前后一致。

**UNVERIFIED**：R5-01..03（F4-06 candidate crash + live Controller，无可控注入）；RG-01/02/04/06/07/11（PARTIAL L1 hook）、RG-08、RG-05/09/10/12（NOT_RUN）；B03/E5-P04（仍 UNVERIFIED）；独立 Reviewer 的全部结论尚不存在。

**BLOCKED**：`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`；`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、`M0=DECISION_PENDING`；真实 Key/Broker/Egress/TLS/账单全部 HUMAN_REQUIRED。

## 4. 被测模型 / 费用来源

```text
real model calls = 0; real external HTTP/TCP = 0; real spend/invoice = 0; real Provider Key = 0
route = synthetic_only / offline-test-only-g3b / fixture-bridge-v1
所有 usage/cost = synthetic fixture / local bookkeeping，不得当真实账单
```

## 5. 请求 Reviewer 复核（建议范围，按优先级）

1. **身份/范围**：`git rev-parse d33e0aa`、`git diff 3e7afee..d33e0aa`（31 files + 本轮 docs）、`src/` 变更仅 `authorization.py`/`controller.py`/`request_lifecycle.py`/`recovery_diagnostics.py`；受保护文件（gates/run_live/dsh_adapter/cli）零 diff；冻结 Packet/旧 Reviewer 报告未改。
2. **最终 Stage**：manifest `cc7ccb61…`/tree `933f2c07…`/trusted/candidate；loaded source 52/52 == git blobs；rootfs/deps/runtime/adapter canonical；旧 Stage 仅 HISTORICAL。
3. **P2-03**：自建多线程/多进程/epoch/crash/symlink/FS 负例；恰一次消费、loser 稳定 replay、fail-closed 不放松（R1-08 reviewer 独立探针）。
4. **P2-05/06**：request-lifecycle vs dispatch-window 真实层级（不得伪造 dispatch）；recovery 保留 first cause + 独立 observation、Broker 唯一权威、不重发/不双结算。
5. **L2**：从只读 DB 副本独立对账 Echo/Tool/resume/F5 的 Res/Claim/Intent/Attempt/Receipt/Fake/held/usage；对比 Owner 数值。
6. **Packet v2（F-C 构建的最终包）**：全树集合/hash/tree；注入 sidecar/隐藏/未知/symlink/mode/篡改必须 FAIL；env/manifest/review LiveGate reasons 逐元素相等；旧 Packet 字节不变。
7. **Registry**：RG 状态是否与证据等级一致（L1 vs L2 attestation）；不得把 R3 写成 E5-P04 PASS。
8. **回归**：Host 1420/1412/5/3 逐 nodeid；OCI 1081/1052/1/28/69 deselect（43 legacy 未扩大 + 26 explicit g4r_auth 环境类）；Node 36/36；Ruff/Scanner/LiveGate/strace。
9. **环境纪律**：漂移窗口与清理恢复记录（16:52–16:59Z → 17:01:49Z `25491e45`）、独占窗口快照、`cp -a` 副本政策；确认没有把漂移窗口产物当作 NO_DRIFT 证据。
10. **不一致事件**：Delta-pre `5bf9b8b` 的 test-only collection error（已重冻结修复）；历史 OCI junit 误覆盖后从 Packet 原字节恢复（如实记录）。

## 6. 请求的最高裁定（枚举）

```text
PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE
PASS_FOR_G4R_NO_KEY_SCOPE_WITH_B03_RUNTIME_SNAPSHOT_VERIFIED   （仅当 Reviewer 独立证明冻结 Runtime 完整注册集合并限定 Scope）
PARTIAL_FOR_G4R_NO_KEY_SCOPE
FAIL_FOR_G4R_NO_KEY_SCOPE
BLOCKED_NEEDS_ENVIRONMENT_OR_HUMAN
```

- 不得给出 `E5_PRELIVE_FULL PASS`、`G4-H/G5/G6 PASS`、`LIVE_APPROVED`、`M0_GO` 或等价表述。
- Reviewer 必须从未参与本轮设计的独立 worktree/分支，从冻结 SHA 独立复现；不得采信 Owner 的 summary/status 文字；发现 P0/P1/真实 Key/网络/证据篡改 → STOP 并保全证据。

## 7. 已知限制（主动披露）

1. OCI filtered 的 `--deselect=tests/integration/g4r_auth`（26 tests）为**环境 harness 显式新增**（uid 65534 与授权目录 owner 校验冲突），legacy 43 未扩大；请 Reviewer 签收该差异，不得静默接受其它新增 deselect。
2. 环境并非全程 NO_DRIFT：见本文 §5.9 与 `integration-env.json` 漂移链；独占窗口内为 NO_DRIFT。
3. `R5-01..03` 未验证（无可控 Candidate crash 注入），不得据 F4 旧证据外推恢复语义。
4. `B03/E5-P04` 仍 UNVERIFIED；`P2-RUN-IDENTITY/USERNS/DISK` 等未关闭项见 `M0_G4R_FINDINGS_AND_DISPOSITION.md` §4。
5. 本轮无 GitHub PR（无 gh/token）：提交为分支 commit，真实 PR 由维护者创建；不得把 commit 列表称为 PR。

> 本请求不构成 PASS/授权；Reviewer 独立复核后 STOP，等待维护者决策。
