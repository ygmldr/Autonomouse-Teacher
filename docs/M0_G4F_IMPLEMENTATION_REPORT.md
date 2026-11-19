# M0 G4-F — Closeout / Integration / Freeze 实现报告（No-Key）

- **任务**：G4-F 收口 —— F1 scanner、F2 DSH 工具面/辅助请求可观测、F3 费用权威、
  F4 真实 resume、F5 撤销/超时/在途失败之后，在最终 HEAD 做联合重跑、全量回归、
  证据矩阵、独立复核请求与 Review Packet 冻结。
- **执行者**：G4-F6 Integration / Freeze / Review-Packet Agent（Lead 委派；只做集成、
  回归、证据、矩阵、报告与 Packet，不改产品语义/不删测试/不放宽断言）。
- **冻结身份**：base `bb2e9142a4e96e2b8fbe65bb99f1b4c045260251`（G4-E 收口后）→
  impl `e7d92967ec0ece80de4a1a3705f637e8eb9bde99`（F1–F5 + F6 集成兼容修复）→
  code `dbacb76f98a1a91559ff70e02bf544ace76ed7b5`（最后 `src` 提交）→
  docs 本文件所在提交 → build 本目录 Packet 构建时的 HEAD。
- **G4-F stage**：`artifacts/g4/c/stages/stage-20261119T142828Z`，base=head=`e7d9296`，
  manifest `82e10c6ffe37e401a58730e9abcaa691f19d6702a7276c03df625d5b4636e501`，
  stage tree `7d32ec1d8b02726ba52ef8303e8677b46384e9954559e838b31bb8c58f222068`，
  trusted tree `6d887bbf4c83ee87145bd5e71d97475a2c61cdbe97b101302650eb84cc1b5aec`，
  candidate tree `2459db9df83b9dedfa68c6c0210f5904f0c11601e57744a3d357c4884a06907c`。
- **性质**：**no-key / no-model / no-external-network / no-live / no-podman-pull**。
  0 真实 Key、0 真实模型、0 外部 HTTP/TCP、0 真实计费；全部 provider 请求为 synthetic
  Fake；容器全部 `--network none`、`--read-only`、`--cap-drop ALL`、
  `--security-opt no-new-privileges`；rootfs `25491e45…`、deps `e07729d7…` canonical。
- **最高可交付裁定**：`PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE`（本报告不自行出具；
  由独立 Reviewer 按 `docs/M0_G4F_REVIEW_REQUEST.md` 出具）。

