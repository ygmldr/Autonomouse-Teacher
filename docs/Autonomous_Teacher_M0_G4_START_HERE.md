# G4 PreLive No-Key — START HERE

**仓库**：`https://github.com/ygmldr/Autonomouse-Teacher`  
**参考远程 HEAD**：`017c747631cae1e7788014c4ef9e6056c141fecd`（执行时重新检查）  
**上一关口**：`PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`，只限本机和冻结 Runtime。

先阅读：
1. `AGENTS.md`（Lead 只编排/审阅，实际实现交子 Agent）。
2. `Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md` 全文。
3. `Autonomous_Teacher_M0_G4_PreLive_Test_Evidence_Matrix_v1.0.csv`。
4. 仓库 `docs/REVIEW_G3D_INDEPENDENT.md`、`docs/M0_G3D_REVIEW_ERRATA.md`、`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`、`docs/E5_PRELIVE_NO_KEY_REPORT.md`、`docs/SECURITY_APPROVALS.md`。

## 本轮权限

**允许**：只在无 Key、无外网、Fake Provider 下执行 G4-00/A/B/C/D/E 工程准备、模拟准入、负例、独立复核。

**禁止**：真实 DeepSeek/OpenCode API、真实 Secret、外部 TCP/HTTP、修改 `LiveGate` 为放行、修改 `run_live.sh` 硬退出、部署真实信任根、自动签发实际 Approval、自动进入 G5/G6。

工作顺序：`G4-00` → `G4-A + G4-B` → `G4-C` → `G4-D` → `G4-E` → 独立 Reviewer → **STOP**。

**最高可能裁定**：`PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`。`G4-H` 六项在 CSV 默认 `BLOCKED`，`E5_PRELIVE_FULL` 依旧 `BLOCKED_PENDING_HUMAN_DEPLOYMENT`。若任何一项需要真实 Key，标 `BLOCKED`，不要尝试“临时开一次”。

完整证据：逐项 `argv/UTC/exit/hash/loaded modules/fake receipts/Broker DB/LiveGate negatives`；Reviewer 自己做恶意探针。

## 完成时交给维护者

`docs/M0_G4_IMPLEMENTATION_REPORT.md`、`docs/M0_G4_REVIEW_REQUEST.md`、`docs/REVIEW_G4_INDEPENDENT.md`、完整矩阵、Packet Manifest/Hashes、关键源码 Diff、P0/P1/P2 和 human-only 阻断项。
