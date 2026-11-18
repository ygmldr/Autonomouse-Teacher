# M0 G3-D 独立复核归档勘误与残余登记（append-only）

- **文档性质**：G3-D 最终归档的勘误、P2 残余与历史状态登记。本文件为 **append-only**：后续如需修订，只在文件末尾追加新小节，不改写既有字节。
- **归档时间**：2026-11-18T00:29Z（UTC）。
- **归档提交**：`docs: archive G3-D independent review (PASS) and final errata (no-key)`。同一提交只包含：本文件（新增）、`docs/REVIEW_G3D_INDEPENDENT.md`（原字节归档）、`docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv`（仅 `D-REVIEW-01` 一行）。
- **约束**：0 真实 Key / 0 真实模型 / 0 外网 / 0 Live；未 `podman pull`；未修改实现、测试、脚本、证据、Packet、历史 docs 或历史矩阵字节；未 amend、未 push。

---

## 1. 归档对象与冻结输入

### 1.1 Reviewer 身份与独立性

- **Reviewer**：Independent D Reviewer（独立 D Reviewer）。
- **独立性声明**：未参与 G3-D0/D1/D2/D3 的实现、证据生成、矩阵填写或 D4 Review Packet 构建；未复用 Owner 的 `summary.json`/`checks.json` 结论文字作为判定；所有关键结论来自 Reviewer 自建 Probe、独立复跑、原始字节复核及 SQLite 只读副本对账。
- **复核窗口**：2026-11-17T23:33Z – 2026-11-18T00:20Z（UTC）。
- **工作树**：`/root/Autonomous Teacher`。
- **写入范围**：仅 `docs/REVIEW_G3D_INDEPENDENT.md` 与 `artifacts/reviewer-g3d/`（后者被 gitignore，不进入提交）；Reviewer 未修改矩阵、Packet、Stage、Rootfs/Deps、D1–D3 证据或任何历史 docs；未 commit / push。

### 1.2 冻结输入（Reviewer 独立复算一致）

| 对象 | 冻结值 |
|---|---|
| base | `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b` |
| implementation | `97230a0ba40f5f2dec98a426676fbe81a5157a26` |
| code | `cf40c6bfb84ceae98e795db19efa955aa3035991` |
| docs（归档前 HEAD） | `ce4979eb1c28f5d03efe4cb3dade5d200003b8e2` |
| D3 Stage | `artifacts/g3d/stage-20261117T221955Z`；manifest `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03`；tree `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5` |
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| DSH SDK | `0.2.2rc2`（DSH `0.2.2-rc.2`），runtime SHA `1cc41d5a…`，adapter `2cb42461…`（`deterministic_match=true`） |
| Node | `v22.23.2` |
| Runtime / 内核 | Podman `4.9.3` rootful、crun `1.14.1`、kernel `6.17.13-2-pve`、cgroup v2 |
| Python | `3.11.15` |

### 1.3 Reviewer 报告

| 项 | 值 |
|---|---|
| 路径 | `docs/REVIEW_G3D_INDEPENDENT.md` |
| 大小 | 42996 B |
| sha256 | `a16dd453386a23b51566f474dc4bc4166a6823fa586d85e3a49bb38adfc07a45` |
| 归档方式 | 新文件、**原字节** `git add`；提交前后 sha256 必须保持上述值 |
| 证据索引 | `artifacts/reviewer-g3d/RUN_INDEX.md` |

### 1.4 Review Packet（只读，未重打包）

- 路径：`artifacts/review-packet-g3d-97230a0ba40f5f2dec98a426676fbe81a5157a26/`。
- `sha256sum -c hashes.sha256`：**1041/1041 OK**，exit 0；1043 文件、1040 payload、0 symlink；`packet_payload_tree_sha256` 复算一致。
- `manifest.json`：`docs_sha = ce4979e…`、`real_model_calls=0`、`real_external_http_calls=0`、`has_real_key=false`、`live_gate_status=BLOCKED`。
- **冻结说明**：Reviewer 报告产生于 Packet 构建之后，属于 **post-packet 归档**，因此不进入 Packet，也不触发重打包；Packet 的 `docs_sha` 仍为 `ce4979e`，保持原样。详见 §6。

---

## 2. 裁定与范围限定

### 2.1 唯一裁定

**`PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`**

- **P0 = 0；P1 = 0。**
- P0（阻断）与 P1（必须修复后复审）均无；P2 残余见 §4，未验证项见 §5。

### 2.2 与裁定同义、不可省略的范围限定