```text
G4-F  = PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE (candidate; independent review required)
B03   = UNVERIFIED (no authoritative merged registry)
B07   = FALLBACK_ONLY @ frozen config (no extra provider request observed)
E5-P04= UNVERIFIED (unchanged)
G4-H  = NOT_AUTHORIZED; G5 = BLOCKED; G6 = NOT_RUN; LiveGate = BLOCKED; M0 = DECISION_PENDING
E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

---

## 0. 结论摘要

| 项 | 结果 |
|---|---|
| 基线 | HEAD `95ae99a`（F1–F5 完成）、工作区 clean 已核实；最终 impl `e7d9296`（F6 兼容修复） |
| 最终 HEAD stage | 真实构建并验证；base==head；rootfs/deps canonical；18/18 loaded modules == HEAD blob |
| F4 真实 resume 重跑 | **PASS**：resume 38/38 checks、crash-resume 22/22；独立审计 19/19 + 12/12 |
| F2 DSH Echo/Tool 重跑 | **PASS**：Echo 1/1/1/1/1，Tool 2/2/2/2/2；raw-UDS 7 负例 + 1 正例 + 2 auxiliary 全符合 |
| F2 辅助请求 | **`NO_EXTRA_PROVIDER_REQUEST_OBSERVED`**（3 dispatch = 3 assistant = 3 Receipt = Fake 3） |
| F3 费用权威重跑 | **PASS**：host 8/8；L2 7/7（89 checks）；`held>0`、crash PENDING、无二次结算 |
| F5 失败窗口重跑 | **PASS**：13/13 cases、162/162 checks；可停止 vs 保守边界与 F5 报告一致 |
| Host full | **1357 collected = 1352 passed / 4 failed / 1 skipped**；4 项逐条归因（已知 frozen-src/host-only） |
| 固定 OCI | raw 1018/26/43（43 全为环境类）→ filtered **1018 passed / 26 skipped / 43 deselects / 0 failed**；root replay **351 passed / 8 deselects / 0 failed** |
| Node | adapter 9 + guard 19 + skill 8 = **36 pass / 0 fail**（真实 TAP） |
| Ruff | G4-E 口径 scoped **All checks passed**；repo-wide 38 findings（37 既有 + 1 F1 测试 F841） |
| 扫描器 | 全历史 `files=467 blobs=739 commits=165 findings=0`；self-test PASS；7/7 tests PASS |
| LiveGate/CLI/Adapter/run_live | 全部 BLOCKED/exit 3；5 类 env 注入无效；0 外部 socket 尝试 |
| 矩阵 | 46 行 = **38 PASS / 2 UNVERIFIED / 5 NOT_RUN（Reviewer）/ 1 BLOCKED（E5 Full）** |
| 终态 | `containers_after=[]`；rootfs/deps canonical；`podman ps -a` 空；0 Key/网络/模型 |
| Review Packet | `artifacts/review-packet-g4f-e7d92967ec0e/`（自校验 100%，见 §11） |

---

## 1. 身份、提交链与不可变面

### 1.1 提交链（base → impl）

```text
bb2e914  (base; G4-E 收口)
  0347f3f feat: G4-F1 scanner strict sentinel + missed-detection negatives
  b97bf72 docs: G4-F1 report
  3edf48c fix: G4-F3 authoritative cost semantics and unknown-cost held
  7000f72 docs: G4-F3 report
  b963ad4 feat: G4-F4 real dual-principal DSH session resume
  2ff60c0 docs: G4-F4 G4-C regression counts
  25fb9a2 docs: G4-F4 F2 merge scope
  40af7b1 feat: G4-F2 per-dispatch tool and auxiliary request observability
  64d32cb fix: G4-F2 evidence runner frozen case names and lazy claim table
  339312b fix: G4-F2 evidence analysis handles reused DSH request headers
  0123884 docs: G4-F2 report
  dbacb76 feat: G4-F5 revocation timeout and in-flight failure negatives
  c804bb8 fix: G4-F5 dsh recovery stop timing and deadline override
  95ae99a docs: G4-F5 report
  e7d9296 fix: G4-F6 launcher namespace compatibility + F2 evidence output isolation
```

> `e7d9296` 是**本轮发现的真实集成回归**的最小 additive 修复（见 §4）。只改
> `scripts/g4/launch_c.py` 的 `getattr` 兼容读取与
> `tests/integration/g4_f2/run_f2_evidence.py` 的 `--out-dir`（默认不变），
> 未改 `src/`、未删测试、未放宽断言。`code_sha` 因此仍为 F5 的 `dbacb76`。

### 1.2 冻结输入（最终 HEAD）

| 对象 | 值 |
|---|---|
| base | `bb2e9142a4e96e2b8fbe65bb99f1b4c045260251` |
| impl（证据 HEAD） | `e7d92967ec0ece80de4a1a3705f637e8eb9bde99` |
| code（最后 `src` 提交） | `dbacb76f98a1a91559ff70e02bf544ace76ed7b5` |
| G4-F stage | `stage-20261119T142828Z`（manifest `82e10c6f…`，tree `7d32ec1d…`） |
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| DSH runtime | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`（`0.2.2rc2`） |
| adapter built JS | `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba` |
| Node | `v22.23.2` |
| 实际加载模块 | **18/18** 来自 `/project/src`，且逐模块 `sha256 == HEAD blob == stage 副本` |
| LiveGate | `BLOCKED`（未改变） |

