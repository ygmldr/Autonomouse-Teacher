# M1-B 最终独立评审 Addendum 2（P1-3 关闭 mini delta）

| 字段 | 值 |
|---|---|
| Reviewer | 最终独立 Reviewer（未参与 M1-B / B-NEXT 任何实现、修复或 Owner 证据生成） |
| 本轮角色 | 仅新增本文件；未改源码/测试/fixtures/证据/既有文档/既有 commit；未 amend |
| 日期 | 2026-11-21 UTC |
| 工作区 / 分支 | `/root/m1b/delta-review2` / `b-next/m1b-final-review-delta2` |
| HEAD / tree（复核时） | `1eb40a921d48c3098a1f70f2ec219c89642ee893` / `0fd453b3ee8d84d942cf58ec00b60a31f839947a` |
| 前序 | 首轮 `5d5ebf8`：`PASS_WITH_ACTIONS`（P0=0/P1=3/P2=6）；delta `a09e56e`：P1-1/P1-2 `CLOSED`、P1-3 `PARTIAL` |
| 基线 | `main=3e7afee`；M1-A `4706250` |
| 环境 | Linux 6.17.13-2-pve x86_64；Python 3.11.15；pytest 9.2.0；bubblewrap 0.9.0；TZ=UTC |
| 证据标签 | `OWNER_REPORTED` / `REVIEWER_REPORTED` / `INDEPENDENTLY_REEXECUTED_THIS_TURN` / `NOT_RUN`；无 hidden 明文/凭据 |
| 边界 | **Offline synthetic / MOCK only, not real teaching effect.** 不扩大真实 Provider/Live/生产/人类 Gate 范围 |

## 0. 结论

**`P1_ACTIONS_CLOSED`**：P1-1、P1-2、P1-3 全部关闭。

- **P1-1 / P1-2：`CLOSED`（承 `a09e56e`）。** 本轮确认 `db5ce03..HEAD` 仅两份 docs 变化，代码/测试/fixtures/证据零改动，故 clean archive（939/0 skipped）与证据绑定结论不被破坏。本轮未重跑 clean archive/strict，属证据继承而非新复跑（§8）。
- **P1-3：`CLOSED`（5/5）。** 逐项见 §2；报告现行数字/哈希/状态均与独立实测一致。
- **建议总体裁定升级为 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`**（仅限离线、合成 fixtures、确定性/mock E2E、本树证据齐全的 M1-B 集成范围）。不是无条件 PASS，不得外推到真实教学/Provider/Live/生产（§5）。
- **B5-01：** `PARTIAL` 的唯一 P1 事由（P1-3）已消除；建议 Lead 记为 `PASS_WITH_ACTIONS`（仅余 P2 文档项），最终标签由 Lead 按流程确定。
- **新增 P2-7：** X-01 计数口径（302/303、243/244），不阻断（§6）。

## 1. Git 范围 / 守卫 / Reviewer 完整性

| 检查 | 本轮实测 | 标签 |
|---|---|---|
| `git status --porcelain`（开始/结束） | 空 | `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| `git diff --name-status db5ce03..HEAD` | `M docs/M1_B_EVALUATION_REPORT.md`、`A docs/M1_B_FINAL_INDEPENDENT_REVIEW_ADDENDUM.md` | 同上 |
| `git diff --stat db5ce03..HEAD` | 2 files changed, 232 insertions(+), 17 deletions(-) | 同上 |
| HEAD commit `1eb40a9` | 仅 `docs/M1_B_EVALUATION_REPORT.md`，+17/−17（docs-only errata） | 同上 |
| `git log --oneline db5ce03..HEAD` | `1eb40a9` / `8af234a`（merge）/ `a09e56e` | 同上 |
| 源码/测试/fixtures 守卫 | `git diff --name-only db5ce03..HEAD \| grep -E "^(m1_teacher\|tests\|fixtures)"` → 无（exit 1） | 同上 |
| 证据守卫 | `... \| grep -E "^docs/m1b_evidence/"` → 无（exit 1） | 同上 |
| Reviewer 文档/证据 | `git diff a09e56e..HEAD -- docs/M1_B_FINAL_INDEPENDENT_REVIEW.md docs/M1_B_FINAL_INDEPENDENT_REVIEW_ADDENDUM.md docs/m1b_evidence/` → 空；首轮文档仅 `5d5ebf8`、addendum 仅 `a09e56e`（历史上均未被改写） | 同上 |
| 必需祖先 | `5d5ebf8/12f6290/9c383e5/580be70/8f8d00e/d9201e9` 均为 HEAD 祖先 | 同上 |