该 PASS **仅限本机**（`192.168.1.101` / rootful Podman 4.9.3 + crun 1.14.1 + kernel `6.17.13-2-pve` + §1.2 冻结 rootfs/deps/stage/DSH SHA）**已实测的**：

1. 双 OS Principal 隔离；
2. 真实 DSH（Fake Provider）正向；
3. 真实 Candidate 攻击拒绝；
4. 崩溃/取消/断连/并发/恢复一致性。

**该裁定不主张、也不得外推为**：

- 内核/容器运行时 0day 防护；
- 宿主 root 被攻陷后的安全；
- 生产部署安全；
- 真实 Provider / 真实 Invoice / exactly-once；
- 跨 Runner、跨内核、跨 Runtime 可移植性；
- 任何 Live / G4 / G5 / M0 GO 授权。

---

## 3. 独立复核摘要（不采信 Owner 结论文字）

| 复核域 | 结果 | 关键事实（Reviewer 独立复算/复跑） |
|---|---|---|
| **R0 身份 / Packet / 漂移** | PASS | 1041/1041 哈希 OK；两种 patch 字节一致；Stage/Rootfs/Deps/DSH/Node/Podman 身份全部复算一致；实际加载模块 SHA 等于冻结引用，旧 `e6fde1c` Stage 未被加载 |
| **R1 静态复验** | PASS | D1-A socket mode/peercred/ready/stale 逐行核验；Candidate argv 白名单；Admission UID 与 OS peer UID 分离；G3-C 语义未削弱（`src` 相对 base 0 改动） |
| **R2 自建真实 Candidate 攻击** | PASS | 8 个自建 Run 全部 `exit 0`、`cleanup.ok=true`、canonical；24 个协议负例后账本仍为 0；state 不可读/不可写（No Mount / CONTROL DAC EACCES）；旧 G3-B 四个同 UID 绕过与当前真实拒绝成对记录；同 payload 重放 → `ATTEMPT_ALREADY_STARTED`、仅 1 套账本 |
| **R3 真实 DSH 双主体** | PASS | Echo 1/1/1/1/1；Tool 2/2/2/2/2 且 tool result 进入第二请求；Resume 两个真实 Candidate 进程、`resume_session`、不重放旧 Attempt；usage 与 receipt 字段级相等 |
| **R4 故障 / 并发** | PASS | C04/C05/C06 三个真实崩溃窗口（trusted `exit 97` + 对应 hook）；C07 取消；C08 断连；C10 自算时钟 `T1 < T2`；C11-same 恰 1 finish + 1 `ATTEMPT_ALREADY_STARTED`；C11-real 两独立请求分级单列 |
| **R5 回归 / 清理** | PASS | 固定 OCI **916 tests / 909 passed / 0 failed / 7 skipped / 4 deselects**，exit 0；Host targeted 144/31/110/14 全过；Node 19/19 + 8/8；Ruff 0；LiveGate BLOCKED；`podman ps -a` 空；0 残留；三 Hash canonical |

补充：

- 固定 OCI 的 4 个 deselect 与 7 个 skip **如实保留**，未被写成“920 全跑”；Host full 的 2 个失败为已记录的 host-only 环境语义（可写 checkout 的 config mode、子进程 `PYTHONPATH`），未隐藏、未改断言。
- 所有账本结论来自 evidence 内只读 DB 副本（`/tmp` 副本），未打开 live DB；未复用 Owner 的 `checks.json` 文字。

---

## 4. P2 清单与处置

**总则**：以下 P2 均**不阻断**上述限定范围 PASS；标记「**Reviewer 已接受但需维护者知情/决定**」者必须由维护者明确接受或另立工作项；标记「**UNVERIFIED**」者不得被引用为已证明。