Loaded modules 证据：`artifacts/g4f/f6/integration/f4-resume/loaded-modules.json`
（来源为真实容器 `peercred/trusted-modules.json`，非宿主静态推断）。
`controller.py` 加载值 `0152fcde6bba7c7989740b1bfde8f72744e6c709da22ebbe4940cb443eb35ca3`。

---

## 2. F1–F5 摘要（本轮不重写其结论）

| 包 | 结论 | 本轮重跑/复核 |
|---|---|---|
| **F1** | scanner 严格哨兵 + 7 测试 + 全历史 0 findings | self-test PASS；`files=467 blobs=739 commits=165 findings=0`；7/7 tests PASS（§7） |
| **F2** | per-dispatch tool journal；Echo 1/1/1/1/1、Tool 2/2/2/2/2；B03/E5-P04 UNVERIFIED；B07 fallback-only | Echo/Tool/raw-UDS/adapter 全部在最终 HEAD 重跑通过（§3.2） |
| **F3** | Broker 唯一费用权威；unknown held>0；Host 8/8 + L2 8/8 | host 8/8 + L2 7/7 重跑（§3.3） |
| **F4** | real resume L2（绑定 `7000f72`）；crash-resume 限域 | 在最终 HEAD 重建 stage 后重跑 + 独立审计（§3.1） |
| **F5** | 13/13 L2 revocation/timeout/crash；可停止 vs 保守边界 | 全 13 case 在最终 HEAD 重跑 162/162 checks（§3.4） |

F4 原证据绑定 `7000f72`（F2 合并前）。本轮把 F4 证据重新绑定到最终 HEAD：
两个 phase 均在 `stage-20261119T142828Z` 上重新执行，旧证据保留未改。

---

## 3. 最终 HEAD 联合重跑（真实双 Principal）

所有窗口内 `containers_after=[]`、`rootfs_canonical=true`、`deps_canonical=true`、
`stage_unchanged=true`、`real_model_calls=0`、`real_external_http_calls=0`、
`provider_keys_seen=0`。逐案 argv/UTC/exit 见 `artifacts/g4f/f6/integration/commands.jsonl`。

### 3.1 F4 真实 DSH resume（`artifacts/g4f/f6/integration/f4-resume/`）

命令：

```text
python3 -B scripts/g4/run_g4_f4.py --stage artifacts/g4/c/stages/stage-20261119T142828Z \
  --out-dir artifacts/g4f/f6/integration/f4-resume
```

| phase | UTC | exit | checks | 关键结果 |
|---|---|---:|---:|---|
| `resume` | 14:29:37→14:29:46 | 0 | **38/38** | 两个 Candidate 容器；`start_session`→`resume_session`；session 14→24 行（3597→6005 bytes），`reason:"resume"` 1 次 |
| `crash-resume` | 14:29:47→14:29:56 | 0 | **22/22** | crash 后 1 Attempt `SETTLEMENT_UNCERTAIN`、1 Reservation `PENDING 0.002731`、Fake 0；恢复 Controller exit 3 `ADMISSION_REPLAYED`；resume 无新账本 |

正向账本：2 Reservation（各 `OK 0.001022`）/ 2 Claim `COMPLETED` / 2 Attempt `SETTLED` /
2 Receipt / Fake 2；committed=spent=`0.002044`、reserved=0、pending=0；两套
call_id/attempt_id/reservation_id/receipt_id 互不相同。usage 两请求均为
`{cacheRead:2, cacheWrite:0, input:11, output:5, reasoning:0, total:18}`，Broker
`input_used=13 / output_used=5`，与 Fake receipt 字段级相等。

独立审计（`scripts/g4/audit_g4_f4.py`，不导入产品代码）：resume **19/19**、
crash-resume **12/12** 全 PASS，包括 `old_attempt_unchanged_after_resume`、
`old_reservation_unchanged`、`old_receipt_unchanged`、`no_second_settlement`。
审计 UTC 14:57:05→14:57:06，exit 0。

### 3.2 F2 工具面与辅助请求（`artifacts/g4f/f6/integration/f2/`）

命令：