**X-01 = VERIFIED（本 mini delta 范围）：** 无 `src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate、`plugins/`、`.github/` 改动；范围仅 `docs/`，未改证据数据。注：`docs/M1_B_FINAL_INDEPENDENT_REVIEW_ADDENDUM.md` 在 `db5ce03..HEAD` 显示为 `A`，因它创建于 `db5ce03` 之后，不是 Owner 改写。

## 2. P1-3 五项逐项复核

| # | 位置 | 独立实测 | 报告现状 | 判定 |
|---|---|---|---|---|
| R1 | collector 测试数 | `pytest tests/m1_teacher/test_evidence_collector.py -q` → **15 passed in 1.48s**（exit 0；`--collect-only` 15） | 第 89 行 `15 passed in 1.43s`；§3.2/§13 均 15；无 `14 passed` | `CLOSED` |
| R2 | JD v1 journal 哈希 | summary `interview.jd_change.old_session_before/after.journal_sha256` 均为 **`c372421798cce3169d2231ff902f07e254f1e606d43f4c1bbe5f687da6bf153a`**（27 events、REVIEW；new session 12 events `4a2526b3…`） | 第 115 行现行值一致；`554c1153…` 仅作“旧树、已废止、仅历史”标注 | `CLOSED` |
| R3 | summary manifest | `artifact_manifest.implementation_commit` = **`12f6290c43523d5c3930915fe18810adca8609a4`**（`base_sha=3e7afee…`，`generated_at=2026-11-20T00:00:00Z`） | 第 165/177/227/230/246 行均一致；`c420d19` 仅第 162 行描述“旧 27 条 c420d19 历史窗口”，不再指向现行 manifest | `CLOSED` |
| R4 | B5-01/评审状态行 | 全文 grep `'未出\|待合入\|待 Reviewer\|PENDING（Lead\|评审未\|独立评审 \`PENDING\`\|P1 修复待'` → 仅第 114 行“FULL 从未出现”（面试 hint 语义），无状态矛盾 | 第 5/12/28/132/238/249 行：首轮 `PASS_WITH_ACTIONS`（P0=0/P1=3/P2=6，`5d5ebf8` 已合入 HEAD）+ delta `a09e56e`（P1-1/P1-2 `CLOSED`）+ `B5-01 PARTIAL` + mini delta 复核 `PENDING` | `CLOSED` |
| R5 | 最终 PR5 SHA 占位 | 占位处无伪造 40-hex；唯一显式 SHA 占位为第 229 行 | 第 229 行 **`PENDING_LEAD_MERGE`**（说明由 Lead 记录实际 push SHA）；第 8 行同义说明“由 Lead/报告回填” | `CLOSED` |

> R5 说明：`PENDING_LEAD_MERGE` 是本轮任务允许的占位口径；未发现把分支起点 `db5ce03…`、本 HEAD `1eb40a9…` 或其他值冒充“最终 PR5 commit”。第 8 行是文字说明而非哈希，建议后续与第 229 行统一为同一 token（P2，非阻断）。

## 3. 全报告一致性抽查

| 项 | 本轮独立实测 | 与报告对照 | 标签 |
|---|---|---|---|
| 测试收集数 | `pytest tests/m1_teacher --collect-only -q` → **939 tests collected**；注意：根目录 `pytest --collect-only -q`（`testpaths=["tests"]`）为 **2296**，含 M0/M1-A，非 939 | 报告 §3/§13 的 939 指 M1-B 套件，一致；命令须带路径 | `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| 全量套件（HEAD） | 私有 `TMPDIR` 串行：**939 passed in 102.44s**，exit 0，0 skipped | 报告 939 passed（103.11s/102.96s 为 Owner 历史运行时长） | 同上 |
| 计数构成 | collector 15 + B5 E2E 11（`--collect-only` 11）；939 = 913 + 26 | 报告 §3.2 一致 | 同上 |
| X-01 vs main / M1-A | `db5ce03`/`d9201e9`：**302 / 243**；HEAD：**303 / 244**（+1 = 本 addendum 文件） | 报告 302/243 对应最终代码/测试树；未注明“不含评审 addendum”，见 P2-7 | 同上 |
| B4 demo 双跑 | `demo_b4 --json` 两次逐字节相同：sha256 **`b3231658a4ac12a49cd2ac57f4a3e8d9719fbf7476ca36a54e4d8f9eea72d905`**；**513 行 / 15,340 bytes** | 报告 §4/§9/§13 一致 | 同上 |
| B5 demo 双跑 | `e2e_b5` 两次逐字节相同：sha256 **`4d0e0c851f4ff4d745127932aa62fcfabeca47da2f7d23ae434cae1ab300a2fc`**；**27 行 / 4,168 bytes** | 报告 §4/§9/§13 一致 | 同上 |
| `audit-index.jsonl` | **`a11ce42948d5dd43563a1bf6befa8bb7c8600ba3b73f9df32e345b07bc66ea80`**；38 行 | 报告 §8/§13/§14 一致 | 同上 |
| `audit-index.json` | **`8db875301cc10f5af3af4f038b42d50a43a9291ac50c96719f7fd9ce37fc34e5`**；`entry_count=38` | 一致 | 同上 |
| `e2e_b5_summary.json` | **`a07cfe7ec06208bc3271e01eaaf62a6145c753bf175b23c844658c756d444053`** | 报告 §9 一致 | 同上 |
| 其余 4 个 E2E 文件 | cf `526f9dfd…`、interview `8f3a16fc…`、cross_domain `c02723ec…`、freshness `8a25de6e…` | 报告 §9/§14 一致 | 同上 |

