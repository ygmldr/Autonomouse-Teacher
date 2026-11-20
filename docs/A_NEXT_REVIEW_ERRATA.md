# A-NEXT — 最终 Review Errata 归档与 Packet v3 Lead 冻结声明（append-only）

- **文档 ID**：`A-NEXT-REVIEW-ERRATA-v1`
- **生成时间（UTC）**：`2026-11-20T21:47Z`
- **性质**：**append-only 档案**（只新增本文件；不改任何已提交文件/Packet 字节；不 push）。
  本文件归档最终 no-key 裁定、Lead 对 Packet v3 的冻结声明、残余清单与分支/提交清单。
- **base**：`fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`
- **集成冻结 SHA（code/docs freeze）**：`e1b48ee33d72205395d5f14e6c28c79e969e6586`（`work/a-next`）
- **Reviewer 报告**：`docs/A_NEXT_INDEPENDENT_REVIEW.md` @ `docs/a-next-review`
  `220171cb6cc39ec12fe1eea26b641fd06d9f9f03`；**1636 行**；文件 sha256
  **`9b833c6f4480346f250e2ff423fbd03e45c6e8de73ac84bea1651d169c6f55a3`**（`git show 220171c:… | sha256sum` 实测）。
- **当前状态常量（未变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

## 1. 最终裁定归档

> **最终裁定：`PASS`（限 no-key 工程与证据范围）。P0 = 0；P1 = 0。**

依据（Reviewer §17.7，摘要）：A1/A2 实现与测试独立复跑通过；A-PR0 v3/P2-A0-1 闭环；A3 Registry 诚实
`UNVERIFIED` + 攻击矩阵；A4/R-REV6 Reviewer 独立 OCI L2 PASS（14/14、T0=T1、digest 11/9）；A6 文档/人类交接
与 append-only 更新；集成树 `git diff fd1d3a6..e1b48ee` = **69 files / +17298 / −22**、冻结件零改、无未审受保护
变更；Host **1649 tests = 1624 passed / 7 failed / 18 skipped**（6 ENV + 1 EXISTING，**0 REAL_REGRESSION**）；
Packet v3 身份/全树/mutation（20/20）/T0-T1/incident/exclusions 全通过，且可由冻结 builder **逐字节复现**。

**本 PASS 明确不构成**：`E5-PreLive Full`、`E5-P04`、B03 关闭、G4-H1/H2 已部署、G5 已获批、G6 GO、
M0 GO、Live/生产安全或任何部署授权。附属状态：`B03/E5-P04 = UNVERIFIED`；`A2-01..03 = NOT_RUN`；
`A3-01/A3-02 = PARTIAL`；人类决策 `UNSIGNED`。

## 2. Packet v3 — Lead 冻结声明（`FROZEN_BY_LEAD`）

Lead 以本 arch 文件执行 **Packet v3 身份冻结动作**（声明式，**不修改包内任何字节**）：包内原
`status = CANDIDATE_PENDING_LEAD_FREEZE` → 本档案记录其对外状态为 **`FROZEN_BY_LEAD`**。
**人类维护者验收仍为 `UNSIGNED`**（本文件不代签、不构成人类批准）。

| 项 | 值（Reviewer §17.2 复算 / 本文件实测核对） |
|---|---|
| Packet root（相对 `work/a-next`） | `artifacts/review-packet-a-next-v3-e1b48ee33d72205395d5f14e6c28c79e969e6586` |
| `manifest.json` sha256 | `47ff93efa0b7e56f8d3a6ddb6a3c5b4e5162ecd1bfbed253b5d8d55f2a518d74`（实测一致） |
| `hashes.sha256` sha256 | `799d8db6b27ae713adc2d5c8eab2db0a89359c0169e1e44d95f3e1a9c1796330`（实测一致） |
| `payload_tree_sha256` | `20b6356220b9b759c65fb994b81c5781d015b82eff12aca34d431245a7263d50` |
| `content_sha256`（payload-only content digest） | `1ba03b4fff58b8b7e89b7241934ec9d6f530927ea0510c088ade350d78cb9883` |
| `builder_sha256` | `c5128cba8451e64ac0b98cfceec49a8330be92c7d35cd5fb9d4447b444f13a80`（== 冻结树 `scripts/a_next/build_packet_v3.py`） |
| 计数 | **payload 370 / total regular 373**（+ README/manifest/hashes；0 symlink/0 hardlink） |
| T0/T1 环境 | rootfs `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（相等）；deps `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（实测重算） |
| Stage | `stage-20261120T210101Z` manifest `b3fd4cbc…`（存在） |
| impl 身份 | `impl_sha = e1b48ee33d72205395d5f14e6c28c79e969e6586`（`impl_sha != content_sha256`，身份分离） |
| Packet name | `review-packet-a-next-v3-e1b48ee…` == 目录名 == prefix+impl_sha（verifier 强制） |
| Packet README sha256 | `5843ed24dc8801b32c4fcbc9a5d9791a0723464ac38bb0db9cd489a1545ce30c` |
| packet 内 disclosures | `payload/docs/A_NEXT_PACKET_V3_DISCLOSURES.md` sha256 `5e940fd9de1fdfa649a2799f1e612f42da66419828f0329046daecddd92eb0b1` |