```text
python3 -B tests/integration/g4_f2/run_f2_evidence.py \
  --stage artifacts/g4/c/stages/stage-20261119T142828Z \
  --out-dir artifacts/g4f/f6/integration/f2
```

| 项 | 结果 |
|---|---|
| Echo（14:33:25→32，exit 0） | admissions=1 attempts=1 claims=1 intents=1 receipts=1 **fake=1**；journal 1 条 `completed`；tool `skill_lookup` schema==approved `c984bef0…`；origin uid/gid 65534 pid 0 |
| Tool 两轮（14:33:32→39，exit 0） | **2/2/2/2/2**，两套 call_id/reservation_id 不同；journal 2 条 `completed` |
| raw-UDS（14:33:39→54，exit 0） | 7 负例全 `ADMISSION_TOOL_SCHEMA_MISMATCH`（含 message tool-call/addition/removal）；负例账本 **0/0/0**、Fake 0；1 正例 1/1/1、Fake 1；2 个 title 请求 `BAD_TYPE` 且账本/journal 零增量 |
| adapter purpose probe | title → `G3B_BRIDGE_PURPOSE`；conversation → `G3B_BRIDGE_CONNECT_FAILED`（guard 在 socket 之前） |
| 辅助请求判定 | **`NO_EXTRA_PROVIDER_REQUEST_OBSERVED`**；3 dispatch = 3 assistant = 3 Receipt = Fake 3；`session/title` 2 次均为 `source.kind=fallback` |

### 3.3 F3 费用权威（`artifacts/g4f/f6/integration/f3-host/`、`f3-l2/`）

Host（8/8，UTC 14:30:41→14:30:42，exit 0）：

| case | held（后） | known（后） | 说明 |
|---|---:|---:|---|
| `ok_usage` | 0 | 0.001022 | consume 时 held=0.001583，Broker OK 后释放 |
| `no_usage` | 0 | 0.001583 | 仅 Broker FAILED 释放；committed 不变 |
| `lost_ack_reconcile` | 0 | 0.001022 | 结算回复丢失时 held 保持，Broker OK 后释放 |
| `replay` | 0 | 0.001022 | 第二次 `ATTEMPT_ALREADY_STARTED`，无二次结算 |
| `broker_denial` | 0 | 0 | requests 0，Fake 0 |
| `crash_after_reserve` | 0.001228 | 0 | 新进程 reconcile PENDING=reserved |
| `crash_after_attempt` | 0.001228 | 0 | 同上，Fake 0 |
| `concurrent_authorize` | 0.005 | 0 | 5 允许 / 3 `HARD_BUDGET_CEILING_EXCEEDED`，5 个唯一 view |

L2（7/7 cases、**89/89 checks**，UTC 14:34:53→14:36:25，exit 0）：

| case | Fake | Reservation | Attempt | gate known/held |
|---|---:|---|---|---|
| `c01` | 1 | 1 OK `0.001022` | SETTLED | 0.001022 / 0 |
| `c02` | 2 | 2 OK（各 0.001022） | SETTLED | 0.002044 / 0 |
| `replay` | 1 | 1 OK | SETTLED | 0.001022 / 0；requests 1 |
| `crash-before-send` | 0 | 1 PENDING `0.001619` | UNCERTAIN | 0 / **0.001619** |
| `crash-after-receive` | 1 | 1 OK | SETTLED | 0.001022 / 0（recovery sends=0） |
| `quota` | 1 | 1 OK | SETTLED | 0.001022 / 0；无第二次 reserve |
| `broker-down` | 0 | 0 | — | 0 / 0 |

### 3.4 F5 撤销/超时/在途失败（`artifacts/g4f/f6/integration/f5/`）

命令：

```text
python3 -B scripts/g4/run_g4_f5.py --stage artifacts/g4/c/stages/stage-20261119T142828Z \
  --out-dir artifacts/g4f/f6/integration/f5
```

结果：**13/13 cases、162/162 checks、exit 0**；UTC 14:30:24→14:33:03。
逐案（distilled `matrix.json`）：

