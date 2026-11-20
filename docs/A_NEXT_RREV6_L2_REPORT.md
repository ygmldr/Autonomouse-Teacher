# A-NEXT A-PR3 — R-REV6 真实双 Principal / DSH Fake-only L2 报告

- **阶段**：A-NEXT / A-PR3（R-REV6 独立 L2 复跑；此前 R-REV6 = `NOT_RUN`）
- **Owner**：`a-g4r-recovery`（Implementer-Test），非 Lead；独立审阅另由 Reviewer 完成。
- **工作树 / 分支**：`/root/Autonomous Teacher/worktrees/a-next-rrev6` / `test/a-next-rrev6`
- **基线**：`work/g4r` = `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`（canonical 候选；最终实现冻结 SHA `d33e0aa`）
- **依据**：`/root/handoffs/AT_LeadA_G4R_Next/01_LEADA_AGENT_HANDOFF.md` A4、`AUDIT_REQUESTS.md` A-Q1/A-Q2
- **性质**：no-key / no-model / Fake-only / `--network none` / 0 外部 HTTP(TCP) / 0 真实计费；
  LiveGate=`BLOCKED`、G4-H=`NOT_AUTHORIZED`、G5=`BLOCKED`、M0=`DECISION_PENDING`（本轮不改变）。
- **当前状态**：`L2_W1_EXECUTED_OWNER_EVIDENCE`（Lead 批准的独占窗口 2026-11-20T20:00–20:50Z 内完成；
  实际批次 20:20:39–20:24:06Z）。13 个 case（+ 1 个字节级 replay 子 case R6-04B）全部有真实容器证据，
  Owner 审计 14/14 PASS；**这是 Implementer/Owner 证据，不是 Reviewer 独立复跑**，R-REV6 是否 PASS
  仍以独立 Reviewer 自行复跑为准。

```text
A-PR3 / R-REV6: NOT_RUN -> 准备完成，等待 Lead 批准 30 分钟独占 OCI 窗口
证据等级目标: L2-REAL-DSH-FAKE（真实 Stage/rootfs 工作副本/真实 DSH/真实本地 Broker+Fake/双 principal）
```

---

## 1. 环境自检结果（只读，2026-11-20T19:49Z）

机器可读原始记录（gitignored）：`artifacts/a_next/rrev6/prep/env-check-20261120T194901Z.json`。
自检脚本：`scripts/a_next/rrev6/env_check.py`（只读；`--copy-test` 仅做 /tmp 副本哈希验证；
`--stage-artifacts` 把冻结输入复制到本工作树 gitignored `artifacts/`）。