**旧 `bbcb37` 包 = `SUPERSEDED / INVALID`**（Reviewer §16.6/§17.8：builder provenance/临时目录名/非确定性缺陷）：
`artifacts/review-packet-a-next-v3-bbbcb37c7468ed3f8c1d5f9ac83402fd68996c74` 仅保留作历史对照，
**不计最终证据**；不得再引用为新包/有效包。

- **冻结含义**：上述 SHA/计数/环境绑定是本档案对 Packet v3 的**最终身份记录**；任何后续修改必须产生
  **新身份/新版本**（新目录 + 新 SHA），不得原地改 v3 字节。
- **人类验收**：维护者仍需按 `docs/A_NEXT_HUMAN_HANDOFF.md` 的 D-xx 决策表另行签核；本档案与 Reviewer PASS
  均不能替代人类批准，也不能据此进入部署/G5。

## 3. P2 残余清单（Reviewer §17.7 逐条；非阻断，均已披露）

| # | P2 项 | 级别/状态 | 处置归属 |
|---|---|---|---|
| P2-1 | A-NEXT 测试 **OCI 可移植性 `NOT_VERIFIED`**：OCI filtered 1287/97F/54E/31S，151 F/E 全环境归因（缺 host git/tar、uid 65534 owner、env 断言衍生），**无产品失败** | `NOT_VERIFIED`（非产品回归） | 后续测试工具修复 + 独立 OCI 复跑 |
| P2-2 | **A2 生产强制未完成（G4-H1 BLOCKER）**：run admission 仍 opt-in；G4-H1 前 `run_admission_required` 必须成为唯一生产启动路径 | `BLOCKED`（人类 Gate） | 人类 Gate + A2 后续实现 |
| P2-3 | `A2-01..03` 真实 L2 `NOT_RUN`；`B03/E5-P04` `UNVERIFIED`（Registry 权威缺失，仅补偿控制）；`A3-01/A3-02` `PARTIAL` | `NOT_RUN`/`UNVERIFIED`/`PARTIAL` | A-PR2/A-PR3 后续 |
| P2-4 | **Human decisions 全部 `UNSIGNED`**；E5-Full/G4-H1/G5/G6/M0 均 blocked/pending；真实 Key/Broker/Egress/Watchdog 未部署 | `UNSIGNED`/`BLOCKED` | 维护者 |
| P2-5 | **INCIDENT_20261121 残余**：v1 Packet 原始字节 `LOST_IN_INCIDENT_20261121`；部分 G4-F/G4-R 原始证据仅 `PARTIAL` 恢复（provenance 已披露）；**不得宣称全程 NO_DRIFT/证据完整** | `PARTIAL/LOST`（不可消除） | 人类知情；后续证据注明恢复来源 |
| P2-6 | **Packet 状态需维护者接受**：Reviewer 时点包内为 `CANDIDATE_PENDING_LEAD_FREEZE`；本档案由 Lead 声明 `FROZEN_BY_LEAD`，人类验收仍 `UNSIGNED` | `FROZEN_BY_LEAD` + 人类 `UNSIGNED` | 维护者 |
| P2-7 | **EXISTING security finding**（LeadB `m1_teacher` 合成 sentinel 历史 blob，masked）**非 A-NEXT 回归** | `EXISTING` | 交 B 线处置（不在 A 线范围） |

## 4. P3 文档一致性建议（非阻断；下次 append-only 修订再落，不改现有文件字节）

1. `A_NEXT_IMPLEMENTATION_REPORT.md` 顶部摘要仍写“OCI filtered=NOT_RUN / 65 files”，与终态（Host 1649 tests、
   集成树 69 files）不一致；合并表未列 #8.2 —— 建议 Integrator 下次修订澄清“摘要为历史时点/以 §6/§10 为准”。
2. 证据矩阵 §5 行级 `TBD/NOT_RUN` 与 §10 终态并存 —— 建议明示“以 §10/§6 为准，§5 为冻结前快照”。
3. merge 计数建议精确为 **“8 branch tips + 2 addendum = 10 merges”**（与 Lead“9 分支”口径差异属措辞，非事实冲突）。
   > 以上 3 项不影响 Packet v3 身份/证据；本文件不修改任何既有文档。

