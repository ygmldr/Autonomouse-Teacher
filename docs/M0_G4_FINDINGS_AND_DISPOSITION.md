# M0 G4 — Findings 与残余处置（G4-E 冻结）

- **性质**：本文件是 **Owner 自查 + G4-E 冻结登记**，不是独立 Review 结论。
- **冻结点**：base `017c747`、impl `a6f3e0a`、code `d3d429c`、docs 本提交。
- **状态**：G4-A/B/C/D 均已实现并自测；E5 Full 未通过；G4-H 六项全部 `BLOCKED`。
- **纪律**：只登记真实运行暴露的问题；不把“无 Key 工程通过”写成“人类授权部署通过”；不修改历史测试/证据来消除失败。

---

## 0. 严重等级总览

| 等级 | 数量 | 说明 |
|---|---:|---|
| **P0**（权限绕过/可计费出站/Key 泄漏/账本 FREE/未授权 Fake send） | **0** | 本轮所有可测路径均为 BLOCKED 或 0 发送；真实 Key/网络调用 0 |
| **P1**（关键部署契约不一致/凭据边界失效/结算恢复错误/核心主张缺动态证据） | **0** | G4-C/D 的关键正向/负向链有 L2 证据；无发现 P1 |
| **P2**（不影响本轮限定范围的运行维护/证据卫生） | **14 项 + 3 项维护者待决** | 见 §2–§6 |

> P0/P1=0 是 **Owner 自查**，不替代独立 Reviewer。Reviewer 若发现任何可复制反例，可将裁定降为 FAIL/PARTIAL。

---

## 1. P0/P1 判定依据（摘要）

- **P0 排除**：`LiveGate` 恒 BLOCKED；`run_live.sh`/CLI exit 3；Adapter 恒 `SECURITY_BLOCKED`；合成签名 `billable_send_authorized=False`；无 Claim/已消费 Claim/Prepared 或 Payload 变更/Fake=0；Broker kill Fake=0；配额超限 0 发送；哨兵 0 命中；0 真实 Key/外部 HTTP/模型。
- **P1 排除**：G4-C 有 9 次真实双 Principal 容器运行（Echo/Tool/Stream/负例/replay/crash/broker-down/quota）；G4-D 有真实外部 watchdog kill/absence、撤销/epoch、哨兵、E5 子集；G4-B 有真实 DSH Tool 两轮 2/2/2/2/2 与 Controller 白名单；G4-A 有 223 项 host + OCI uid-0 replay。
- **不把“缺真实 Key”误标为技术 P0**：它是 G4-H/G5 的硬 `BLOCKED` 条件，不是本轮工程缺陷。

---

## 2. G4-A 残余

| ID | 残余 | 处置 |
|---|---|---|
| A-R1 | 全量证据为 L1-HOST；G4-E 补 OCI uid-0 replay（221 passed，2 环境 deselect） | 已缓解；仍非 65534 候选环境下的全量 A 证据 |
| A-R2 | G3-D frozen-src 断言因授权改码必然失败 | 显式登记，deselect，不修历史测试 |
| A-R3 | 闭包路径表是 G4-A 契约声明，runtime/deps/stage 在 fixture 中为 TEST_ONLY 占位 | 由 G4-B manifest 与 G4-E stage 证据补强；不声称独立构建 |
| A-R4 | 新 API 未加入 `security/__init__.py`（写域外） | 调用方直接导入；后续包维护提交需 Lead 授权 |
| A-R5 | 单独 `load_execution_authorization` 不知道 candidate Stage | 必须经 `TrustedLiveController` 组合；G4-C 保持 |
| A-R6 | 单次使用记录未签名/未锚定；可信目录 owner 可删除 | 部署侧 root 只读；P2-RUN-IDENTITY 未决 |
| A-R7 | 检查点到发送之间无 OS 级不可变保证 | G4-C 以 prepared/claim/字节摘要绑定收窄；G4-H 用只读挂载 |
| A-R8 | pricing `REQUIRED_UNVERIFIED`；$10 是工程硬顶，不是供应商硬限 | G4-H/G5 核验官方价格与供应商额度 |
| A-R9 | 密钥轮换/吊销 SOP 由人类定义 | G4-H-02 |
| A-R10 | `signature_valid` 只证明 Ed25519 数学有效，不证明人类意图 | G4-H-01/02 |
| A-R11 | 网络守护为进程内 socket patch，不能证明子进程/内核无网络 | 容器侧证据在 G3-D/G4-C |
| A-R12 | 权限检查基于 mode/owner，不覆盖 ACL/xattr；测试以 root 运行 | G4-H 评估 |