| 项 | 实测 | 判定 |
|---|---|---|
| 工作树 HEAD / 分支 | `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af` / `test/a-next-rrev6` | 与任务基线一致 |
| 主机 main SHA | `3e7afee077845a071cd364e93ab209cac20b2d5f` | 只读引用 |
| podman | `podman version 4.9.3`；`podman ps -a` 容器 0；本地镜像 4（未 pull） | 可用、窗口前干净 |
| host Node / frozen rootfs Node | `v22.23.2` / `v22.23.2`（`sha256 3517c2df…`，容器外 `--version` 可执行） | 版本一致 |
| DSH SDK | `deepseek_harness_sdk 0.2.2rc2`（显示 `0.2.2-rc.2`），runtime package `0.2.2rc2` | 与冻结口径一致 |
| DSH runtime binary | `sha256 1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4` | canonical |
| frozen rootfs（main 只读源） | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（275.3 MiB，hash 0.77 s） | **canonical** |
| frozen deps（main 只读源） | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（222.4 MiB，hash 0.54 s） | **canonical** |
| rootfs 可写副本程序验证 | `/tmp` 复制 288,723,429 B，0.76 s，副本 `tar --sort=name` 哈希 == frozen == canonical；复制前后 frozen 哈希一致，副本已删除 | **可用**（禁止直接 `--rootfs <frozen>` 的方案成立） |
| Stage 构建前置输入（main 只读源） | G3-A stage 134M、G3-C stage 135M、`plugins/offline-fixture/node_modules` 40M、adapter 期望 JS `2cb42461…` | 全部存在 |
| 本工作树 staged 冻结输入 | 751.3 MiB 已复制到 `artifacts/{security/rootfs,foundation/deps,g3a-provider-bridge/stage,g3c/stage}` + `plugins/offline-fixture/node_modules`；staged rootfs/deps 重算哈希均 canonical | 自包含，不依赖其它 worktree 可写路径 |
| 磁盘 | staging 后空闲 5.0 GiB；窗口峰值预算 ≈ 1.4 GiB（Stage 输出 + 单 case rootfs 工作副本 + 证据） | 余量 ≈3.6 GiB，足够 |
| 已有容器/镜像 | 0 容器；无 pull | 满足独占窗口前置 |
| 历史 L2 证据 | 仅 main `artifacts/g4f/{f2,f5}` 旧 Stage/base SHA 数据（F5 13 case 实测 158 s 属历史参考） | **只作时长参考，绝不复用为 R-REV6 证据** |
| adapter 既有 build-meta | main 的 `artifacts/g4/c/build` 无现成 build-meta | 窗口内由 Stage 构建重新生成并与期望 JS 哈希比对 |
| **环境事件（Lead 通报，2026-11-20T19:53Z）** | Lead 清理 /tmp 陈旧 bind mount 时误删主仓库 gitignored `artifacts/`；已从 `/tmp/at-g4f-review` 与各 worktree 副本恢复。本工作树在删除前（19:49Z）已复制并哈希验证的 `artifacts/{security/rootfs,foundation/deps,g3c/stage,g3a-provider-bridge/stage}` 与 `plugins/offline-fixture/node_modules` 是恢复来源之一，已保留 | 恢复后主仓库 rootfs/deps 复算仍为 canonical（本报告写作前再次验证）；**A4 证据必须记录“rootfs 恢复自经哈希验证的副本、恢复后复算 25491e45…”**；不得写“全程 NO_DRIFT” |

---

## 2. 冻结保护与 Stage / rootfs 使用协议（窗口强制）

1. **冻结源只读**：`/root/Autonomous Teacher/artifacts/security/rootfs` 与
   `artifacts/foundation/deps` 全程只读（仅 `tar|sha256` 识别与一次性复制）。**永不**作为
   `podman --rootfs` 目标。
2. **本工作树 staged 副本**：上述冻结源复制到本工作树 `artifacts/` 与
   `plugins/offline-fixture/node_modules`（gitignored），复制后重算 canonical 哈希校验；
   后续 Stage 构建与容器只使用本工作树副本。
3. **每 case 独立可写 rootfs**：从 staged canonical rootfs `shutil.copytree` 生成
   `artifacts/a_next/rrev6/<run>/rootfs-work/<case>/`，记录副本哈希，case 结束删除；
   `podman --rootfs` 只指向该工作副本。
4. **Stage 重建**：窗口内用当前 run HEAD 重新 `scripts/g4/build_stage_c.py`（进程内把
   `lib_g3d.ROOTFS` 重绑到工作副本，adapter build 容器也必须使用工作副本），
   `validate_stage_g4(base_sha=run HEAD, verify_git=True)` 通过后才允许跑 case；
   **不复用** `stage-2026111*` 任何旧 Stage 字节。
5. **T0/T1 门**：窗口开始记录 frozen rootfs/deps canonical 哈希（T0）；窗口结束重算并
   与 T0 比对，任何漂移 → **STOP**，保留证据并上报。同时记录 staged 副本、work copy、
   Stage manifest/tree 哈希。
6. **单写者/独占**：同一时刻只允许本批 L2；runner 启动前要求 `podman ps -a` 空、
   证据目录不存在、`git status --porcelain` 干净、frozen canonical；结束要求
   `containers_after=[]`。

---

## 2.1 环境事件后的身份对齐（重要）

- 本工作树 staged 副本：rootfs `25491e45…`、deps `e07729d7…`（19:49Z 从主仓库复制时校验，
  20:00Z 前后再次复算一致）；主仓库恢复后同值。