## 5. 分支/提交清单（集成前冻结）

| 线 | 提交 SHA | subject（实测） |
|---|---|---|
| A1 | `e6f3aa6` | fix(a-next): cross-check use-record body authorization_id (P2-01) |
| A2 | `c7eb74e` | test(a-next): rebase onto A1, add R-07 body-id real-file cases |
| A0 | `bf312c8` | docs(a-next): append-only v3 clarification for baseline provenance |
| hygiene | `7d7c0a5` | test(a-next): unique hygiene helper module avoids conftest shadowing… |
| A6 | `13e39a4` | docs(a-next): G4-H1 human handoff and no-key deployment docs (no-key) |
| registry | `748fd0a` | docs(a-next): reviewer batch-2 C1/C2/C3/C5 corrections… |
| packet tooling | `ce914c1` | test(a-next): unique packet-v3 helper module avoids conftest shadowing… |
| R-REV6 | `fc935bd` | fix: A-PR3 runner fail-closed prerequisites and audit (P2-A4-2/P2-A4-3, no-key) |
| R-REV6 addendum | `0735d7b` | docs: A-PR3 R-REV6 append-only addendum — evidence-index v2 path fix and P3 scope |
| review | `220171c` | docs(a-next-review): FINAL no-key verdict PASS at freeze e1b48ee … |
| **本 errata 分支** | 本文件所在 commit（`docs/a-next-errata`，基线 `e1b48ee`） | docs(a-next): append-only final review errata and packet v3 lead freeze (no-key) |
| 集成冻结树 | `e1b48ee` | fix(a-next): make packet v3 manifest deterministic for reproducible provenance (no-key) |

**最终集成 HEAD 说明**：code/docs 冻结为 `e1b48ee`；在合并 Review 报告（`docs/a-next-review@220171c`）与本
errata（`docs/a-next-errata`）后，**最终集成 HEAD 将变为 `e1b48ee` 的 docs-only child**（不含 `src/`/产品
`tests/`/冻结件字节改动）。该最终 HEAD 由 Integrator/Lead 在合并时产生并另行记录；本文件不预设其 SHA。

## 6. 引用与身份

| 对象 | 位置/哈希 |
|---|---|
| 环境事故记录 | `docs/A_NEXT_ENVIRONMENT_INCIDENT.md`（sha256 `201c59846a6b50f17a5541165ed8907ae19aeae569a4ac4b5054f222c2ed4150`） |
| R-REV6 L2 addendum v2 | `docs/A_NEXT_RREV6_L2_REPORT_ADDENDUM_V2.md`（sha256 `28a2bba43ad21933c1180b30f4300ba4f0df59e5752dd7bae0ad663ad4d34319`） |
| Packet v3 disclosures | `payload/docs/A_NEXT_PACKET_V3_DISCLOSURES.md`（见 §2；sha256 `5e940fd9…`） |
| Reviewer 报告 | `docs/A_NEXT_INDEPENDENT_REVIEW.md` @ `220171c`（1636 行；sha256 `9b833c6f…`） |
| 旧 v1/v2 Packet | v1 = `LOST_IN_INCIDENT_20261121`；v2 = HISTORICAL_REFERENCE_ONLY（unmodified） |
| 门常量 | `LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` |

## 7. 不主张 / 人类待决 / STOP

- 不主张：E5-Full/E5-P04/B03 关闭、G4-H1 部署、G5 获批、G6/M0 GO、Live/生产安全、人类已验收。
- 人类待决：接受最终 no-key PASS 与 Packet v3 `FROZEN_BY_LEAD` 身份；P2-1..P2-7 处置/知情；D-xx 决策表签核；
  G4-H1/G5 另行授权（均不在本文件范围）。
- **append-only**：后续补充只在末尾追加新小节，不改写本文件与任何既有字节。
- **STOP**：本文件完成后 A-PR4 收尾结束；等待人类/Lead 决定合并与后续门。

## 8. 自查（实测）

```text
git -C worktrees/a-next-errata diff fd1d3a6..HEAD --name-only   -> 预期待提交后仅 docs/A_NEXT_REVIEW_ERRATA.md
git -C worktrees/a-next-errata status --porcelain -uall          -> clean（提交后）
sha256sum docs/A_NEXT_INDEPENDENT_REVIEW.md (worktrees/a-next-review) -> 9b833c6f…
sha256sum Packet v3 manifest/hashes -> 47ff93ef… / 799d8db6…
旧包 bbcb37: artifacts/review-packet-a-next-v3-bbbcb37… 仅保留历史对照，状态 SUPERSEDED/INVALID，不计证据
0 Key/真实 Provider/HTTP/Live；不 push/merge。
```