| case | Fake | Broker | Attempt | held / known |
|---|---:|---|---|---|
| `revocation-pre-reserve` | 0 | 0 | — | 0 / 0；dispatch `rejected` |
| `revocation-post-reserve` | 0 | 1 PENDING `0.002684` | UNCERTAIN | **0.002684 / 0** |
| `revocation-in-flight` | 1 | 1 OK `0.001022` | SETTLED | 0 / **0.001022** |
| `timeout-pre-send` | 0 | 0 | — | 0 / 0 |
| `timeout-post-send` | 1 | 1 PENDING `0.002698` | UNCERTAIN | **0.002698 / 0** |
| `crash-after-authorize` | 0 | 1 PENDING `0.002684` | UNCERTAIN | **0.002684 / 0** |
| `crash-after-consume` | 0 | 1 PENDING `0.002684` | UNCERTAIN | **0.002684 / 0** |
| `crash-before-send` | 0 | 1 PENDING `0.001619` | UNCERTAIN | **0.001619 / 0** |
| `crash-after-receive` | 1 | 1 OK `0.001022` | SETTLED | 0 / **0.001022** |
| `revocation-post-reserve-hold` | 0 | 1 PENDING `0.001619` | UNCERTAIN | **0.001619 / 0**；第二请求 rejected |
| `revocation-in-flight-hold` | 1 | 1 OK `0.001022` | SETTLED | 0 / **0.001022**；第二请求 rejected |
| `crash-after-authorize-hold` | 0 | 1 PENDING `0.001619` | UNCERTAIN | **0.001619 / 0** |
| `crash-after-consume-hold` | 0 | 1 PENDING `0.001619` | UNCERTAIN | **0.001619 / 0** |

所有 case 的 `containers_after=[]`；恢复进程均以 `ADMISSION_REPLAYED` exit 3。
可停止 vs 保守分类与 `docs/M0_G4F_F5_REPORT.md` §6 完全一致。

---

## 4. 集成回归：定位、修复与 RED→GREEN

### 4.1 发现（RED）

在最终 HEAD `95ae99a` 上首次运行 F4 resume 时，两个 phase 均在
`F4Launcher` 构造阶段失败（evidence 保留在
`artifacts/g4f/f6/integration/f4-regression-before-fix/`）：

```text
AttributeError: 'Namespace' object has no attribute 'test_delay_hook'
  (scripts/g4/launch_c.py:107, G4CLauncher.__init__)
AttributeError: 'Namespace' object has no attribute 'deadline_ms'
  (scripts/g4/launch_c.py:280, write_configs)
```

**根因**：F5 在 `launch_c.G4CLauncher` 中新增了 5 个 argv 属性（`test_delay_hook`、
`test_delay_ms`、`revocation`、`pre_revoke`、`watch_revocation`）与 `deadline_ms`
覆盖，但 F2/F4 的 runner 各自构造 `argparse.Namespace` 子集；F5 fix 提交 `c804bb8`
引入的 deadline override 让 F4/F2 raw-UDS 在**同一 HEAD**上不可运行。这是真实集成
回归（不是 evidence-only），且此前 F4/F2 的旧证据绑定旧 HEAD，未暴露。

### 4.2 修复（GREEN）

- `scripts/g4/launch_c.py`：六个可选 argv 用 `getattr(..., default)` 读取；
  CLI 解析路径行为不变（F5 runner 仍显式传参），旧 Namespace 恢复 pre-F5 语义。
- `tests/integration/g4_f2/run_f2_evidence.py`：新增 `--out-dir`（默认
  `artifacts/g4f/f2` 不变），避免 F6 证据覆盖 F2 历史证据。
- 未删除/修改任何测试断言，未改 F5 判定或 checkpoint；未改 `src/`。

修复提交 `e7d9296`。修复后最终 HEAD 重跑：F4 两 phase 全 PASS（38+22 checks）、
F2 raw-UDS 全 PASS、F5 13/13、F3 7/7。RED/GREEN 日志均在
`artifacts/g4f/f6/integration/f4-regression-before-fix/` 与 `prefix-95ae99a/`。