- **Stage 身份**：G4-R Packet 记录的旧 Stage 是主仓库
  `artifacts/g4/c/stages/stage-20261120T165407Z`（base_sha=`d33e0aa…`，manifest
  `cc7ccb61bc4df76675b14e1f73bdd9209d3a13eeda7e79193e913ea284874d03`，tree
  `933f2c07a6c79415183a4d3f1db1ba19249b95d96ee88334bd43e71dd40d3882`，trusted 60 /
  candidate 6549 files，adapter build `adapter-20261120T165408Z`，rootfs canonical）。
  该 Stage 的 base 是 `d33e0aa` 而本任务 HEAD 是 `fd1d3a6`，G4-C launcher 要求
  `stage.base_sha == HEAD`，**因此不能拿它作为本次 run 身份**；它在窗口期间**只读保留**，
  仅作历史对照，不当证据。
- **窗口内将重建新 Stage**：run HEAD `fd1d3a6`（src 与冻结实现 `d33e0aa` 相同，test/tooling-only
  delta），Stage 输出到本工作树 `artifacts/g4/c/stages/stage-<utc>/`；构建时进程内把
  `lib_g3d.ROOTFS` 重绑到工作副本，adapter build 也使用工作副本。构建后记录新的
  manifest/tree/trusted/candidate SHA，并在证据中与旧 Stage 明确区分。

---

## 3. 执行矩阵（13 case；设计已完成，尚未执行）

机器可读矩阵：`scripts/a_next/rrev6/case_matrix.json`
（host 合同测试：`tests/a_next_rrev6/test_prep_contract.py`，10 passed，不启容器/不联网）。

| case | 目标（A4 映射） | 注入手段 | 稳定性 |
|---|---|---|---|
| R6-01 | 真实 DSH **Echo(1)**：1 dispatch/receipt/settlement + digest join | 无（真实 DSH 正常路径） | STABLE |
| R6-02 | 真实 DSH **Tool(2)**：同一 run 两次合法 dispatch 均接受 | 无（approved `skill_lookup` schema） | STABLE |
| R6-03 | 真实 DSH **Resume two-turn**：turn1 echo + turn2 `resume_session` 同一 session store | 无（candidate_entry resume 路径） | STABLE |
| R6-04 | **同一 business request 重放**：拒绝且 0 新 dispatch/Fake/settlement | 无（同 session+prompt identity 重放） | STABLE |
| R6-05 | **pre-Reserve timeout**：请求层拒绝，0 Reserve/Fake，不伪造 dispatch | 既有 test-only delay hook `before_reserve` 2500ms + deadline 800ms | STABLE |
| R6-06 | **post-Reserve revoke**：0 Fake、PENDING/held、恢复后 first cause 保留 | 既有 revocation 文档 + `after_reserve_before_send` 钩子 + trusted restart | STABLE |
| R6-07 | **post-send timeout**：Fake=1/receipt=1、PENDING/held、不重发 | Fake stall fixture + deadline | STABLE |
| R6-08 | **Controller crash**（hook `after_attempt_start_before_fake_send`）+ 恢复 + replay no-op | 既有 crash hook（env gated `os._exit`） | STABLE |
| R6-09 | **Controller 硬停 / socket lost**（SIGKILL 片段，非仅 hook） | host `podman kill` trusted at delay marker + 恢复 | CONDITIONAL（无 src hook；test-side 注入） |
| R6-10 | **Candidate crash 而 Controller 存活**：不重复 dispatch、held 保守 | host `podman kill` candidate at delay marker；deadline 800ms 变体 | CONDITIONAL（test-side 注入，需窗口内先 dry-check 时序） |
| R6-11 | **Fake crash**：SETTLEMENT_UNCERTAIN/held，恢复不双结算 | 容器内 `/proc` SIGKILL `fake_provider.py`（test-side） | CONDITIONAL（需先验证 Fake 子进程 cmdline/时序） |
| R6-12 | **Broker down/restart**：Reservation 守恒、PENDING held、0 settle | 既有 `kill-broker` + trusted restart（同一 Broker DB） | STABLE |
| R6-13 | **usage/hash 独立对账**（对 R6-01..12 只读快照） | 无（纯审计） | STABLE |

**Digest 绑定（分开断言，绝不混同）**：
`prepared_digest == claim.request_digest`；`payload_digest == receipt.raw_sha256`；
`prepared_digest != payload_digest`（二者构造上不同，不得断言相等）。
另验：`fake_counter == receipt 数`、`ATTEMPT_STARTED` 后未知发送保留 `PENDING/SETTLEMENT_UNCERTAIN`
且 held>0、Broker 已证终态（OK/FAILED）优先且每 reservation 至多一次 settle/fail、同 business
identity 重放 0 新 Attempt/Reservation/Fake。