| ID | 残余 | Reviewer 处置 | 维护者动作 |
|---|---|---|---|
| **R2-P2-a** | Candidate session 无磁盘硬配额（`/work/session` 是 host bind mount，不受 `/work` tmpfs 512 MiB 限制） | **Reviewer 已接受但需维护者知情/决定**；本 Gate 不主张磁盘 DoS 防护 | 明确接受该残余，或另立磁盘配额工作项并重新取证 |
| **R2-P2-b** | 内核允许 Candidate 创建嵌套 userns（可在自己的 ns 挂 tmpfs；`mknod` EPERM、trusted ptrace ESRCH）；对 root-owned state 仍 `EACCES`（含 unshare 后） | **Reviewer 已接受但需维护者知情/决定**；仅登记为 P2 内核攻击面，不作为“userns 已安全”外推 | 明确接受该内核攻击面，或另立加固/重测项 |
| **R2-P2-c** | `SO_PEERCRED` 是 OS 身份，不是 per-Run token；拿到 live 路径的同 UID 旧 Run 仍可连接 | **Reviewer 已接受但需维护者知情/决定**；依赖随机 Run path + mount namespace + host `0700` 父目录；不主张 per-Run 认证 | 明确接受，或另立 per-Run token 工作项 |
| **D3-P2-a** | 未证明 real-DSH same-claim；只有受控双 Controller/UDS 负例 | **Reviewer 已接受**（按允许降级；两级证据严格分开，不拼接） | 如维护者要求 real-DSH same-claim，另立补测 |
| **D3-P2-b** | C09 Broker 仅 SIGSTOP，不重启；Reviewer **未重跑** C09 | **UNVERIFIED**；不据此主张 Broker 进程级 crash-recovery | 决定是否补跑 C09 |
| **D3-P2-c** | C12 10+ 重启只恢复旧状态、不接新 admission；Reviewer **未重跑** C12 | **UNVERIFIED**；不外推持续接单/长期运行稳定性 | 决定是否补跑 C12 |
| **D3-P2-d** | C07 “双流”是单飞 Controller 下 1 active + 1 queued，不是两个并发 Provider 调用 | **Reviewer 已接受**；不主张并发 Provider 流 | 知情即可 |
| **OPS-P2-a** | 固定 OCI 4 deselect / 7 skip；rootfs 无 tar/git、uid 65534 | **Reviewer 已接受**；Host 补跑覆盖；不写“920 全绿” | 知情即可 |
| **OPS-P2-b** | Host full 2 个 host-only 环境失败（可写 checkout 的 config mode；子进程 `PYTHONPATH`） | **Reviewer 已接受为环境**；未隐藏、未改断言；OCI 为权威 | 知情即可 |
| **OPS-P2-c** | Node 测试在 Host 运行，不是 Candidate 内 Node | **Reviewer 已接受**；真实 adapter 由 real-DSH 覆盖 | 如要求 Candidate 内 Node，另立补测 |
| **OPS-P2-d** | Launcher cleanup 在 preflight 早失败（run dir 尚未创建）时把 `run_dir_not_deleted` 计为 problem | **Reviewer 已接受为 P2 证据卫生**；无安全影响；建议后续小修 | 决定是否排期小修 |
| **ENV-P2-a** | 运行固定 OCI 会在 rootfs 生成空 `/evidence` 挂载点，必须在下次 preflight 前删除 | **Reviewer 已按允许方式处理并记录**；非产品漂移 | 见 §8；已 rmdir 并复核 canonical |

Reviewer 对 Owner 残余登记的复核：`D2-R1`（嵌套 userns）、`D2-R3`（磁盘配额，需维护者决定）、`D2-R6`（per-Run 路径非 token）、`D3-R1`（C11 两级）、`D3-R3`（Broker 不重启，接受为“未证明”）、`D3-R5`（C10 时钟）、`D3-R7`（OCI deselect/skip）、`D4-R1`（OCI 物化方式）均**接受**；其中需维护者决定的项已在上表登记。

---

## 5. 明确未验证项（UNVERIFIED / 不在主张内）

1. **C02**（Candidate 发送前 SIGKILL）、**C03**（Claim 后 Attempt 前崩溃）、**C09**（Broker SIGSTOP/Fake 卡死/首帧 Stall）、**C12**（10+ 重启/资源压力）**未由 Reviewer 重跑**；其结论仅来自 Owner 证据，本归档不背书。
2. cgroup `pids-limit=8` / `memory=128m` 的 Candidate 压测（D2-12 部分）**未重跑**。
3. **real-DSH same-claim 竞争未构造**；只有受控负例。
4. Broker 进程级 crash/restart 恢复、持续接单/长期运行稳定性**未证明**。
5. Candidate Session 磁盘硬配额、跨 Run 同 UID 路径攻击**未验证**（P2）。
6. 内核/容器运行时 0day、宿主 root 攻陷、供应链、真实 Provider/Invoice/exactly-once、跨 Runner/跨内核可移植性**不在主张内**。
7. Node 测试仅在 Host；未在 Candidate 沙箱内重跑 Node。
8. 未覆盖的失败路径（如真实内核构造 `PEERCRED_UNAVAILABLE`）只以静态代码与 Host 单测覆盖，未在容器内制造“`SO_PEERCRED` 不可用”的内核状态。

---

