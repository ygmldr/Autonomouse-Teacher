# OPEN BLOCKERS — M0 v0.6 G0 基线（2026-11-15 UTC）

- 任务：`task-58`/G0；审计者：`verify2`；性质：只读静态记录。**未运行项目代码/pytest/TS/容器；0 真实 Key/模型/网络；LiveGate/E1–E5/Live 仍 BLOCKED，总体 DECISION PENDING。**
- 基线：HEAD `abbc6bcd2a2128456627d9370465323b505aafd9`（docs-only）；实现 SHA **`87f44e1227f38e454c4dc418b0e289df85721fb5`**；worktree clean；169 tracked files。
- 详细来源与逐项 file:line：[`M0_G0_BASELINE.md`](M0_G0_BASELINE.md)；证据：[`artifacts/g0-baseline/`](../artifacts/g0-baseline/manifest.json)。

## 1. 当前 Gate 阻塞总表

| Blocker | Gate | 优先级 | 当前事实（静态） | 解除所需证据/动作 | 责任方 |
|---|---|---|---|---|---|
| BLK-G1-AUTH-02 | G1 | **P0** | `ed25519.py` 无可信公钥子群/identity/low-order 准入；trusted key 加载仅校验 hex（`ed25519.py:77-89,127-140`；`authorization.py:211-223`） | 严格公钥注册/加载拒绝 identity/小阶/非规范点；AUTH-02 构造负测 + 正向 RFC8032 向量；独立复核 | 实现 + Security Reviewer |
| BLK-G1-AUTH-05 | G1 | **P0** | `authorization.py:345,367-369` 使用 `int(...)`，可接受 `True`/字符串/float；无 `type(x) is int` | 严格整数类型校验 + AUTH-05 定向回归（`"10"`, `10.4`, `True` 均拒） | 实现 + Reviewer |
| BLK-G1-AUTH-06 | G1 | P1（矩阵未列，待 Lead 裁定） | `approver` 解析在 try 内失败后未赋值，`:418` 可触发 `UnboundLocalError`（`authorization.py:275-288,418`） | 异常路径明确 `approved=False`/安全拒绝；AUTH-06 回归 | 实现 + Reviewer |
| BLK-G1-AUTH-08 | G1 | P1 | Controller 只比较 `host_ports`（`live_controller.py:106-126`），未校验完整 route/egress policy | 离线完整 policy 检测；AUTH-08 回归；仍不新增 Live 入口 | 实现 + Security Reviewer |
| BLK-G1-OBS-01/02 | G1 | P1 | reasoning 仅 AUTHORITATIVE 分支拒绝 `>output`；独立 additional reasoning>output 不可表示（`observation.py:133-142,207-224`） | 按 route billing policy 语义化约束；OBS-01/02 定向测试 | 实现 + Accounting Reviewer |
| BLK-G1-OBS-03 | G1 | **P0** | 静态未复现 v0.6 所述“只有 cache_read 仍折扣”：输入不完整时 `cache_read=0` 且用 reserved bound；ledger 对 estimated 成本有 `max(cost,reserved_cost)` 地板（`observation.py:227-237`；`ledger.py:256-276`）。残余路径（完整 input + 缺失 output + actual/provider_invoice）需测试 | 定向 OBS-03 测试证明任何 PARTIAL/MISSING 不低估保守上界；若保留折扣须 Route Policy 显式批准；不得写 PASS 直到独立复跑 | 实现 + Accounting Reviewer |
| BLK-G1-OBS-05/06 + INT-15 | G1/G2 | **P0** | `deliver_observation` 信任 caller-supplied observation；无来源签名/route/model/request 绑定；`provider_invoice` 可自行声明（`observation.py:279-324`） | 可信 Egress 来源认证 + route/model/request digest 校验；伪造 observation 不能结算；INT-15/OBS-05/06 定向证据 | Security + Accounting |
| BLK-G1-WD-03/04 | G1 | **P0** | `watchdog.py:256-272` 异常路径只 kill tree 后重抛；cleanup 非 `finally`，cleanup 异常/超时未统一 `SECURITY_BLOCKED`；测试 `test_watchdog.py:166-173` 当前期望 RuntimeError | 统一 finally/外部 supervisor 清理；kill+absence；cleanup 失败→BLOCKED；WD-03/04 回归 | Security + Runtime Reviewer |
| BLK-G2-UNIFIED-ID | G2 | **P0** | `egress.py` 用 `eg-`（含 reservation，`:103-108`）；`observation.py` 用 `call-`（预留前，`:268-271`）；ledger 只接受 `call-`（`:122,134-160`） | ADR-002 统一 CallIdentity + 全链 ID；egress/broker/observation/ledger 联动；INT-01 真 Broker+SQLite 证据 | Architecture + Accounting/Security |
| BLK-G2-CLAIM | G2 | **P0** | broker `reserve` 返回 `dispatch_allowed=True`；无原子 claim/单 Attempt 许可；`bind_call` 只是链接（`broker.py:151-167,196-227`） | 持久 reserve+claim：一条 Reservation 只许可一次 Provider Attempt；INT-04/05/06/17 跨进程/崩溃/重放证据 | Accounting + Reviewer |
| BLK-G2-RESERVATION-VALIDATION | G2 | **P0** | Egress 仅检查非空 `reservation_id`（`egress.py:129`），无 Broker/ledger 查询；伪造/未绑定 reservation 无法在 Egress 内被拒 | Dispatch 前可信 Broker claim/校验；INT-02/03 证据 | Security + Accounting |
| BLK-G2-PERSISTENT-ATTEMPTS | G2 | **P0** | `EgressBoundary._streams` 为内存 dict，attempts 内存计数（`egress.py:116-123,152-160`）；无持久/跨进程去重 | 持久 claim/attempt 状态；INT-04/05/17（跨进程、重启、同 ordinal 重放） | Accounting + Security |
| BLK-G3-F7-NETWORK | G3 | **P0** | PR2 evidence：no-guard `fixture_invocations=1`（`artifacts/m0-runtime-integration/manifest.json:74-77`）；外部 egress/Key 边界未实测；当前 runtime 仍 hard BLOCKED | G3 独立执行：受控 Fake Provider、真实 DSH 直连被拒、OS direct-connect 负测、BR-06/10 证据；不得在 G1/G2 内以插件替代 | Runtime + Security；需 Lead/维护者批准 G3 |
| BLK-G4-HUMAN-BOUNDARY | G4 | **P0** | 人类授权/私钥托管/撤销/OS 身份/部署均无证据；`TrustedLiveController` 仍 inspect-only/BLOCKED（`live_controller.py:38-44,128-147`） | 外部独立授权边界、Key Broker、只读 Profile、人类签核；E5-P01–P05 真实验收 | 维护者 + Security |
| BLK-G4-EGRESS-KEY | G4 | **P0** | 外部 egress/Key Broker 未部署；OCI `socket()` 被拒（PR4a LIMITATION）；真实 wire/retry/cache 未观测 | 受控外部 proxy/Key Broker + 假 Key OS 负测；真实 egress 证据；不得把 descriptor/mock 当真实 wire | 维护者 + Ops/Security |
| BLK-G4-ROUTE-POLICY | G4 | P1 | `live_controller.py:69`/`egress.py:24-28,67-78` 默认 OpenCode Go；OpenCode Go 仅 INTERNAL-TEST-ONLY，不是官方 DeepSeek 主路由 | 维护者裁决官方主路由/模型 ID；若使用 OpenCode Go 仅作内部测试且不得替代 E1–E5 强制验收；配置/政策证据 | 维护者 + Lead |
| BLK-G5-HUMAN-APPROVAL | G5 | **P0** | 无维护者单独批准；0 真实 Key/模型调用；不得由 Agent 自批/自动进入 | 维护者显式批准（仓库外）、专用可撤销低额度 Key、预算/usage 上限；LIVE-00/01 等 | 维护者 |
| BLK-G6-E4-E5 | G6 | **P0** | E4 配对/E5-Full 未开始；E5-PreLive 整体未 PASS | E4 6 对真实策略比较、E5-Full 逐项验收、独立最终冻结审计 | 维护者 + Verification |
| BLK-EVIDENCE-DRIFT | G0 | P3 | O-PR2-1/O-PR4A-1/O-FINAL-1/O-FINAL-2 worktree-bound evidence 漂移；历史 evidence 字节未改；旧 manifest 字节不重写 | 后续 manifest/errata 绑定 commit/blob 身份或补说明；不改旧证据 | owner/Lead 归档 |
| BLK-EVIDENCE-NAMING | G0 | P3 | O-PR4B-1：PR4b 使用 artifact-hashes 而非 evidence.sha256，8/8 OK；stage 未纳入 checksum | 后续统一 manifest/checksum 规范；不阻塞功能 | broker-docs/Lead |
| BLK-USAGE-INVOICE | G1/G4 | **P0**（真实账单） | PR4b 仅离线 ProviderObservation/usage 映射；真实 provider wire/usage/invoice 未验证；悬而未决 | 真实 provider 响应级 usage vs invoice 对账证据（G4/G5）；在之前不得声称账单已核对或硬预算已证明 | Accounting + 维护者 |