### 3.1 无法注入 / 不做的项（预判，最终以实测为准）

| ID | 项 | 原因 |
|---|---|---|
| R6-NR1 | 真实 Provider/API/计费 usage | no-key 禁止；本轮不触碰 |
| R6-NR2 | 权威 Runtime tool-registry 快照 | A-PR2/R3 范围；B03/E5-P04 仍 `UNVERIFIED`，本任务不声称 |
| R6-NR3 | 穷举外部 SIGKILL/断电纳秒窗口 | 无可控 hook；仅跑列出的确定性窗口，F5-R6 限制保留 |
| R6-NR4 | Controller 重启后同一 DSH session 的 resume 语义 | admission 单次消费设计使重启进程 `ADMISSION_REPLAYED` 退出；需新 Run admission（A-PR1），本轮不声称 |
| R6-NR5 | 真实跨机/跨主机隔离 | 单 PVE 主机环境限制，如实记录 |
| R6-NR6 | Candidate crash 后“正在写的 Fake 是否发出”的纳秒级判定 | 只有 test-only delay 窗口；按实际 ledger 归类，不外推 |

---

## 4. 独占 OCI 窗口申请

**申请窗口时长：30 分钟**（预计实际 12 分钟，余量用于一次 case 重试或 Stage 重建）。
前提：Lead 批准且确认该时段没有其它 L2 batch 运行；窗口内 `git HEAD` 冻结（任何 commit
都会使 Stage base SHA 失效，需重建）。

窗口步骤与预算：

| # | 步骤 | 预计 |
|---|---|---|
| 1 | T0 门：frozen rootfs/deps canonical 哈希、git clean、容器空、磁盘 ≥2.5 GiB | ~30 s |
| 2 | staged rootfs 工作副本 + Stage 重建（adapter build 容器，使用工作副本）+ `validate_stage_g4` | 2–3 min |
| 3 | R6-01..R6-13 顺序执行（每 case 新 rootfs 工作副本、新证据目录、case 间容器必须空） | 6–8 min |
| 4 | T1 门：frozen 哈希与 T0 相等、stage manifest/tree、containers_after=[]、证据 sha256 清单 | 1–2 min |
| 5 | 证据冻结（只读副本）+ 报告追加实测行 | 2 min |

**中止条件（任一触发即 STOP、保留证据、上报 Lead）**：
frozen rootfs/deps 哈希漂移；真实 Key/HTTP(TCP)/Provider 调用；未批准工具进入 Fake/Provider；
双 Reserve/Claim/Settlement/Fake；PENDING 被释放为 FREE；容器清理残留；证据目录已存在/写失败。

窗口批准后，本文件 §5 追加逐 case 实测（命令、UTC、exit、Stage/Runtime/rootfs SHA、
uid_map/peercred、原始 JSONL/DB 路径、checks、限制），并单独提交
`run_l2_matrix.py` / `evidence_audit.py` / 证据索引；**不 push**。

---

## 4.1 窗口命令清单（草稿，批准后执行；全部在 worktree 内、不 push）

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-rrev6"
# 0) 前置：git clean、podman ps -a 空、frozen T0
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/env_check.py --copy-test

# 1) 重建 Stage（进程内 rootfs 重绑到工作副本；adapter build 只用工作副本）
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/build_stage.py --base HEAD

# 2) 执行矩阵（单写者；每 case 新 rootfs 工作副本 + 新证据目录）
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/run_l2_matrix.py \
  --stage artifacts/g4/c/stages/stage-<utc> --out artifacts/a_next/rrev6/l2/<run-id>

# 3) 事后审计 + T1 门 + 证据索引（只读副本）
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/evidence_audit.py \
  --run artifacts/a_next/rrev6/l2/<run-id>
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/env_check.py --copy-test