**附加观察（A-OBS-1）**：`TrustedLiveController.expected_budget` 是冻结代码常量；`config/budgets.yaml` 是声明镜像。任何配置改动会被逐字段比较与闭包摘要双重发现，但“配置改了而代码常量没改”时以代码常量为准——这是有意的 fail-closed 设计，不是双源漂移。

---

## 3. G4-B 残余

| ID | 残余 | 状态 | 处置 |
|---|---|---|---|
| B-R1 / 矩阵 B03 | DSH 0.2.2-rc.2 无权威 merged tool registry/schema 导出 | **UNVERIFIED** | Controller per-dispatch tool-schema 白名单兜底；不得声称 registry 只有 `skill_lookup` |
| B-R2 / 矩阵 B07 | `session-title` 未禁用，可能产生辅助 LLM 调用 | **BLOCKED** | 本轮真实 run 0 额外请求；必须保留 Controller per-dispatch Reserve/Claim 兜底 |
| B-R3 | `session-log-deepseek` 仅 `config.enabled=false` | **PARTIAL** | 无外发路径 + 无观测外发，但不证明插件逻辑 inert |
| B-R4 | `mcp-resources` 外部资源面 | **UNVERIFIED** | 未见 server 配置；无外发观测 |
| B-R5 | 跨 worker 二次 build stage 的字节可复现 | **UNVERIFIED** | 本轮只重算既有 stage（两次一致），未重编译 |
| B-R6 | `config/budgets.yaml` 无运行时解析代码 | 观察 | 真实限额在 stage 模板；manifest 同时记录两者 |
| B-R7 | Adapter「实际加载」无 JS `inspect.getfile` | 限制 | 加载自报 + 产物/构建元数据/策略三方字节一致 |
| B-R8 | G4-A 改码使冻结 manifest 在 HEAD 上 verify 失败 | 设计如此 | B11 的 fail-closed 行为；不是缺陷 |
| B-R9 | 证据在本地 worktree `2f1e41f`（`src=cf40c6b`）产生 | 已记录 | main 对应代码提交 `c29cabc` |
| B-R10 | 宿主 1 项 host-only 测试失败（G3-D 类） | 环境 | 未改测试 |
| B-R11 | raw-UDS 逐阶段 `podman exec` exit code 记录不完整 | 证据卫生 | 每阶段返回帧/payload 已落盘；G4-E 未补 |
| B-R12 | P2-DISK/USERNS/RUN-IDENTITY | 未变 | 维护者待决 |

---

## 4. G4-C 残余（L1-only PARTIAL 组）

| 行 | 场景 | 为什么 PARTIAL |
|---|---|---|
| C04 | Claim 后改 Prepared | 决定性断言在 L1-HOST；容器内无法由 Candidate 远程触发，未新增产品测试钩子 |
| C05 | 发送前改 wire 字节 | 同上；controller 只构造一次字节 |
| C10 | synthetic 429/5xx/timeout/eof | Fake 场景注入为 L1；未跑容器 429 |
| C11 | missing/partial/duplicate/conflicting usage | 控制器层 L1；未跑 L2 fake-mode |
| C14 | 预算软/硬阈值 | gate 阈值 L1；未主张供应商侧额度 |
| C15 | 未知 pricing / real route | real route 恒 BLOCKED；价格核验是 G4-H/G5 人工工作 |
| C16 | Session resume 不重发 | 无 G4-C 真实 DSH resume run；引用 G3-D D2-11（frozen src 不同） |

**其他 C 残余**：

- **C-R1**：容器内只能独立复算 `src/**`、`fake/**`；`config/`、`plugins/`、锁文件由 Launcher 声明。
- **C-R2**：`authorize` 与 `transport.dispatch` 之间仍有 Python 内存窗口；consume 时重算字节 SHA 收窄，不是 OS 级保证。
- **C-R3**：`g4c-policy.json` 与 send journal 位于 `/work/state`（root 0700），不是独立签名账本。
- **C-R4**：仅 synthetic fixture route；真实 route/TLS/DNS/proxy/redirect/计费未证。
- **C-R5**：Broker hang/timeout 由既有 30s deadline 兜底，未单独做 hang 注入（stop 已 L2）。
- **C-R6**：G3-D frozen-src 断言因授权改码必然失败；deselect 处理。
- **C-R7**：价格 3.00/10.00 是工程硬顶，不是供应商额度；synthetic 费率不是真实价格。