## 4. 最终裁定与升级建议

- **P1 全部关闭**：P1-1 clean archive 可移植性、P1-2 证据绑定最终树、P1-3 报告数字/哈希/状态勘误，均不再构成阻断。
- **建议总体裁定：`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`。** 适用范围严格限定为：离线、合成 fixtures（`hidden=false` 的 teacher-visible 脚本 / synthetic JD+简历）、确定性/mock E2E、本树可复算证据齐全的 M1-B 集成范围。
- 该裁定**不是**无条件 PASS，也**不是**对产品行为、真实教学效果或生产安全的验收；不得改写 M0 G4-H/G5、LiveGate 或人类 Gate 决策。
- `B5-01`：P1 阻塞已解除；建议 `PASS_WITH_ACTIONS`（仅余 P2 文档项），不再维持 `PARTIAL`（最终由 Lead 记录）。

## 5. 必须保留的 NOT_RUN / UNVERIFIED / BLOCKED

1. **真实学习效果/教学收益：`NOT_VERIFIED`**——无真人、无对照、无效果测量。
2. **真实 Provider / 外部网络 / LiveGate：`BLOCKED` / `NOT_RUN`**——仅离线 mock；LiveGate 保持 BLOCKED。
3. **真实用户 CODE：`BLOCKED`**——fail-closed 为本地实现与合成验证，未接真实用户提交。
4. **非 root 目标部署：`NOT_RUN`**——本地以 root 合成模式运行，不构成部署安全证据。
5. **断电持久性：`NOT_RUN`**——crash 矩阵为进程级 SIGKILL，不含主机断电/掉盘。
6. **真实 auth / 多租户：`NOT_RUN`**——无真实身份、租户隔离或鉴权验收。
7. **target CI 接线：`NOT_CONFIGURED` / `NOT_RUN`**——`scripts/m1b/run_safety_ci.sh` 可用，`.github` job 未配置。
8. **event `schema_version`（B4-05）：`PARTIAL` / `NOT_IMPLEMENTED`**——不得写成 PASS。
9. **B0 签收：`NOT_RUN`**。
10. **B4-04 完整双向（JD/简历闭环）：`PARTIAL`**——仅合成 JD v1→v2 与受控会话。
11. **真实 JD / 简历：`NOT_RUN`**——只用 synthetic fixtures。
12. **真实恶意代码 / 攻击样本：`BLOCKED` / `NOT_RUN`**——未做真实恶意载荷评测。
13. **全仓 M0 套件：`NOT_RUN`**——本轮/本报告只覆盖 `tests/m1_teacher`（939）；全仓 collect 为 2296（含 M0/M1-A），未整体复跑。
14. **真实 OS 判题安全承诺 / 生产可用性：`NOT_VERIFIED`**。
15. **人类 Gate H-01/H-02/H-03、G5、LiveGate、M0 决策：保持各自状态**，B 线无权解除或预填。