# 4) 本地提交（不 push）
git add tests/a_next_rrev6 scripts/a_next/rrev6 docs/A_NEXT_RREV6_L2_REPORT.md
git commit -m "test: A-PR3 R-REV6 real DSH Fake-only L2 evidence (no-key)"
```

未提交到窗口前的实现项：`build_stage.py`（rootfs 工作副本包装器）、`run_l2_matrix.py`、
`evidence_audit.py`（含 digest 绑定与 ledger 对账）；窗口批准后先提交这些脚本再开跑，
保证 Stage base SHA 与 git HEAD 对齐。

## 5. 窗口实测结果（Owner 证据，2026-11-20T20:20:39–20:24:06Z）

### 5.1 批次身份与冻结门

| 项 | 值 |
|---|---|
| 窗口 | Lead 批准 2026-11-20T20:00:00–20:50:00Z；实际批次 **20:20:39Z → 20:24:06Z**（单写者，唯一 L2 批次） |
| run HEAD（仓库） | `d083c54e023ca58124b3424d4de19caa972ba5da`（`test/a-next-rrev6`，在基线 `fd1d3a6` 之上仅 test/scripts/docs 变更；`src/` 与冻结实现 `d33e0aa` 相同） |
| 新 Stage | `/root/Autonomous Teacher/worktrees/a-next-rrev6/artifacts/g4/c/stages/stage-20261120T202016Z` |
| Stage base_sha | `d083c54e023ca58124b3424d4de19caa972ba5da`（= run HEAD） |
| Stage manifest SHA-256 | `34b3db73f76743343bcb691a87f5feda1bb3bb3a08f232e41cdd953ce0c3ffc6` |
| Stage tree SHA-256 | `2b9edab82a25f3c4108a839041dc0e0239f89b72d69c4ae386e4f820c6a57401` |
| trusted tree / candidate tree | `dbf3ca368a7c41e487713eb4d8e4f7f79185ae05e36bf7ee698a89a6070de39c` / `b2c73100da2099ccae8d8df3e31ef472c9e40cbf9aff27c76a4f4486dbc36e4f` |
| Stage 文件数 | trusted 60 / candidate 6549；`validate_stage_g4(base_sha=HEAD, verify_git=True)` = ok |
| adapter build | `adapter-20261120T202017Z`，built JS `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba`，DSH LLM `0.2.2-rc.2` |
| DSH runtime | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`；SDK `0.2.2rc2`；Node `v22.23.2` |
| rootfs 使用方式 | 每 case 从 staged canonical rootfs 复制**独立工作副本**（副本哈希先验证 == canonical，case 后删除）；`podman --rootfs` 从未指向 frozen rootfs；adapter build 容器使用 stage-build 工作副本（`rootfs-stage-20261120T202015Z`，build 前后哈希均 `25491e45…`） |
| T0（20:20:39Z，写于 `t0.json`） | rootfs `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`；deps `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`；containers `[]` |
| T1（20:24:06Z，写于 `t1.json`；独立 `env_check --copy-test` 20:25:57Z 再验） | rootfs 同 T0、deps 同 T0；`rootfs_matches_t0=true`、`deps_matches_t0=true`；`podman ps -a` = **空**；copy-test 副本哈希 == canonical |
| rootfs provenance | rootfs/deps 来自 **2026-11-20T19:53Z 主仓库 artifacts 误删事件后、经哈希验证的恢复副本**（主仓库恢复后与 staged 副本均复算 `25491e45…` / `e07729d7…`）；**不声明“全程 NO_DRIFT”**；Batch 内 T0/T1 一致，但该事件的恢复事实必须在 A4 Evidence 中保留 |
| 0 调用声明 | 每 case `real_model_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`；Launcher env/network-probe 证据在 case `env/`、`network-probe/`；无 pull、无外部网络 |
| 容器残留 | 批后 `podman ps -a` 空；每 case `containers_after=[]` |
| 旧 Stage 关系 | 旧 G4-R Stage `stage-20261120T165407Z`（base=`d33e0aa`，manifest `cc7ccb61…`，tree `933f2c07…`）仅作历史参照，**未被本次任何 case 使用**；本次全部证据绑定新 Stage `stage-20261120T202016Z` |
| 证据根 | `artifacts/a_next/rrev6/l2/run-20261120T202039Z/`（gitignored）：`t0.json`、`t1.json`、`matrix.json`、`audit.json`、`evidence-index.json`（每 case 关键文件 sha256）、`cases/<case>-<stamp>/`、`logs/<case>.log` |

### 5.2 逐 case 结果（Owner audit；全部 exit=0）