## 2. 逐步解除顺序（建议）

1. **G0**：Lead 接受本 baseline + source inventory；确认 P0/P1 划分（尤其 AUTH-06 是否升 P0），冻结 G1/G2 工作范围。
2. **G1**：最小 PR（AUTH-02/05/06/08、OBS-01/02/03/05、WD-03/04）→ 定向回归 + 新实现 SHA + 独立审阅；LiveGate 保持 BLOCKED。
3. **G2**：ADR-002 统一 ID；Broker 持久 claim；Egress→Broker→Observation 真 SQLite/跨进程闭环；INT-01/04/05/06/10/15/17 独立复跑。
4. **G3**：经 Lead/维护者另批后，做真实 DSH + 受控 Fake Provider + OS 直连拒绝；F7 外部闭包。
5. **G4**：维护者部署外部安全边界并签核；E5-P01–P05。
6. **G5/G6**：维护者单独批准真实模型；E4/E5-Full；最终独立审计与决策。

## 3. 明确不解除/不得绕过的边界

- 不得用 `--live`、Markdown、环境变量、Agent 自签/自批解锁 Live；`LiveGate`/`scripts/run_live.sh`/Adapter 当前 hard BLOCKED 不得删除。
- 不得把静态 CONFIRMED、历史离线 PASS、不同 commit 的测试数相加，写成当前 HEAD 的 G1/G2/G3/Live PASS。
- 不得使用真实 Key/公开网络/宿主敏感挂载做 G0–G2；G3 也仅允许受控本地测试端点/Fake Provider；G5+ 必须维护者另行批准。
- OpenCode Go 仅 INTERNAL-TEST-ONLY；真实 Key 仅在仓库外 launcher 注入；US$10 硬/US$3 软/≤50 次上限；当前未使用。
- 任何 P0 未关闭 → 不进入下一 Gate；任何真实 wire/invoice 未验证 → 不声称账单/硬预算 PASS；总体保持 **DECISION PENDING / Live BLOCKED**。
