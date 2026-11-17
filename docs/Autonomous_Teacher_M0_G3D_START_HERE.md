# G3-D — Lead Agent START HERE

**适用仓库**：[ygmldr/Autonomouse-Teacher](https://github.com/ygmldr/Autonomouse-Teacher)  
**制定时 HEAD**：`fff36232687afb779befb49fb6e2a10cedbcb7fd`；**G3-C 产品实现**：`b2f6af054555705192c4e1ae3019a68078764736`。运行时再确认实际 SHA。  
**核心参考**：`docs/M0_G3D_OS_BOUNDARY_DESIGN.md`、`docs/REVIEW_G3C_INDEPENDENT_v2.md`、`docs/M0_G3C_REVIEW_ERRATA.md`、`AGENTS.md`。

完整任务书：`Autonomous_Teacher_M0_G3D_Dual_Principal_Agent_Execution_Plan_v1.0.md`。  
配套工作矩阵：`Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv`，**53 项全部 `NOT_RUN`**，其中包含历史 16 个 D ID 的原样继承。

## 请直接执行

你是 Lead Agent，必须先读 `AGENTS.md`；你只负责编排、审阅和验证，不直接修改产品代码。请委派独立 Implementation Agents，准备与实现者隔离的 Reviewer。

**第一阶段：D-G0 + D-P0 + D1。** 先核实真实 HEAD 与 rootfs/deps/Runtime/DSH，证明加载的是修复后的 `b2f6af0` 产品基线或经审批的新实现，不是旧 `e6fde1c` Stage。小型修正 Digest 报告的两对关系与 OCI `pgrep/noexec` 兼容问题。采用 D0 方案 A：BridgeServer 最小 additive Socket Mode/GID、`SO_PEERCRED`、可信 Ready。建立真正不同 OS 主体的 Candidate（LXC UID 65534）与 Trusted（LXC UID 0）容器，私有 Broker State，唯一共享 UDS，均 `--network none`。使用真实 DSH `0.2.2-rc.2` 完成 Echo + Tool 两轮与独立账本核验。**D1 失败就 STOP，不得放松权限或继续 D2。**

**第二阶段：D2 + D3。** 在 D1 门槛通过后，由非 D1 实现 Agent 从真实 Candidate 身份执行 D2-01..D2-12 攻击，获得实际 errno/mount/uid_map/peercred；尤其复验旧的 Broker DB/Policy/直接 Claim 越权。随后跑跨容器 Crash/Cancel/Replay/Session/Streaming/两个真实 DSH Candidate 并发与标准固定 OCI 全量回归。不得把 Host Mock、raw UDS 和 real DSH 混为一谈。所有实际 Evidence 绑定 Code SHA + Stage SHA + Runtime SHA。

**第三阶段：冻结 + 独立审阅 + STOP。** 冻结实施 Commit，提供最小 Diff、完整运行 argv/UTC/exit、Sqlite 只读副本、Fake Receipt、Hash/Stage Manifest、新证据矩阵、Review Packet。独立 Reviewer 用自己的 Candidate 攻击和 DSH+Broker/Receipt 对账复验。允许限定范围 PASS/PARTIAL/FAIL/BLOCKED，禁止无证据升级。

## 绝对禁止

真实 Key、真实模型、外网/付费 HTTP、`podman pull`、开启 LiveGate、同 UID 伪隔离、Socket `0666`、把可信 State 挂给真实 Candidate、用 Mock 抵替内核权限、自动进入 G4/G5。不要修改 G3-C v1/v2 审阅或冻结 Packet 的原始字节。

## 首次提交给维护者的最小材料

1. `D-G0_BASELINE.md`：实际 HEAD、Code/Stage SHA、环境探针、无 Key、LiveGate BLOCKED。
2. `D1_IMPLEMENTATION_REPORT.md`：Two-Principal UID/GID/Peercred/Mount、Socket Mode、DSH Echo+Tool、Broker/Attempt/Receipt 对账。
3. `D1_REVIEW_PACKET/`：详细源码 Diff、原始命令和 Trace、内核拒绝初测、失败/残余。

**D1 Gate 失败或环境不可用，必须 STOP 并报告，不得直接跳到 D2；全 D 独立审阅完成后再次 STOP，待维护者决定 G4。**