| case | UTC | 关键观测（read-only DB/JSONL 复算） | 状态 |
|---|---|---|---|
| R6-01 Echo(1) | 20:20:44–20:20:54 | 1 completed dispatch、1 receipt、1 `SETTLED`、Broker `OK`、Fake=1；prepared/claim 与 payload/receipt 绑定通过 | PASS |
| R6-02 Tool(2) | 20:20:56–20:21:07 | 同一 run 2 个合法 dispatch（2 receipts、2 `SETTLED`、Broker 2×OK、Fake=2），**不同合法步骤未被误拒** | PASS |
| R6-03 Resume two-turn | 20:21:10–20:21:23 | turn1 echo + turn2 `resume_session`（resume marker=1，session 24 行）：2 dispatch/2 receipts/2 `SETTLED`/Fake=2；两次不同 business identity | PASS |
| R6-04 DSH 同 session 重放 | 20:21:25–20:21:37 | turn2 DSH 在 start_session 阶段被 SDK 拒绝（`session ... already exists`），第二个 provider 请求未到达 bridge：1 dispatch/1 receipt/1 `SETTLED`；**限制已记录**（见 §5.3），字节级 Controller replay 由 R6-04B 覆盖 | PASS（with limitation） |
| R6-04B 字节级重放（补充） | 20:21:40–20:21:58 | candidate hold + probe `valid` 后 `replay`（byte-identical，同 business identity）：completed 1 / **rejected 1**、仅 1 receipt、1 attempt、0 第二 reservation | PASS |
| R6-05 pre-Reserve timeout | 20:22:00–20:22:12 | 0 dispatch/0 reservation/0 attempt/0 Fake；request-lifecycle = `[received, controller_entered, deadline_before_controller]`（`stage=before_reserve`，`reserved=false`，`dispatch_seq` 真实存在） | PASS |
| R6-06 post-Reserve revoke | 20:22:14–20:22:32 | real DSH；revocation 在 after_reserve 窗口写入并 gate 复读：Fake=0、Broker `PENDING`、attempt `SETTLEMENT_UNCERTAIN` 且 reason 保留 `REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED`（恢复后仍保留，recovery diagnostic 独立记录）；无 settle/fail | PASS |
| R6-07 post-send timeout | 20:22:34–20:22:46 | Fake=1、receipt=1、Broker `PENDING`、attempt `SETTLEMENT_UNCERTAIN`；无重发、无第二次 receipt/settle | PASS |
| R6-08 Controller crash | 20:22:49–20:23:00 | crash hook `after_attempt_start_before_fake_send` + restart：attempt `SETTLEMENT_UNCERTAIN / NO_RECEIPT_AFTER_CRASH`、Broker `PENDING`、Fake=0；恢复后 replay no-op | PASS |
| R6-10 Candidate crash（Controller 存活） | 20:23:03–20:23:15 | candidate SIGKILL at after_reserve marker（deadline 800ms 触发 pre-send abort）：Broker `PENDING`、intent `RESERVED`、Fake=0、0 attempt；Controller 后仍完成结案与清理；**held>0，无 FREE/无重复 dispatch** | PASS |
| R6-09 Controller 硬停（SIGKILL） | 20:23:18–20:23:30 | host SIGKILL trusted at after_reserve marker：Broker `PENDING`、intent `HELD_UNCERTAIN`、Fake=0、0 attempt、0 dispatch 行（controller 未及写）；restart recovery 保守保留 held；**SIGKILL 落在 pre-attempt 窗口**（限制见 §5.3） | PASS（conservative） |
| R6-11 Fake crash | 20:23:32–20:23:43 | scenario=stream，Fake 写 receipt 后被杀：Fake=1、receipt=1、attempt `WORST_CASE_HELD / USAGE_NOT_AUTHORITATIVE`、Broker **`FAILED`（已证终态，权威）**、0 第二次结算；restart 不改写终态；不 FREE、不双计费 | PASS（conservative terminal） |
| R6-12 Broker down/restart | 20:23:45–20:24:02 | broker SIGKILL at after_reserve marker → Claim `CLAIM_DENIED`：Fake=0、Broker `PENDING`、intent `HELD_UNCERTAIN`、0 settle；restart 后 Broker 同 DB 恢复、reconcile 只读 PENDING，held 保持 | PASS |
| R6-13 usage/hash 对账（审计） | 20:24:03 | 跨 case 聚合：prepared/claim 绑定 join 11 行、payload/receipt 绑定 9 个 receipt，0 mismatch；`prepared_digest != payload_digest` 恒成立；fake counter == receipt 数；PENDING 未标 FREE；SETTLED 每 reservation 至多一次；全部 case `containers_after=[]`、0 real calls | PASS |

