# M0 G3-D — 残余风险与处置登记（Findings & Disposition）

> **状态**：D4 交付物；不是 Independent Review，不是 `G3-D PASS`。Owner 对下列残余做**如实登记**，并区分“Owner 接受为已知残余”“需 Independent Reviewer 判定”“需维护者决定”三类。
> **身份**：base `4bd4803`；implementation `97230a0`（code 等同 `cf40c6b`）；`docs_sha` 见 Packet manifest。
> **原则**：残余不得被 Gate PASS 隐藏；任何 P0（OS 越权/未授权发送/重发/虚假账本）不是“残余”，而是 FAIL。本文件只登记 P1/P2 与范围边界。

---

## 0. 处置标签

| 标签 | 含义 |
|---|---|
| `ACCEPT_P2` | Owner 接受为已记录 P2；不阻断本 Gate 的限定范围，但不得写成“已防护”。 |
| `REVIEWER_JUDGE` | 必须由 Independent Reviewer 判断是否接受、是否影响最终裁定。 |
| `MAINTAINER_DECISION` | 需要维护者明确批准/范围收缩；Reviewer 不能代替。 |
| `OUT_OF_SCOPE` | 明确不在 G3-D 的安全主张内；不得作为 PASS 依据。 |

---

## 1. D2 残余（真实 Candidate 攻击阶段）

| ID | 残余 | 证据/事实 | 影响 | 处置 |
|---|---|---|---|---|
| **D2-R1** | 嵌套 user namespace 被内核允许 | D2-08：Candidate 可 `unshare(CLONE_NEWUSER\|CLONE_NEWNS)` 并在子 ns 挂 tmpfs；但 Host UID 仍 65534、Trusted/state 仍 `ENOENT` | 属于内核/userns 攻击面；本 Run 未获得 Host root 或 Trusted state，但不等于“userns 已安全” | `REVIEWER_JUDGE`（若要求“不可创建 userns”，需额外 sysctl/运行时配置，超出本 Gate） |
| **D2-R2** | Trusted 重启/reconcile 不在 D2 Gate 内 | D2-10 只证明 Candidate 无重发、状态保守（`PENDING/ATTEMPT_STARTED/RESPONSE_OBSERVED`）；`reconcile_on_startup` 的恢复语义由 D3 C03–C06 覆盖 | 若只看 D2，不能得出“崩溃后可恢复”结论 | `ACCEPT_P2`（D3 已覆盖，证据级别分开；不把 D2 当恢复证明） |
| **D2-R3** | Candidate session 无磁盘硬配额 | Candidate `candidate-session` 为 tmpfs `size=512m`，非 per-session 磁盘硬配额；D2-12 只覆盖 pids/memory/fd/连接 | 磁盘 DoS 未防护；任务书 §7.2/§9.3 允许作为 P2 残余 | `REVIEWER_JUDGE` + `MAINTAINER_DECISION`（若要求硬配额，须维护者批准新增 quota/卷方案） |
| **D2-R4** | G3-D 阶段无 Candidate 侧 Guard 组件 | D2-09 验证等价不变量：Candidate 本地 tool/plugin/伪造 Guard/admission 均不能获得 Controller 之外的发送权限；Controller 仍是唯一 Reserve/Claim/Attempt 路径 | 不是“Guard 已实现”；若未来引入 Guard，需单独重测 fail-closed | `ACCEPT_P2`（等价不变量已测；不宣称 Guard 存在） |
| **D2-R5** | D2-13 是 CONTROL，不是正式 Candidate 配置 | 同 UID map control 容器额外只读挂载 `$RUN/state`，得到 `EACCES(13)`；正式 Candidate **无** state 挂载 | 不能拿 D2-13 替代 D2-01/02/03 的“无挂载”结论 | `OUT_OF_SCOPE`（仅 DAC 对照；正式结论只来自 D2-01..03） |
| **D2-R6** | per-Run 路径不是 per-Run token | D2-14：同 UID 65534/group 2000 的 stale Candidate 若拿到 live 路径仍可连接；本 Run 证明 live 路径在其 mount namespace 不可见；`SO_PEERCRED` 只验证 UID | 同 UID 的其它进程/旧 Run 不是被密码学隔离的；边界是随机 Run 路径 + mount namespace + 唯一 socket | `REVIEWER_JUDGE`（不得宣称 per-run 身份认证） |
| **D2-R7** | Trusted crash hook 是 test-only | 需同时设置 `G3B_TEST_MODE=1` + `G3B_CRASH_HOOK`；Candidate 不能设置；argv/env 已记录 | 不是产品运行时后门；但 Reviewer 应确认 Candidate 不可注入该 env | `ACCEPT_P2`（test-only；Reviewer 可复核 env 隔离） |
| **D2-R8** | 单机 rootful Podman/Trusted root 属 TCB | Podman 4.9.3 rootful、crun 1.14.1、LXC 嵌套、Trusted root 均为受信基础；`CAN_ISOLATE` 仅本机 | 内核/容器运行时 0day、宿主 root 攻陷、供应链不在本 Gate 主张内 | `OUT_OF_SCOPE`（本机限定；不可外推） |