---

## 5. 矩阵统计

`docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv`：
**46 行**。

| 状态 | 行数 | 说明 |
|---|---:|---|
| PASS | **38** | F1 5、F2 7（B03 行除外）、F3 8、F4 5（F4-06 除外）、F5 8、F6 5 |
| UNVERIFIED | **2** | `F2-08`（B03/E5-P04 registry）、`F4-06`（字节级 context replay） |
| NOT_RUN | **5** | `REV-01..05`（独立 Reviewer 行，未执行） |
| BLOCKED | **1** | `E5-FULL`（`BLOCKED_PENDING_HUMAN_DEPLOYMENT`） |

矩阵不伪造：Reviewer 行与 E5 Full 行没有 PASS；F2/F4 的不可证项明确 UNVERIFIED。

---

## 6. 全量回归实际计数

### 6.1 Host full（`pytest tests -q`，Python 3.11.15 + deps）

```text
collected 1357 = 1352 passed / 4 failed / 1 skipped   (exit 1)
```

| # | 失败项 | 归因 | 证据 |
|---|---|---|---|
| 1 | `g3d::test_runner_does_not_modify_product_src` | **frozen-src 断言**：`git diff 4bd4803 -- src` 非空（G4 授权改码），历史测试按约定不修 | `REVIEW_G4_INDEPENDENT.md` C-R6 |
| 2 | `g4_d::test_d15_same_uid_known_path_is_denied_by_mode_not_name` | **host-only 环境**：降权子进程无法穿越 0700 的 `/root/.local` | F2/F3/F5 报告同项 |
| 3 | `runtime::test_required_files_exist_and_are_read_only_text` | **host checkout mode**：工作树 0644，OCI stage 为 0444 | G4-E 已知 host-only |
| 4 | `sandbox::test_all_live_entrypoints_remain_blocked` | **host-only 子进程 PYTHONPATH**：硬编码 `/project/src:/deps` | G4-E 已知 host-only |

skipped 1：`sandbox/test_probe_contract.py::test_actual_os_negative_probe`（需要真实
外部 OS 负例环境）。4 项均非本轮产品回归，未做 deselect 隐藏；OCI/独立 probe 覆盖其中 3 项。

各套件（collect-only 复核）：g4_a 223、g4_b 38、g4_c 78、g4_d 26、g4_f2 30、g4_f3 23、
g4_f5 12、g3c 110、g3d 144、g3_bridge 31。

### 6.2 固定 OCI（rootfs `25491e45…`、deps `e07729d7…`，`--network none --read-only --cap-drop ALL`）

| 运行 | 结果 |
|---|---|
| raw（uid 65534，ignore g4_a + test_authorization） | 1087 selected = **1018 passed / 26 skipped / 43 failed**；43 项全部为环境类，逐项分类 |
| filtered（uid 65534，43 显式 deselect） | 1044 = **1018 passed / 26 skipped / 43 deselected / 0 failed**，exit 0 |
| root replay（uid 0） | **351 passed / 8 deselected / 0 failed** |

43 项 deselect 分类（`artifacts/g4f/f6/integration/oci/oci-env-deselects.json`）：

| 类别 | 数量 | 原因 |
|---|---:|---|
| `candidate_uid_owned_trusted_dir_requires_root` | 12 | 可信目录须 root 所有；uid 65534 无法构造 |
| `missing_git_in_rootfs` | 14 | rootfs 无 git（frozen tree/字节比较） |
| `host_root_uid_peercred_assumption` | 4 | 测试断言 host uid 0 的 peer 身份 |
| `relative_deps_pythonpath_in_crash_child` | 4 | crash child 用相对 `PYTHONPATH=src:artifacts/foundation/deps`，固定 OCI 布局中 deps 在 `/deps` |
| `frozen_stage_absent_from_oci_project_tree` | 3 | 测试读取 `artifacts/` 下的冻结 stage manifest |
| `missing_sh_or_bash_in_rootfs` | 3 | rootfs 无 `/bin/sh`/`bash` |
| `missing_tar_in_rootfs` | 3 | rootfs 无 tar |
| **合计** | **43** | 显式清单包含 `test_digest_sidecar_contract`（不重演 30/34 不一致） |