Owner audit 汇总（`audit.json`）：**PASS 14 / PARTIAL 0 / NOT_RUN 0 / total 14**；
每 case checks_total 13–15，checks_failed 全 0。

### 5.3 已知限制 / 无法注入项（如实记录）

1. **R6-04（DSH 层同 session 重放）**：真实 DSH SDK 对重复 `start_session` 在客户端即拒绝
   （`session "..." already exists`），第二个 provider 请求未到 bridge；因此该 case 只证明
   “DSH 层拒绝且无第二次发送”，Controller 身份级 replay 由 **R6-04B**（真实 candidate 容器 +
   真实 UDS，byte-identical probe replay）覆盖：第二请求 dispatch `rejected`、无第二 receipt。
2. **R6-09（Controller 硬停）**：SIGKILL 落在 test-only `after_reserve_before_send` 延迟窗口内，
   即 **pre-attempt** 窗口；因此观测为“0 attempt + PENDING + held”，不是“ATTEMPT_STARTED 后未知
   发送”。ATTEMPT_STARTED 后的崩溃窗口由 R6-08（hook，确定性）覆盖；**外部 SIGKILL 的纳秒级
   全窗口仍不穷举（F5-R6 限制保留）**。
3. **R6-11（Fake crash）**：Fake 在写出 receipt 后被杀，控制面对 partial stream 的既有策略是
   `Broker FAILED`（已证终态、无计费）+ `WORST_CASE_HELD` 保守归档；这是 Broker 权威终态优先，
   不是 FREE/held。若要求“Fake 崩溃后必须保持 PENDING”，需产品策略变更，本轮不改生产语义。
4. **未运行（NOT_RUN by design）**：真实 Provider/计费、Registry 权威快照（B03/E5-P04 仍
   UNVERIFIED）、穷举 SIGKILL/断电窗口、Controller 重启后同 DSH session 语义、跨机隔离。
5. **证据等级**：本文件与 `audit.json` 是 **Implementer/Owner 证据**（真实容器、真实 DSH、真实
   本地 Broker/Fake，L2-REAL-DSH-FAKE），**不是独立 Reviewer 复跑**；R-REV6 最终裁定需 Reviewer
   自建命令/自建反例复算，不得以本报告代替。
6. 窗口内前两次批次（`run-20261120T200727Z`、`run-20261120T201507Z`）为脚本修正前的
   superseded 运行，**不作为证据**；最终证据仅 `run-20261120T202039Z`。

### 5.4 复现命令（窗口内实际使用）

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-rrev6"
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/env_check.py --copy-test
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/build_stage.py
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/run_l2_matrix.py \
  --stage artifacts/g4/c/stages/stage-20261120T202016Z \
  --expected-head d083c54e023ca58124b3424d4de19caa972ba5da
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/a_next/rrev6/evidence_audit.py \
  --run artifacts/a_next/rrev6/l2/run-20261120T202039Z
```

窗口内使用 UTC：T0 `20:20:39Z`（t0.json）→ batch start `20:20:42Z` → batch end `20:24:06Z`
（t1.json）→ 独立 T1 env-check `20:25:57Z`。

## 6. 与旧证据 / 矩阵的关系

- 旧 Owner L2（Stage-20261120T165407Z 等）与 Packet 内计数均为**旧 Stage/旧 SHA** 产物：
  本报告只作历史引用与时长参考，**绝不复制/冒充**为本次 R-REV6 证据。
- 冻结 `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`、
  `docs/REVIEW_G4R_INDEPENDENT.md`、旧 Packet/Stage/JUnit 均不改字节（host 合同测试断言）。
- R-REV6 最终状态仍以独立 Reviewer 自己复跑结果为准；本报告是 Owner/Implementer 的
  原始证据与自检，不是 Reviewer 裁定，也不改变 `B03/E5-P04=UNVERIFIED`。
