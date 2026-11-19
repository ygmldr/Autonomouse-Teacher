# 人工签核模板 — G4-H0 / 受信部署（不是授权凭据）

- **文档性质**：空白模板 + 填写说明。**本文件不是授权、不是批准、不是 Live 许可、不是机器可读凭据。**
- **签署方**：仅限项目维护者（人类）本人，在**仓库外**、独立权限域中完成。**Agent（包括 Lead / Implementer /
  Reviewer Agent）不得代填、代签、代勾“APPROVED”，也不得把本模板或任何 Markdown 当作解锁条件。**
- **基线**：`3e7afee077845a071cd364e93ab209cac20b2d5f`；相关设计见
  [`DEPLOYMENT_RUNBOOK.md`](DEPLOYMENT_RUNBOOK.md)、[`TRUST_BOUNDARY_DIAGRAM.md`](TRUST_BOUNDARY_DIAGRAM.md)、
  [`E5_PRELIVE_FULL_CHECKLIST.md`](E5_PRELIVE_FULL_CHECKLIST.md)。
- **当前状态**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`
  （`docs/M0_G4F_REVIEW_ERRATA.md:89-98`）。在真实签署发生前，本模板所有字段保持 `PENDING_HUMAN_ACTION`。

---

## 0. 使用规则（先读，再填）

1. **谁可以填**：只有维护者本人或其明确授权的受信 Operator（仅在维护者口述/书面指令下代填文字，
   签名仍必须维护者本人完成）。Agent 产出只能作为“待审草稿”，且必须标注 `DRAFT_BY_AGENT`。
2. **填在哪里**：签署后的完整记录保存在**仓库外**证据根（例如
   `<TRUSTED_DEPLOY_ROOT>/signoff/<release-id>.md` + 分离的签名/授权文件），**不得**把含真实身份、
   真实 Key 引用或真实授权字节的内容提交到 Git。
3. **模板不是凭据**：模板只记录人类决策的结构化证据。真正让 Controller 接受的是仓库外
   `at-m0/execution-authorization/v1` 签名文件 + 公钥注册 + 撤销状态 + 单次消费记录
   （`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:62-87`；`docs/M0_G4_A_AUTHORITY_CONTRACT.md:277-286`）。
4. **逐项填写**：空白字段不得留空后签署；不适用项写 `NOT_APPLICABLE` 并说明理由；未验证项写
   `UNVERIFIED` 并给出维护者决定（接受/补测/阻断）。
5. **示例值仅为占位符**：`<...>` 一律是占位，不是可执行值；不得填真实 Key、真实 Secret 或个人数据。
6. **签名与文件分离**：签署动作 = 用维护者正式 Ed25519 私钥对“除 signature 外字段的 canonical JSON”
   签名；本模板表格只是人读摘要。**不得**把本模板的“已填写”当成签名。

---

## 1. 签核模板（复制到仓库外填写）

```text
文档性质：人工签核记录（非授权凭据）        填写状态：DRAFT / FINAL
签署方（维护者）：____________________________  身份/部门：____________________
独立复核人（未参与实现）：____________________  独立性声明：未参与实现/测试/证据生成  [ ]
日期（UTC）：________________________________  发布 ID：________________________
```

### A. 待审身份（必填；全部为完整值，不允许“前 8 位”）

| 字段 | 填写值 | 证据位置（仓库外路径 + SHA-256） | 复核结果 |
|---|---|---|---|
| 被审 Git 提交（完整 40 hex） | `________________________________________` | | `PASS / PARTIAL / BLOCKED` |
| docs 提交 / Packet 构建 SHA | `________________________________________` | | |
| 工作区状态（clean，0 行） | `git status --porcelain -uall = ____ 行` | | |
| 5 个绑定根（完整值） | `code_sha256=________________________________________` | | |
|  | `lock_sha256=________________________________________` | | |
|  | `runtime_sha256=________________________________________` | | |
|  | `plugin_sha256=________________________________________` | | |
|  | `merged_profile_sha256=________________________________________` | | |
| 完整文件清单 SHA（inventory） | `________________________________________` | | |
| 配置文件 SHA（merged profile/target patch/budget mirror） | `________________________________________` | | |
| 依赖摘要（uv.lock SHA + deps canonical tree + 关键 wheel hashes） | `uv.lock=________________`；`deps_tree=________________` | | |
| rootfs/stage/deps 身份（digest/tree/manifest） | `rootfs=________`；`stage_manifest=________`；`stage_tree=________` | | |
| DSH runtime / 插件版本 + 实际加载模块证明 | `runtime=________`；`version=________`；`loaded_modules=__/__` | | |
| 工具/插件清单（registry evidence） | `________________________________________` | | |
| 允许命令（精确 argv） | `________________________________________` | | |
| 允许路由（route_id/provider/model/endpoint/method/exact_path） | `________________________________________` | | |
| 预算与次数（soft/hard/per-call/max_calls/max_steps/max_dispatch_attempts/deadline） | `________________________________________` | | |
| 授权有效期（issued/not_before/expires；≤24h） | `________________________________________` | | |
| 授权 ID（authorization_id） | `________________________________________` | | |
| 撤销方式（revocations 文件/位置/生效检查点/操作人） | `________________________________________` | | |
| 单次消费记录位置（use-records 目录） | `________________________________________` | | |
| 独立复核人姓名/报告 ID/日期 | `________________________________________` | | |
| E5 PreLive Full 状态（P01..P05 + FULL） | `P01=__ P02=__ P03=__ P04=__ P05=__ FULL=__` | [`E5_PRELIVE_FULL_CHECKLIST.md`](E5_PRELIVE_FULL_CHECKLIST.md) | `BLOCKED / PARTIAL`（当前必然） |
| P0/P1/P2 发现与处置 | `P0=__ P1=__ P2=__`；逐项决定：`FIX/ACCEPT/BLOCK` | [`A3_REFS.md`](A3_REFS.md) / G4-F errata | |
| 已知 UNVERIFIED 项及补偿控制 | `________________________________________` | Runbook §12 | |
| 发布 Packet 位置/哈希/不可变声明 | `________________________________________` | | |

### B. 维护者决定（逐项勾选；不得由 Agent 代勾）

```text
[ ] 我确认以上 SHA/哈希由我在独立权限域复算，未仅依赖 Agent 提供的 manifest。
[ ] 我确认 5 个绑定根与实际运行内容一致；任何后续变化使本次签核失效。
[ ] 我确认允许命令/路由/模型/端点/工具白名单与冻结清单逐字段一致。
[ ] 我确认预算与次数只是 M0 工程目标；若供应商无侧强限制，我不将其表述为“绝对硬封顶”。
[ ] 我确认有效期 ≤24h（建议更短）、单次消费、撤销路径与责任人均已就绪。
[ ] 我确认独立复核人未参与实现/测试/证据生成，且其结论为（PASS / PARTIAL / BLOCKED）。
[ ] 我确认当前 E5_PRELIVE_FULL 仍为 BLOCKED_PENDING_HUMAN_DEPLOYMENT（不是 PASS）。
[ ] 我确认本次不启动 G4-H1/H2/G5，除非另发单独的人类授权。
[ ] 我确认本模板不是授权凭据；真实授权是仓库外签名文件。
```

### C. 签署区（维护者本人；禁止 Agent 填写）

```text
Maintainer name (print):        ______________________________
Signature (detached Ed25519):   key_id=________________________
                                signature_hex=__________________  ← 以分离文件保存，不写入仓库