OCI 环境说明（如实记录）：podman `--rootfs` 会在共享 rootfs 内创建 `/var/tmp` 与挂载点
目录（如 `/evidence`），导致 tree hash 短暂漂移；每批运行后已清理并复核
`25491e45…` canonical。一次 OCI 与 host full 并发时，
`g4_b::test_real_anchor_is_the_frozen_baseline` 观测到 rootfs 漂移而失败；清理后
干净重跑通过（该失败不计入最终 host 结果，最终 host 结果为无并发下的 §6.1）。

### 6.3 Node（固定 rootfs，真实 TAP）

| 套件 | 结果 |
|---|---|
| adapter `adapter-signal.test.mjs` | **9 pass / 0 fail** |
| guard `guard-pr1.test.mjs` + `precheck.test.mjs` | **19 pass / 0 fail** |
| skill `plugin.test.mjs` | **8 pass / 0 fail** |
| 合计 | **36 pass / 0 fail** |

### 6.4 Ruff

- pinned `artifacts/foundation/deps/bin/ruff` **0.17.5**。
- G4-E 口径 scoped（`src/autoteacher_m0` + `tests/integration/g4_a..f5` + `scripts/g4`）：
  **All checks passed**。
- 追加 `tests/security` 后：**1 finding**（`F841`，`tests/security/test_scan_git_secrets.py:169`
  的未使用 `material`；F1 引入，非本轮改动，不影响断言）。
- repo-wide：**38 findings** = 37 既有（`spikes/`、`scripts/g3b`、`scripts/g3c`）+ 上述 1 项；
  `src/` 0 findings。

### 6.5 Secret scanner

| 命令 | 结果 |
|---|---|
| `--self-test` | PASS |
| 全历史 + 工作树 + commit messages | `scanned_files=467 scanned_blobs=739 scanned_commits=165 findings=0` |
| `tests/security`（7 tests） | **7 passed** |

### 6.6 0-Key / LiveGate / CLI / Adapter / run_live 负例

| 检查 | 结果 |
|---|---|
| `LiveGate.inspect(live_requested=True, all evidence)` | `status=BLOCKED`，reasons 4 项不变 |
| `LiveGate.require_live()` | raises `SecurityBlocked` |
| `/bin/sh scripts/run_live.sh` | exit **3** |
| CLI `smoke --live` | exit **3** |
| `AT_M0_LIVE_APPROVED` / `AT_M0_ALLOW_LIVE` / `AT_M0_APPROVAL` / `AT_M0_APPROVAL_MD` / fake `DEEPSEEK_API_KEY` | 全部 exit **3** |
| adapter `_require_live_authorization` | raises `SECURITY_BLOCKED` |
| 外部 socket 尝试 | **0**（GuardedSocket 记录 `external_socket_attempts=[]`） |
| key-like env | **0** |

证据：`artifacts/g4f/f6/integration/livegate/livegate.json`。

---

## 7. E5 两列