## 6. P2 残余（不阻断，docs-only）

- **P2-7（X-01 计数口径）：** 302/243 实测于最终代码/测试树（`d9201e9`/`db5ce03`）；HEAD `main...HEAD` 为 303/244，差 1 为本 addendum 自身。报告写“最终树”但未注明“不含评审 addendum”。建议加注，或把命令期望改为 303/244；不影响 P1-3 五项关闭与离线范围裁定。
- **P2-8（评审后状态刷新）：** 本文件合入后，评测报告第 5/12/28/132/238/249 行的“P1-3 关闭中 / mini delta `PENDING` / B5-01 PARTIAL”将成为历史表述；建议 Owner 做一次 docs-only 状态刷新为 `P1-3 CLOSED` / B5-01 最终标签。无需重跑代码测试。
- **P2-9（占位一致性）：** 第 8 行文字说明与第 229 行 `PENDING_LEAD_MERGE` 建议统一；不构成伪造哈希。

## 7. 复现命令（本 mini delta 实际执行）

```bash
cd /root/m1b/delta-review2
PY='/root/Autonomous Teacher/.venv/bin/python'
TMPDIR=$(mktemp -d) "$PY" -m pytest tests/m1_teacher -q -p no:cacheprovider   # 939 passed
"$PY" -m pytest tests/m1_teacher --collect-only -q | tail -1                 # 939
"$PY" -m pytest tests/m1_teacher/test_evidence_collector.py -q               # 15 passed
"$PY" -m pytest tests/m1_teacher/test_b5_e2e.py --collect-only -q | tail -1  # 11
TMPDIR=$(mktemp -d) "$PY" -m m1_teacher.demo_b4 --json | sha256sum           # b3231658… / 513 / 15340
TMPDIR=$(mktemp -d) "$PY" -m m1_teacher.e2e_b5 | sha256sum                   # 4d0e0c85… / 27 / 4168
sha256sum docs/m1b_evidence/audit-index.jsonl docs/m1b_evidence/audit-index.json docs/m1b_evidence/e2e_b5_summary.json
python3 -c "import json;d=json.load(open('docs/m1b_evidence/e2e_b5_summary.json'));print(d['artifact_manifest']['implementation_commit'],d['interview']['jd_change']['old_session_after']['journal_sha256'])"
git diff --name-only db5ce03..HEAD | grep -E '^(m1_teacher|tests|fixtures)'  # 空
```

## 8. 本轮边界与未执行项

- **未重跑**：clean archive full/strict、`M1B_REQUIRE_OS_SANDBOX=1` strict、`e2e_b5 --write-evidence`（会改写证据）。理由：`db5ce03..HEAD` 仅 docs（§1），代码/测试树未变；P1-1/P1-2 结论承 `a09e56e`（`REVIEWER_REPORTED`）。
- **未改动**：源码、测试、fixtures、`docs/m1b_evidence/**`、既有评审/实现/架构文档、既有 commit；未 amend、未 force-push。
- **不含**：hidden expected 明文、真实凭据/Key、真实个人数据、攻击代码；本文件仅为评审记录。
- 证据标签说明：本文件中的“实测”均为 `INDEPENDENTLY_REEXECUTED_THIS_TURN`；“承 `a09e56e`/Owner 报告”的引用为 `REVIEWER_REPORTED` / `OWNER_REPORTED`，未冒充本轮复跑。