Signed at (UTC):                ______________________________
Separate authorization file:    path=___________________________  sha256=________________
Independent co-reviewer:        name=___________________________  date(UTC)=_____________
Supersedes (auth/release ID):   ______________________________  (none / 上一版)
```

### D. 撤销登记（签署后若失效/撤销时填写）

```text
Revoked at (UTC):               _____________________________
Revoked by (human):             _____________________________
Reason code:                    LEAK / DRIFT / OVERRUN / INCIDENT / OTHER:____________
revocations.json updated:       [ ]  sha256=__________________
In-flight disposition:          PENDING_CONSERVATIVE / SETTLED / FAILED / NONE
Evidence root:                  _____________________________
```

---

## 2. 填写说明（每类字段的判断标准）

| 字段类别 | 合格标准 | 常见错误（应拒签） |
|---|---|---|
| Git SHA | 完整 40 hex，可从冻结提交复现父链；工作区 clean | 只写短 SHA；工作区有未提交改动 |
| 5 个绑定根 | 由 15 组件 canonical 规则聚合；Reviewer 独立复算 | 直接抄 Agent 的 manifest 未复算 |
| 配置 SHA | merged profile/target patch/budget mirror 全量字节摘要 | 只给文件名或版本号 |
| 依赖摘要 | `uv.lock` + deps canonical tree + wheel hash（如涉及） | 只说“依赖已锁定” |
| 允许命令 | 精确 argv 数组，不含 shell 展开/`eval`/通配 | “运行 pytest 即可”这类模糊描述 |
| 路由 | route_id/provider/model/endpoint/method/exact_path 逐字段；real route 模板在人工核验前恒 BLOCKED | 写“默认模型”“自动选择” |
| 工具白名单 | 实际 merged registry 证据或明确 `UNVERIFIED` + 补偿控制 | 把旧 profile 行/测试 fixture 当 merged registry |
| 预算/次数 | soft/hard/per-call/max_calls 等逐项数值；明确“工程目标”性质 | “不会超过 $10” |
| 有效期 | `issued ≤ not_before < expires`，≤24h，零 skew | 永久有效/无有效期 |
| 撤销方式 | 谁、在哪里、改哪个文件、何时生效、如何核对 | “出问题就停”无具体路径 |
| 独立复核 | Reviewer 未参与实现/测试/证据生成；有报告 ID；从冻结 SHA 复跑 | Owner 自评当复核 |
| Packet/证据 | append-only、哈希可复验、不覆盖历史字节 | 口头“证据都有” |

---

## 3. 拒签条件（出现任一即不得签，先处置/补测）

1. 无法给出完整 40 hex SHA，或工作区不 clean，或 5 个绑定根任一无法独立复算。
2. 依赖/镜像/工具清单不完整，或 merged DSH registry 仍 `UNVERIFIED` 且无维护者明示补偿控制（E5-P04）。
3. 真实 Provider 价格/Usage/额度/Key 作用域未核验，或试图用 synthetic fixture 价格替代
   （`docs/SECURITY_APPROVALS.md:31-42`）。
4. E5 PreLive 任一项被写成 `PASS` 但实际为 `PARTIAL/UNVERIFIED`（尤其 E5-P04、F4 candidate-crash、
   E5-P05 watchdog 执行腿）；E5 FULL 被表述为 PASS。
5. 授权位于仓库内、使用测试种子、由 Agent 生成/代签、或 Markdown/环境变量/`--live` 被当作解锁路径
   （`docs/M0_G4_A_AUTHORITY_CONTRACT.md:230-243`）。
6. 无撤销路径、无单次消费、无有效期，或并发消费 P2-03 未修复且无明示接受（`docs/M0_G4F_REVIEW_ERRATA.md:152-158`）。
7. 预算被表述为“绝对硬封顶”，或没有供应商侧限制/降级计划却承诺费用上限。
8. 真实 Key 曾进入仓库/镜像/Stage/Prompt/Trace/日志/Receipt/JUnit/Packet/候选 env，或无法排除。
9. `LiveGate` 的 `BLOCKED` 语义被改动，或出现 `--live` 旁路、第二条发送路径、未批准工具/路由。
10. 缺少独立复核人，或复核人参与了实现/测试/证据生成（独立性不成立）。
11. Packet/证据被改写、sidecar/路径/reasons 缺陷未披露（P2-01/02/07），或声称“全量一致”。
12. 任何“已部署/G5 已获批/E5 Full PASS/M0 GO”等未经人类决定的文字。

---

## 4. 签后失效条件（自动失效，无需额外动作）

以下任一发生，本次签核立即失效；重新部署前必须重新复核+重新签名：

- 代码、依赖、镜像/rootfs/stage、DSH runtime/插件、merged profile、工具清单、route/model/endpoint、
  预算/policy、价格快照、Controller 常量发生任何变化（`docs/M0_G4_A_AUTHORITY_CONTRACT.md:178-226`）。
- 授权过期、撤销、被单次消费；或 use-record 出现异常/损坏（存在即视为已消费，fail-closed）。
- Key 轮换/撤销；Provider 侧价格或额度变化影响预算判断。
- 出现未授权出站、预算异常、未知 Usage、容器/进程残留等事故信号 → 立即 Kill Switch 并暂停。
- 独立复核结论被后续证据推翻（append-only errata 更正）。

---

## 5. 明确禁止（Agent 侧）

- Agent **不得**在本模板任何位置填写“签名/APPROVED/AUTHORIZED”；不得代维护者勾选；不得生成正式私钥。
- Agent **不得**把本模板、Packet、`SECURITY_APPROVALS.md` 或任何 Markdown 作为授权依据或 Live 解锁条件。
- Agent **不得**在提交信息、日志、证据中写入真实 Key/Secret/个人数据；示例仅可使用明显占位符。
- 本模板中的真实填写值（若曾填写）**不得**提交到 Git；仓库内只保留空白模板与说明。