---

## 5. G4-D 残余与 F1–F5 自查缺陷

### 5.1 残余

| ID | 残余 | 状态 |
|---|---|---|
| D05 | G4-C synthetic controller 没有“人类 revocation 文件”运行入口；撤销在 authorization/attempt 层验证 | **PARTIAL**；端到端容器撤销属 G4-H |
| D09 | host root 不受 `RLIMIT_NPROC`；只证明容器 cgroup `pids.max` | **PARTIAL** |
| D13 | DSH 无可枚举 merged registry；E5-P04 子集 UNVERIFIED | **UNVERIFIED** |
| D-R1 | P2-RUN-IDENTITY：同 UID 旧 run 拒绝依赖 mount/DAC；若目录被放宽为 candidate 可写则失效 | 维护者待决 |
| D-R2 | D02 本 run 无 attempt/receipt（trusted 从未处理请求）；in-flight 保守由 D05 补 | 已说明，未伪造 |
| D-R3 | 真实 Cleanup 需要 host root/podman；OC19 环境不可用 | 环境 |
| D-R4 | 哨兵值唯一，扫描器排除定义处；不能证明“真实 Key 永不泄漏” | E5-P05 FULL BLOCKED |

### 5.2 F1–F5（实现期发现并修复的自身工具缺陷，非产品安全缺陷）

| ID | 缺陷 | 复现 | 修复后证据 |
|---|---|---|---|
| F1 | `podman pause` 注入 hang 后容器卡在 `paused/container state improper`，`rm -f` 无法删除 | D02 首轮容器残留、后续 preflight 失败、rootfs 出现空 `g4c` 目录 | 改为 host 侧 `SIGSTOP` 容器 init（`state=T` 复核）；D02 终态容器空 |
| F2 | `podman inspect` 输出 8 KiB 截断导致 JSON 解析失败，uid_map/mountinfo/cgroup 证据为空 | D01 首轮 `containers-up.json` 无 inspect/proc | `max_stdout=1 MiB`；D01/D15 记录完整 |
| F3 | `min(value, RLIM_INFINITY=-1)` 使 rlimit soft 变成 infinity，CPU/AS/NOFILE 未真正生效 | D09 首轮 CPU 20s 未杀、AS/NOFILE 假通过 | 显式处理 `RLIM_INFINITY`；CPU `-24`、AS `1`、NOFILE `2` 真实发生 |
| F4 | 从 `podman exec` PID namespace 内 `os.kill(1,SIGSTOP)` 未停止 init（状态仍 `S`） | D02 第二轮仍完成一次 send | watchdog 对 host `/proc/<container-init>` 发 SIGSTOP 并读 `/proc/<pid>/stat` 复核 `T` |
| F5 | `/proc/<pid>/environ` 以 NUL 分隔，按行解析只得到首个变量名 | D03 首轮 `env_names=['PYTHONPATH']` | 按 NUL 切分；D03 列出 11 个真实变量名 |

修复提交：`718b44e`、`4622389`、`0975412`、`2019c49`、`d8e71a8`、`d3d429c`；`d8a8dc8` 为任务要求的 `feat:`。未 amend。

---

## 6. 环境限制与证据卫生

### 6.1 Host

| 现象 | 分类 | 处置 |
|---|---|---|
| frozen-src 断言失败 | **冻结基线断言**（G4 授权改码） | 显式记录 + deselect；不修历史测试 |
| D15 降权后 3.11 解释器不可穿越 | **host-only 解释器路径** | 用 G4-D 的 conda 解释器重跑：1 passed；host full 中 deselect |
| config 文件 0644 vs OCI 0444 | **host checkout mode**（G3-D OPS-P2-b） | 不 chmod 工作树“修绿”；OCI 通过 |
| sandbox 子进程硬编码 `/project` | **host-only PYTHONPATH**（G3-D OPS-P2-b） | 不修测试；OCI 与独立 probe 通过 |

### 6.2 固定 OCI