**D2 Gate 结论**：15/15 用例 PASS、19 Run exit 0、旧四绕过关闭、D2-11 正向成功；上述残余均不构成 P0。

---

## 2. D3 残余（Crash/Cancel/Streaming/并发阶段）

| ID | 残余 | 证据/事实 | 影响 | 处置 |
|---|---|---|---|---|
| **D3-R1** | C11 real-DSH 并发不是“同 Claim” | `d3-c11-real`：两个真实 Candidate 容器同时 running，但两个独立 DSH session 产生不同 `sessionId`/business digest/identity，2 Claim/2 Attempt/2 Receipt；`d3-c11-same` 才是受控双 Controller/UDS 同身份负例（1 finish、1 `ATTEMPT_ALREADY_STARTED`） | 未证明“两个真实 DSH 客户端共享同一 Claim”；不得把两者拼成 real-DSH same-claim PASS | `REVIEWER_JUDGE`（必须分别接受两个证据级别；若要求 real-DSH same-claim，需新 runner/实验） |
| **D3-R2** | C07 “双流”是单飞 Controller 下两个连接 | Controller 对 payload 处理有 `_send_lock`；`d3-c07-two` 是一个 active + 一个 queued，不是两个并发 Provider 调用；取消是 best-effort 契约 | 不能外推为“并发双 Provider 流取消” | `ACCEPT_P2`（报告已明确；不主张并发 Provider 调用） |
| **D3-R3** | C09 Broker 只 `SIGSTOP`，不重启 | 容器 teardown 会回收 stopped broker；本 Case 不证明 Broker 进程级 crash/restart 的恢复语义；Broker DB 的恢复由 C05/C06 的 Controller reconcile 覆盖，但不是 Broker 自身重启 | 若要求 Broker 自身 crash-recovery，需额外实验 | `REVIEWER_JUDGE`（不得把 SIGSTOP 当 crash-restart 证明） |
| **D3-R4** | C08 SIGTERM 故意留下保守状态 | SIGTERM 后最终 Attempt `ATTEMPT_STARTED`、Reservation `PENDING`、Receipt=1；未证明重启后自动结算（C05/C06 覆盖其它窗口） | 不能从 C08 得出“SIGTERM 后自动全面恢复” | `ACCEPT_P2`（保守状态是预期；不伪造 Cancel/Fee=0） |
| **D3-R5** | C10 时钟换算依赖 Host realtime/monotonic 对 | DSH `time0` 是 epoch ms；Host 用同一台机的 realtime/monotonic 采样换算；`CLOCK_MONOTONIC` 是同一 Host 内核，不跨主机 | 跨主机时钟排序不在主张内；Reviewer 应独立取时钟对重算 | `REVIEWER_JUDGE`（若 `T1>=T2` 或 Fake 首 chunk 不早于 exit，应 FAIL） |
| **D3-R6** | C12 的 10 次重启不服务新 admission | 每次重启在 reconcile 后以 `ADMISSION_REPLAYED_AFTER_RECOVERY` exit 3；这是“恢复旧状态”，不是“继续接单”；接新请求需要新 admission | 不能外推为“长期运行/持续接单稳定性” | `ACCEPT_P2`（范围明确；持续接单需新 Gate） |
| **D3-R7** | 固定 OCI 4 deselect / 7 skip | 4 个显式 deselect（3 个 host-root tar 树哈希 + 1 个 host-root peer-uid 接受）；7 skip（5 root-only UDS/布局、1 git diff、1 既有 external probe mount）；rootfs 无 `tar`/`git`、uid 65534 | OCI 本身未执行那 4 个测试；Host pytest 覆盖 tar/root 契约，但不能说“920 全跑” | `REVIEWER_JUDGE`（必须复核 deselect 分类与 Host 补跑） |
| **D3-R8** | Node 测试是 Host 运行 | Node `v22.23.2`；guard 19/19、skill 8/8 在 Host；不是 DSH Candidate 内 Node；真实 adapter 执行由 C01/C10/C11 的 real-DSH 覆盖 | 不能把 Node host 测试当 Candidate 沙箱证据 | `ACCEPT_P2`（证据级别已标注） |

**D3 Gate 结论**：17/17 矩阵行 PASS、13 case/suite exit 0、无 P0；上述残余均已在报告/矩阵 `residual` 字段标注。

---

## 3. D4 / Packet 范围的残余