| 项 | NO_KEY_SUBSET | FULL_STATUS |
|---|---|---|
| E5-P01 | PASS（G4-D/F4 真实容器子集） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-P02 | PASS（外部 watchdog absence） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-P03 | PASS（synthetic 撤销） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-P04 | **UNVERIFIED**（无可导出 merged registry） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| E5-P05 | PASS（0-Key 负例） | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` |

`E5-FULL` 在矩阵中单列一行：`BLOCKED`。

---

## 8. 残余与 UNVERIFIED（摘要）

完整清单见 `docs/M0_G4F_FINDINGS_AND_DISPOSITION.md`。

- **B03 / E5-P04**：DSH `0.2.2-rc.2` 无权威 merged registry 导出 → 维持 `UNVERIFIED`。
- **B07**：冻结配置下 session-title fallback-only、无额外 provider 请求；任意未来配置/
  动态注册不能证明。
- **F4**：context replay 是语义证据（session JSONL + payload length/digest），非字节包含；
  Candidate crash + live Controller 子场景 `UNVERIFIED`。
- **F5**：撤销文档无签名；外部 SIGKILL 的纳秒级窗口未枚举；真实 Provider 撤销/计费不在范围。
- **F3**：L2 unknown-cost 仅覆盖 crash→PENDING；视图为 process-local。
- **本环境**：OCI 无 git/tar/sh 与 root capabilities（43 项显式环境 deselect，host 覆盖）；
  podman `--rootfs` 会创建挂载点目录，须清理后复核 canonical。
- **F2/F5 同批 flake**：6 次批处理 + 全量 host 均未复现（详见 findings F6-04）。

---

## 9. 明确非主张

本报告**不**主张：G4 Full PASS、E5-PreLive Full、真实 Provider/计费/额度、真实人类
Ed25519 信任根部署、G4-H 通过、G5/G6 启动、Live 授权、`M0_GO`。所有结论限定于
synthetic、no-key、单机冻结环境。

---

## 10. 证据索引（`artifacts/g4f/f6/integration/`）

| 路径 | 内容 |
|---|---|
| `SUMMARY.json` | 本轮汇总（身份、stage、各包结果、host/OCI/Node/Ruff/scanner、commands） |
| `commands.jsonl` | 每条命令 argv/UTC/exit/log |
| `f4-resume/` | F4 最终 HEAD 两 phase + 独立审计 + loaded-modules + 预修复 RED 日志 |
| `f2/` | Echo/Tool/raw-UDS/adapter + summary/tool-window |
| `f3-host/`、`f3-l2/` | F3 host 8 case 与 L2 7 case 证据 |
| `f5/` | 13 case 证据 + `matrix.json`（distilled） |
| `host/` | host full 日志 + JUnit |
| `oci/` | OCI raw/filtered/root replay 日志、JUnit、43 项 deselect 清单 |
| `node/` | adapter/guard/skill TAP 日志 |
| `ruff/`、`scanner/`、`livegate/` | 静态、扫描器与 LiveGate 负例 |
| `oci-stage/` | OCI 用 `git archive HEAD` 冻结副本（7.6 MB，不含 node_modules） |

---

## 11. Review Packet

`artifacts/review-packet-g4f-e7d92967ec0e/`（`schema_version=m0.g4f.review-packet.v1`；
`base_sha=bb2e914`、`impl_sha=e7d9296`、`code_sha=dbacb76`、`docs_sha`=本 docs 提交、
`build_sha`=Packet 构建时 HEAD；`provider_route_kind=synthetic_only`、`key_present=false`、
`real_model_calls=0`、`real_external_http_calls=0`、`live_gate=BLOCKED`、
`reviewer=NOT_ASSIGNED`、`previous_review=G4 PASS`）。 Packet 由
`scripts/g4/build_packet_g4f.py` 构建：只读工作树与证据，不启动容器/网络，不读 Key；
`hashes.sha256` 覆盖全部 payload + manifest，`packet-integrity-report.txt` 记录
`sha256sum -c`、payload tree 复算、文件计数与 0 symlink。

---

## 12. 提交与 STOP

- 本文件与 `docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv`、
  `docs/M0_G4F_FINDINGS_AND_DISPOSITION.md`、`docs/M0_G4F_REVIEW_REQUEST.md`、
  `docs/M0_G4F_HUMAN_HANDOFF.md` 同一 docs 提交归档。
- Packet builder 以独立 chore 提交归档；未 amend / 未 push / 未改动他人文件。
- 终态：`podman ps -a` 空；rootfs/deps canonical；0 Key / 0 模型 / 0 外网 / 0 Live。

```text
G4-F6 = PASS_FOR_NO_KEY_CLOSEOUT_SCOPE (candidate)
STOP: 不进入 G4-H / G5 / G6；不签发 Live 授权；不执行独立复核。
```