| 现象 | 分类 | 处置 |
|---|---|---|
| rootfs 无 `git`/`tar` | 固定 rootfs 限制 | 18 项与 git/tar 相关测试 deselect；host full 覆盖 |
| rootfs 无 `/bin/sh` | 固定 rootfs 限制 | c05/D07 的 shell 用例 deselect；root replay 中 A01 shell 也 deselect |
| trusted-dir 必须非 candidate uid | G4-A 新增的安全不变量 | uid 65534 下 283 项 root-only 测试无法运行；用 uid 0 replay 覆盖 294 项 |
| 无 `CAP_CHOWN` | cap-drop ALL | A07 candidate-owned 1 项 deselect；host root 覆盖 |

**结论**：OCI 原始 27 failures 全部为环境不兼容，过滤后 0 failed；不是产品断言失败。完整清单见 `artifacts/g4/e/regression/oci-env-deselects.json`。

### 6.3 其他证据卫生

- `artifacts/` 被 gitignore；提交只含 docs/matrix/builder。
- SQLite 在 Packet 中为只读字节副本，builder 未打开。
- G4-D 未构建正式 Packet（E 职责）；D04 的 Packet 列记 `NOT_BUILT`。
- 仓库 secret scanner 在 `tests/integration/g4_d/test_d07_live_entrances.py` 报 2 条 `DEEPSEEK_API_KEY=SENTINEL`；这是**符号常量**，不是字面凭据（scanner 掩码长度 9），已登记为 false positive。G4-D 哨兵扫描 8,815 文件 0 命中。

---

## 7. 维护者待决 P2（本轮不批准）

| ID | 内容 | 当前状态 | 维护者动作 |
|---|---|---|---|
| **P2-DISK** | Candidate `/work/session` 是 host bind mount，无磁盘硬配额 | 未修复 | 真实凭据长期运行前加配额/更强隔离，或明确签收风险 |
| **P2-USERNS** | 内核允许嵌套 user namespace | 未修复（内核行为） | 选择 seccomp/禁 userns，或明确签收 |
| **P2-RUN-IDENTITY** | `SO_PEERCRED` 只鉴别 UID，不是 per-run token | 未修复 | 决定是否加 per-run capability/独立 UID；不得声称已有 per-run OS 身份 |

**明确声明**：G4 无 Key 工程继续**不构成**对以上任一 P2 的批准、接受或风险签收。`G4-H-05` 仍 `BLOCKED`。

---

## 8. G4-H 六项人工阻断（全部 BLOCKED）

| ID | 人工专属项 | 状态 |
|---|---|---|
| G4-H-01 | 对精确冻结提交/依赖/配置/路由/预算做独立二次审阅 | `BLOCKED / PENDING_HUMAN_ACTION` |
| G4-H-02 | 人类在 Agent 不可写域创建/保护审批信任根、Ed25519 公钥注册/轮换/撤销、私钥离线保管 | `BLOCKED / PENDING_HUMAN_ACTION` |
| G4-H-03 | 选择并部署独立 Key Broker/可信 Egress，最小权限、可撤销、供应商作用域 | `BLOCKED / PENDING_HUMAN_ACTION` |
| G4-H-04 | 核实官方模型 ID/Endpoint/价格/Usage/Tool/Stream/供应商额度 | `BLOCKED / PENDING_HUMAN_ACTION` |
| G4-H-05 | 独立执行 E5-PreLive 全项安全 Review 并签收 P2 | `BLOCKED / PENDING_HUMAN_ACTION` |
| G4-H-06 | 单独签发一次范围严格限定的 G5 试验授权 | `BLOCKED / PENDING_HUMAN_ACTION` |

详见 `docs/M0_G4_HUMAN_HANDOFF.md`。任何一项都不得由 Agent 在 Markdown 中写 `APPROVED` 替代。

---

## 9. 处置结论

1. 本轮 G4 无 Key 工程**没有 P0/P1**；但这是 Owner 自查，最终裁定由独立 Reviewer 出具。
2. 仍有 **10 PARTIAL / 2 UNVERIFIED / 5 NOT_RUN（E06..E10）/ 6 BLOCKED**；不得合并为“全绿”。
3. **E5 FULL 未通过**；`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
4. G4-H/G5/G6/Live 均未授权；G5 只能在 G4-H 全部通过后由维护者另发授权。
5. **STOP**：不请求/不执行独立复核；由 Lead 指派未参与实现的 Reviewer。
