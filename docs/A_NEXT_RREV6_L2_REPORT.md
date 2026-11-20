# A-NEXT A-PR3 — R-REV6 真实双 Principal / DSH Fake-only L2 报告

- **阶段**：A-NEXT / A-PR3（R-REV6 独立 L2 复跑；此前 R-REV6 = `NOT_RUN`）
- **Owner**：`a-g4r-recovery`（Implementer-Test），非 Lead；独立审阅另由 Reviewer 完成。
- **工作树 / 分支**：`/root/Autonomous Teacher/worktrees/a-next-rrev6` / `test/a-next-rrev6`
- **基线**：`work/g4r` = `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`（canonical 候选；最终实现冻结 SHA `d33e0aa`）
- **依据**：`/root/handoffs/AT_LeadA_G4R_Next/01_LEADA_AGENT_HANDOFF.md` A4、`AUDIT_REQUESTS.md` A-Q1/A-Q2
- **性质**：no-key / no-model / Fake-only / `--network none` / 0 外部 HTTP(TCP) / 0 真实计费；
  LiveGate=`BLOCKED`、G4-H=`NOT_AUTHORIZED`、G5=`BLOCKED`、M0=`DECISION_PENDING`（本轮不改变）。
- **当前状态**：`PREP_READY_AWAITING_OCI_WINDOW`。**尚未启动任何容器**；本文件先记录准备状态、
  执行矩阵与窗口申请，窗口批准后在同一文件**追加**逐 case 实测结果（append-only）。

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

## 5. 窗口实测结果（待 Lead 批准后 append-only 追加）

```text
STATUS = PENDING_OCI_WINDOW
not yet run: R6-01..R6-13
```

---

## 6. 与旧证据 / 矩阵的关系

- 旧 Owner L2（Stage-20261120T165407Z 等）与 Packet 内计数均为**旧 Stage/旧 SHA** 产物：
  本报告只作历史引用与时长参考，**绝不复制/冒充**为本次 R-REV6 证据。
- 冻结 `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`、
  `docs/REVIEW_G4R_INDEPENDENT.md`、旧 Packet/Stage/JUnit 均不改字节（host 合同测试断言）。
- R-REV6 最终状态仍以独立 Reviewer 自己复跑结果为准；本报告是 Owner/Implementer 的
  原始证据与自检，不是 Reviewer 裁定，也不改变 `B03/E5-P04=UNVERIFIED`。