## 6. 矩阵归档与 Packet 冻结说明

### 6.1 矩阵最终化

- 归档前：`docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv` 共 53 行 = **52 PASS / 1 NOT_RUN**（仅 `D-REVIEW-01` 为 `NOT_RUN`）；sha256 `e846d68f09f84dfbbf4932e1512571d8aed5a95b1298606e7306bb31c1f9875f`。
- 归档后：同一矩阵共 53 行 = **53 PASS / 0 NOT_RUN**；sha256 `178a091541a30b684f3134fc3537bd8310b3d76345a6e70f8829928b98118ceb`。
- **仅** `D-REVIEW-01` 一行被修改：`status=PASS`；`observed` 记录裁定、P0/P1=0、报告 sha256、Reviewer 独立攻击/DSH/DB 对账摘要；`command_argv`/`utc_start`/`utc_end` 填 Reviewer 复核窗口（2026-11-17T23:33:00Z – 2026-11-18T00:20:00Z）与报告/证据路径；`exit_code=0`（Reviewer 8 个自建 Run 与固定 OCI 均 exit 0；Host full 的 917/2/1 为已记录 host-only 环境语义，见 P2）；`code_sha=cf40c6b…`、`stage_sha=644823d4…`、`env_sha` rootfs `25491e45…` + deps `e07729d7…`；`evidence_paths` 指向本报告与 `artifacts/reviewer-g3d/RUN_INDEX.md`；`owner=Independent D Reviewer`；`reviewer_status=PASS`；`residual` 写限定范围与 P2 登记。
- 其余 **52 行逐字节未改**（归档后重新解析确认：前 53 条与归档前完全一致）；历史 G3-C 矩阵（sha256 `6f21d562…`）与 G3-B 矩阵（`cc1df8c6…`）未改。
- Reviewer 在复核时**未修改矩阵**（其报告 §10 明确仍为 52 PASS / 1 NOT_RUN）；`D-REVIEW-01 → PASS` 由 Lead 在本次归档中执行，属预期的归档动作，不是 Reviewer 自评。

### 6.2 Packet 冻结

- Packet 的 `docs_sha` 为 `ce4979eb1c28f5d03efe4cb3dade5d200003b8e2`；Reviewer 报告与本次 errata 均为 **post-packet** 产物，**不进入** Packet，**不重打包**。
- Packet 内的矩阵副本仍为归档前字节（sha256 `e846d68f…`，52 PASS / 1 NOT_RUN），这是**有意的冻结快照**；仓库矩阵在归档后为 `178a0915…`（53 PASS / 0 NOT_RUN）。两者差异仅此一行，属于归档前进，不是 Packet 完整性失败。
- Packet 的 `sha256sum -c hashes.sha256` 在归档时仍为 **1041/1041 OK**；未重跑 `build_packet.py`，未添加/删除 Packet 文件。

---

## 7. 历史状态声明（不得追溯改写）

1. **G3-B `B0-02=BLOCKED` 仍为历史状态**：本次 G3-D 限定范围 PASS 不改变、不追溯升级、不覆盖 G3-B 的历史结论；旧同 UID 绕过证据继续作为历史反例保留（Reviewer §3.5 已与当前真实拒绝成对记录）。
2. **本 G3-D 限定范围 PASS 不改变 G4/G5/Live 的未授权状态**：不构成 G4/G5 通过、不构成 Live 授权、不构成 `M0_GO`；不得改写为 `LIVE_APPROVED`、`G4_PASS`、`G5_PASS` 或任何等价表述。
3. **`OS_TRUST_BOUNDARY` 仅在上述限定范围/冻结环境内被独立复核为通过**：即本机冻结 Runtime/SHA 下的双 OS Principal 隔离、真实 DSH（Fake Provider）正向、真实 Candidate 攻击拒绝与崩溃/恢复一致性。**不得外推**到其他宿主、内核、Runtime、Stage、真实 Provider 或生产环境，**不得据此进入 G4**。
4. 本归档不修改任何历史 docs 字节；历史 G3-C/G3-B 矩阵与报告保持原样。

---

## 8. 过程项与证据卫生