| ID | 残余 | 事实 | 处置 |
|---|---|---|---|
| **D4-R1** | OCI 结果依赖“只读冻结树”物化 | D4 第一次 `git archive`（0644）命中 `target_profile_static` 的既有 host-only 语义（908 passed / 1 failed）；按 D3 REG-01 的 0444/0555 冻结树重跑后 909 passed / 7 skipped / 916 tests / 0 failed。两次日志都在 Packet | `REVIEWER_JUDGE`（应确认物化方式与 Host 失败一致；不得把 0644 失败说成产品回归） |
| **D4-R2** | D4 只重跑最终回归，不重跑 D1/D2/D3 全量 | D4 负责证据编排/Packet/最终回归；D1/D2/D3 的原始证据保持冻结，未重跑 3 个 Stage 的完整 case 套件 | `ACCEPT_P2`（Reviewer 自建 Probe/复跑是独立要求；D4 不冒充新执行） |
| **D4-R3** | Packet 自身不是独立证据 | Packet 的 `hashes.sha256` 只证明字节一致，不证明实现正确；SQLite 副本未在包内打开（避免 `-shm` 漂移） | `OUT_OF_SCOPE`（Reviewer 必须自建证据；Packet 仅提供可复现材料） |

---

## 4. 旧 G3-C P2 的承接（不重复、不删除）

G3-C 的以下 P2 在 G3-D 中**未重开**，但承接关系必须保留：

| G3-C 项 | 状态/关系 | G3-D 处置 |
|---|---|---|
| `SRC-12` `next_logical_step` 不使用 `run_id` | G3-C `DOCUMENTED_RESIDUAL`；只被测试引用、不在运行路径；G3-D `src` 与 base 相同，未改 | `ACCEPT_P2`；若未来接入必须重写 SQL 并重新评审；G3-D 不以“已修”表述 |
| G3-B `P2-4` observation 专用表未使用 | G3-C `DOCUMENTED_RESIDUAL`；Attempt journal 的 observation 文档为权威；G3-D 未改 `src` | `ACCEPT_P2`；本 Gate 仍以 journal 文档对账，未新增双写/迁移 |
| G3-B `P2-6` 并发 harness 启动抖动 | G3-C `DOCUMENTED_RESIDUAL`；G3-D C11 用显式并发/受控双 Controller；未复现旧 15s 等待 | `ACCEPT_P2`；C11 的证据级别已单列，不把它说成旧场景修复 |

> G3-C 历史 docs/Packet/矩阵**未修改**；上表只引用 `docs/M0_G3C_FINDINGS_AND_DISPOSITION.md` 的既有结论。

---

## 5. 处置汇总（给 Reviewer 与维护者）

### 5.1 Owner 接受为已知 P2（不阻断限定范围）

- D2-R2（restart 由 D3 覆盖）、D2-R4（无 Guard，但有等价不变量）、D2-R7（test-only hook）、D3-R2（单飞）、D3-R4（SIGTERM 保守）、D3-R6（不接新单）、D3-R8（Node host）、D4-R2（D4 不重跑全量）、G3-C SRC-12/P2-4/P2-6。

### 5.2 必须由 Independent Reviewer 判定

- D2-R1（嵌套 userns）、D2-R3（磁盘硬配额）、D2-R6（per-Run 路径非 token）、D3-R1（C11 两证据级别）、D3-R3（Broker 不重启）、D3-R5（C10 时钟）、D3-R7（OCI deselect/skip）、D4-R1（OCI 物化方式）。
- Reviewer 若拒绝任一影响核心不变量的项，应给 `PARTIAL`/`FAIL`，不得被 Owner 的 Gate PASS 覆盖。

### 5.3 需维护者决定

- 是否接受 **Candidate session 无磁盘硬配额**作为 P2（D2-R3）；若不接受，需维护者批准新增 quota/卷方案并重跑 D2-12/D3。
- 是否要求 **D2-R1 嵌套 userns** 在运行时被禁用（sysctl/运行时配置），或接受为内核残余。
- 是否要求 **real-DSH same-claim** 新实验（D3-R1）；当前只有受控双 Controller/UDS 负例。
- 是否允许进入 G4/G5/Live（本文件**不**授权；G3-D 复核通过也不自动解锁）。

---

## 6. 残余与最终裁定的关系

- 若 Independent Reviewer 接受上述 `REVIEWER_JUDGE` 项且未发现 P0，可给 `PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`（限本机/冻结 SHA/已验 Runtime）。
- 若有任一 P0：`FAIL`。
- 若关键证据缺失/无法复现：`PARTIAL`。
- 若双 Principal/namespace/UID map/cgroup/UDS 无法真实建立：`BLOCKED`。
- **无论哪种裁定，都不等于** `M0_GO` / `LIVE_APPROVED` / `G4_PASS` / `G5_PASS`。

---

## 7. 引用

- `docs/M0_G3D_IMPLEMENTATION_REPORT.md`
- `docs/M0_G3D_REVIEW_REQUEST.md`
- `docs/M0_G3D_G0_REBASELINE.md`
- `docs/M0_G3D_D_P0_ERRATA.md`
- `docs/M0_G3D_D1_REPORT.md`、`docs/M0_G3D_D2_REPORT.md`、`docs/M0_G3D_D3_REPORT.md`
- `docs/M0_G3C_FINDINGS_AND_DISPOSITION.md`（G3-C P2 原始登记）
- Packet：`artifacts/review-packet-g3d-97230a0ba40f5f2dec98a426676fbe81a5157a26/review/remaining-risk-register.md`