1. **空 `rootfs/evidence` 挂载点（ENV-P2-a）**：Reviewer 运行固定 OCI 命令时，podman 为缺失的 `/evidence` bind mount 在 rootfs 内自动创建空目录 `artifacts/security/rootfs/evidence`（`root:root 1755`，空）。Reviewer 确认为空后 `rmdir`，rootfs 立即回到 canonical `25491e45…`，并记录于 `artifacts/reviewer-g3d/r0-identity/rootfs-evidence-artifact.txt`；Packet 的 `regressions/rootfs-runtime-cleanup.txt` 亦有同类记录。**D4 后 Lead 清理该空目录并复核 canonical**；该现象属固定 OCI 物化方式的环境副作用，**不是产品漂移**，未改产品字节。
2. **Launcher 早失败 `run_dir` 误报（OPS-P2-d）**：preflight 早失败、run dir 尚未创建时，cleanup 把 `run_dir_not_deleted` 计为 problem；仅证据卫生问题，无安全影响。本次归档不修改实现（实现面冻结），建议后续小修。
3. **Node 仅 Host（OPS-P2-c）**：Guard 19/19、Skill 8/8 均在 Host 运行；未在 Candidate 沙箱内重跑 Node，真实 adapter 由 real-DSH 覆盖。
4. **证据目录**：`artifacts/reviewer-g3d/` 被 gitignore，不进入归档提交；其完整性由 `artifacts/reviewer-g3d/RUN_INDEX.md` 索引。

---

## 9. 维护者待决定项

| # | 待决定 | 说明 / 影响 |
|---|---|---|
| 1 | **是否接受 session 无磁盘硬配额（R2-P2-a）** | 接受则作为已知 P2 记录在案；不接受则需新增磁盘配额实现并重新取证/复核 |
| 2 | **是否接受嵌套 userns 风险（R2-P2-b）** | 接受则保留为 P2 内核攻击面；不接受则需加固或限制 userns 并重测 |
| 3 | **是否补测 C09/C12（及 C02/C03、cgroup 压测）** | 补测可把 UNVERIFIED 转成已证明；不补测则维持 UNVERIFIED，不得引用为已证明 |
| 4 | **是否授权 G4 规划** | **当前未授权**；本 PASS 仅限 G3-D 限定范围，不自动进入 G4；需维护者显式决定 |
| 5 | （建议）是否接受 OCI 4 deselect / 7 skip 与 Host 2 个环境失败作为最终证据基线 | 接受则归档为已知环境限制；不接受则需补跑/调整环境 |

在上述决定作出前，默认状态为：**P2 已登记但未获维护者正式接受**；C09/C12 等为 **UNVERIFIED**；**G4/G5/Live 未授权**。

---

## 10. 归档记录与不可变性

- **同提交文件（仅 3 个）**：
  1. `docs/REVIEW_G3D_INDEPENDENT.md`（新增；原字节；sha256 `a16dd453386a23b51566f474dc4bc4166a6823fa586d85e3a49bb38adfc07a45`）；
  2. `docs/M0_G3D_REVIEW_ERRATA.md`（本文件，新增）；
  3. `docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv`（仅 `D-REVIEW-01` 行）。
- **提交信息**：`docs: archive G3-D independent review (PASS) and final errata (no-key)`。
- **不 amend / 不 push / 不 stage 其他文件**；提交后工作区应为 clean（`git status --porcelain -uall` 0 行）。
- **报告字节不变**：提交前后 `docs/REVIEW_G3D_INDEPENDENT.md` sha256 必须始终为 `a16dd453…`；若未来发现不一致，以本文件追加勘误处理，不得静默改写。
- **append-only 版本记录**：

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-18T00:29Z | 初次归档：Reviewer 报告原字节归档、矩阵 `D-REVIEW-01→PASS`、P2/UNVERIFIED/历史状态/维护者待决定项登记 |

---

## 附录 A：复核证据索引

| 内容 | 路径 |
|---|---|
| Run 索引 | `artifacts/reviewer-g3d/RUN_INDEX.md` |
| R0 身份 / Packet / 加载 | `artifacts/reviewer-g3d/r0-identity/` |
| R1 静态 | `artifacts/reviewer-g3d/r1-static/` |
| R2 自建 Probe / 结果 | `artifacts/reviewer-g3d/r2-probes/` |
| R3 真实 DSH | `artifacts/reviewer-g3d/r3-dsh/` |
| R4 故障 / 并发 | `artifacts/reviewer-g3d/r4-faults/` |
| R5 回归 / 清理 | `artifacts/reviewer-g3d/r5-regressions/` |
| 原始日志 | `artifacts/reviewer-g3d/logs/` |
| 账本对账工具 | `artifacts/reviewer-g3d/analyze_ledger.py` |
| Reviewer 报告 | `docs/REVIEW_G3D_INDEPENDENT.md` |
| 本勘误 | `docs/M0_G3D_REVIEW_ERRATA.md` |
