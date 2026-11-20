# A-NEXT 独立评审（Independent Reviewer）

- **报告 ID**：`A-NEXT-INDEPENDENT-REVIEW-v1`（阶段 1 设计门；阶段 2 由 Lead 另行下达）
- **Reviewer**：`a-reviewer`（独立 Reviewer；**未参与本轮任何实现/设计文档撰写/Owner 证据生成**；
  不信 Owner summary 直接写 PASS；本报告所有事实绑定 commit/命令/UTC）
- **复审工作树/分支**：`/root/Autonomous Teacher/worktrees/a-next-review` @
  `docs/a-next-review`，基线 = `work/g4r` = **`fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`**
  （继承 `main=3e7afee`、`frozen impl d33e0aa`、旧 G4-R Review `docs/REVIEW_G4R_INDEPENDENT.md`）
- **写入范围**：仅本文件（`docs/A_NEXT_INDEPENDENT_REVIEW.md`）；不改冻结文件字节、不改 Owner 文件；
  本地 commit、**不 push**。
- **时间（UTC）**：阶段 1 开始 `2026-11-20T19:35Z`；本版本记录至 `19:44Z`（Owner 设计文档尚未出现，
  见 §5）。
- **约束**：0 真实 Key/Provider/HTTP/Live；不启动容器；`LiveGate` 仍 BLOCKED；仅 no-key 工程范围。

---

## 0. 阶段 1 结论（TL;DR）

| 项 | 独立结果 | 状态 |
|---|---|---|
| A0-01 分叉冲突矩阵 | 已建立；**canonical = G4-R**；**禁止从 H0 cherry-pick 实现代码（结论 0）**；H0 仅可选择性吸收已审阅 docs/研究/Runbook/Review 原始文件 | **PASS（事实矩阵）** |
| A0-02 65-case CSV 对账 | Reviewer 亲自解析：**65 行，PASS=29 / PARTIAL=14 / NOT_RUN=12 / UNVERIFIED=4 / BLOCKED=6**（与 handoff 声明一致）；`REV-01..08` 全 `NOT_RUN`、reviewer/utc 空；与最终 Review（`e72255d`/`9768933` 链）存在**7 行 R-REV 时态差**（清单见 §2） | **PARTIAL**（CSV 为冻结前快照；append-only 对账待 Owner 产出，冻结 CSV 不得改字节） |
| A0-03 冻结 rootfs 防写 | 当前 rootfs canonical=`25491e45…`、`podman ps -a`=0（Reviewer 只读复算）；但仓库历史 OCI 命令仍**直接 `--rootfs` 冻结 rootfs**（旧矩阵大量实例）；基线 `fd1d3a6` 尚无新防写实现/证据 | **NOT_RUN（待 A-PR0/PR4 实现+独立证据）** |
| 基线 sanity | Reviewer 亲自跑 `pytest tests/g4r_packet tests/unit/security/test_authorization.py -q` = **59 passed in 31.43s**（fd1d3a6；Python 3.11.15/pytest 9.2.0） | **PASS（限定子集）** |
| 设计门（A-PR1/A-PR2/A-PR3/Owner docs） | `A_NEXT_BRANCH_RECONCILIATION.md`、`A_NEXT_AUTH_RECORD_REPORT.md`、`A_NEXT_RUN_ADMISSION_DESIGN.md` **均未出现**（见 §5）；**任何 PR 均不得判 PASS、不得开始实现** | **BLOCKED（等待 Owner 设计文档）** |
| H0 F-02（dir fsync）是否被 G4-R 覆盖 | **是，已覆盖**：G4-R 在 link 后 `_fsync_directory` + 失败返回 `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`（fail-closed，不返回成功），并有定向测试；H0 分支**无**目录 fsync/该错误码/相关测试（§1.4） | **VERIFIED（源码+测试行号）** |

> **设计门裁定（本版本）**：A-PR0 事实项 PASS（除 A0-03 待实现）；A-PR1/A-PR2/A-PR3 的**是否允许进入实现** =
> **暂缓/拒绝（BLOCKED）**，直到 Owner 设计文档出现并由 Reviewer 逐份判 PASS/PARTIAL（安全降级必须
> 明确拒绝进入实现）。A-PR4 属阶段 2。
>
> 本报告**不**宣称：任何 PR PASS、G4-H1 部署、E5-Full、G5 授权、M0/G6 GO、生产安全。

---

## 1. A0-01 分叉冲突审计与仲裁（work/g4r vs work/m0-g4h0）

### 1.1 独立事实（Reviewer 命令，commit `fd1d3a6` 工作树）

```text
$ git rev-parse work/g4r           -> fd1d3a6d101f17e6a86d7c43f06c630326e3e3af
$ git rev-parse work/m0-g4h0       -> 15c5a08b6f518dadf43f652d5a25f91d5d80811b
$ git rev-parse main               -> 3e7afee077845a071cd364e93ab209cac20b2d5f
$ git merge-base work/g4r work/m0-g4h0
                                   -> 3e7afee077845a071cd364e93ab209cac20b2d5f
$ git diff --stat work/g4r..work/m0-g4h0 | tail -1
                                   -> 164 files changed, 12064 insertions(+), 10995 deletions(-)
$ git diff --stat work/g4r..work/m0-g4h0 -- src/autoteacher_m0/security/authorization.py \
      src/autoteacher_m0/bridge/controller.py
  controller.py      | 370 +++++++++++++--------------
  authorization.py   | 290 +++++++++++----------------
  2 files changed, 177 insertions(+), 483 deletions(-)
```

- 两分支**同源分叉**（merge-base = `main` = `3e7afee`），**不是**先后提交；164 文件、±1.2 万行级 diff
  ⇒ 机械化 merge/cherry-pick 不可接受（handoff §A0-2 明确禁止）。
- `work/m0-g4h0` 的 `authorization.py`/`controller.py` 与 G4-R 修改**同一函数族**：见 §1.2/§1.3 函数表。

### 1.2 `authorization.py` 逐函数行为矩阵（Reviewer 以 `git show <branch>:file` 对照）

| 行为/函数 | G4-R（canonical） | H0（`15c5a08`） | 差异判定 |
|---|---|---|---|
| 完整离线验证 `load_execution_authorization`/`require`/binding/revocation | 不变（继承 main） | 不变 | 相同 |
| `consume_execution_authorization` 线性化 | temp→file fsync→`os.link(no-replace)`→**dir fsync**→回收 temp | temp→file fsync→`os.link`→回收 temp；**无 dir fsync** | **G4-R 更强** |
| 目录 fsync 失败语义 | `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`（fail-closed，不返回成功，final 保留、后续 replay） | 无该信号/无对应测试 | **H0 退化，F-02 未覆盖** |
| 记录读取 `_read_use_record` | `O_NOFOLLOW`+`fstat`+size，**`nlink>2` 拒绝**，**group/other-writable 拒绝** | `O_NOFOLLOW`+`fstat`+size；无 nlink/mode 检查 | **G4-R 更强** |
| bounded retry `_read_use_record_settled` | 5×10 ms（仅 INVALID 重试，不授予权限） | 20×10 ms（同语义） | 同等（参数不同） |
| temp 管理 | 前缀/上限 `MAX_USE_RECORD_TEMPS=256` + TTL 300s 回收；容量计数排除 temp | 仅前缀排除计数；**无上限/无回收** | **G4-R 更强**（H0 崩溃残留可累积但不能永久锁死，仍无 DoS 上限） |
| 不支持 link/EXDEV/权限 | fail-closed `WRITE_FAILED`，无 direct-write 回退 | 同（`_publish_use_record` 的 OSError→外层 WRITE_FAILED） | 相同 |
| `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` | 新增 fail-closed 码（R1 报告已显式声明 Controller 尚未消费） | 不存在 | **G4-R 新增面，接线时必须映射“不确定/不发送”** |
| body `authorization_id` 与路径交叉校验 | **缺失（P2-01 开放）** | **缺失** | 两分支同样缺口；A-NEXT A1 修 |
| `consume_execution_authorization` 生产调用方 | `src/` 内**无**（仅测试/`scripts/g4` 探针；`git grep` 证据见下） | 同样**无** | 两分支同样缺口；A-NEXT A2 修 |

调用方独立证据（两分支 `src/` 均无 prod 调用）：

```text
$ git grep -n consume_execution_authorization work/g4r -- src/
work/g4r:src/autoteacher_m0/security/authorization.py:988:def consume_execution_authorization(...
$ git grep -n consume_execution_authorization work/m0-g4h0 -- src/
work/m0-g4h0:src/autoteacher_m0/security/authorization.py:921:def consume_execution_authorization(...
```

### 1.3 `controller.py` 逐函数/机制行为矩阵

| 机制 | G4-R（canonical） | H0（`15c5a08`） | 差异判定 |
|---|---|---|---|
| P2-05 观测层 | 新增 `request_lifecycle.py`（transport 层 6 事件；pre-Controller `dispatch_seq=null`、`reserved=false`）+ dispatch 层 rejection `dispatch_seq=None`/`request_level_only=true`；两层分离 | 单一 dispatch-window 追加 `observation_only=true`、`dispatch_seq=None` 的观测行（`_observe_envelope_deadline`） | G4-R 两层结构更强；H0 机制被取代 |
| dispatch_seq 真实性 | 仅 worker 真正进入 `_handle_payload_serial` 后由真实 audit seq 回填 | observation 行 `dispatch_seq=None`，正常行不变 | G4-R 更严格 |
| P2-06 recovery reason | `first_cause` 封闭枚举（revoke 精确 + `REVOKED_PRE_SEND:`）+ **Broker PENDING 条件**保留；observation 独立 append-only `recovery-diagnostics.jsonl` | `_preserved_uncertain_reason` 将 fallback 以 `|RECOVERY_EVIDENCE:` 拼接进同一 reason（≤256） | G4-R 分离更彻底；H0 为旧简化实现 |
| observability gap | `observability_status()` 汇总 request/recovery/dispatch gap；写失败不改判定 | 无统一 status | G4-R 新增 |
| cancel/timeout code | `_Cancelled → CANCELLED` 分类修正 | 无该修正 | G4-R 新增 |
| Broker 费用权威/held/不重发/不 FREE | 不变 | 不变 | 相同（G4-R Review R-REV3 已核） |

### 1.4 H0 旧 Review 的 **F-02（use record 发布后未 fsync 目录项）** 是否被 G4-R 覆盖 —— **是**

- H0 分支 `_publish_use_record()`（`git show work/m0-g4h0:...authorization.py:869`）在 `os.link` 后
  **直接 `return True`**：只有 file fsync（:891）、link（:895），**无目录 fsync，无 durability 语义**；
  `git grep -n "DURABILITY_UNKNOWN\|_fsync_directory" work/m0-g4h0 -- tests/` = **无输出**。
- G4-R：
  - `_fsync_directory()` 定义 `authorization.py:918`；
  - link 成功后调用 `authorization.py:1088`；
  - 失败抛 `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` `:1095`（fail-closed、不返回成功、final 保留）；
  - 定向测试 `tests/integration/g4r_auth/test_r1_atomic_use_record.py:345
    test_r1_05_dir_fsync_failure_is_fail_closed_not_success` 注入 EIO 断言该错误码；
    `:326 test_r1_05_crash_after_link_before_dir_fsync_never_double_authorizes` 覆盖 link 后 dir fsync 前崩溃。
- **结论**：G4-R 已覆盖并强化 H0 的 F-02；H0 该点为**退化**分支。任何从 H0 向 G4-R cherry-pick
  `authorization.py` 的行为都会**重新引入 F-02 缺口**或制造冲突 ⇒ **不允许**。

### 1.5 A-PR0 仲裁结论

1. **canonical 安全基线 = G4-R `work/g4r`（`fd1d3a6`，frozen impl `d33e0aa`）**；G4-R Review 的
   `PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE` 仅限 no-key 修复范围。
2. **H0 代码不得 cherry-pick/merge 进 canonical（0）**：两分支同源分叉、同函数族冲突、H0 在
   dir fsync/durability/temp 上限/观测层/恢复原因上均为被取代实现；机械化 cherry-pick 属未授权变更。
3. H0 仅可**选择性吸收**：已审阅的 Provider 研究（A2_SOURCES/PROVIDER_CONTRACT/PRICE）、部署
   Runbook、风险处置/HUMAN_DECISIONS 模板、旧独立 Review 原始文件；**每份仍需 Reviewer 审阅源码/字节**，
   交维护者决定，不合并未经复审代码。
4. 受保护文件/冻结证据：本阶段未发现两分支对 `gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py`/
   旧 Packet/旧 Review 的越权修改（详见 §2 与 handoff；Stage 2 将逐字节复核新变更）。

---

## 2. A0-02：65-case 冻结矩阵独立复算 + Review 时态对账

### 2.1 独立复算（Reviewer 命令，文件 `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv` @ fd1d3a6）

```python
import csv; from collections import Counter
rows = list(csv.DictReader(open("docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv")))
len(rows) -> 65
Counter(r["status"] for r in rows)
-> {'PASS': 29, 'PARTIAL': 14, 'NOT_RUN': 12, 'UNVERIFIED': 4, 'BLOCKED': 6}
```

- **总行数 = 65；status 分布 = PASS 29 / PARTIAL 14 / NOT_RUN 12 / UNVERIFIED 4 / BLOCKED 6**
  —— 与 handoff `29/14/12/4/6` **逐项一致**（Reviewer 亲自解析，不引用 Owner 数字）。
- 分阶段：R0 5 PASS；R1 8 PASS；R2 9 PASS；RG 13（PASS 2/PARTIAL 6/NOT_RUN 4/UNVERIFIED 1）；
  R4 13（PASS 5/PARTIAL 8）；R5 3 UNVERIFIED；**R-REV 8 全 NOT_RUN**；G4-H 6 BLOCKED。
- `reviewer` 列：`PENDING_INDEPENDENT_REVIEW` 51 行、空 14 行 ⇒ 整份 CSV 是**冻结前快照**，
  不含最终独立 Review 终态。

### 2.2 与最终独立 Review 的时态差（Reviewer 结果 vs CSV）

最终 Review：`docs/REVIEW_G4R_INDEPENDENT.md`（review 提交 `e72255d`；G4-R 分支归档提交
`9768933`/`fd1d3a6` 链），最终裁定 `PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE`，R-REV 矩阵终态为：
R-REV1 PASS(with env limitation)、R-REV2 PASS、R-REV3 PARTIAL、R-REV4 PARTIAL、R-REV5 PASS、
R-REV6 NOT_RUN、R-REV7 PASS、R-REV8 PARTIAL。

| CSV 行 | CSV 冻结值 | 最终 Review 终态（绑定 e72255d） | 是否对齐 |
|---|---|---|---|
| REV-01 | NOT_RUN / reviewer空 / utc空 | PASS（with env limitation；Packet/Stage/rootfs 独立复算） | **未对齐** |
| REV-02 | NOT_RUN | PASS（Reviewer 自建竞态/崩溃探针） | **未对齐** |
| REV-03 | NOT_RUN | PARTIAL（L1 代码/原始 JSONL PASS；L2 UNVERIFIED） | **未对齐** |
| REV-04 | NOT_RUN | PARTIAL（API_AVAILABLE 机制 L1 复现；权威性/B03/E5-P04 UNVERIFIED） | **未对齐** |
| REV-05 | NOT_RUN | PASS（自建遍历器全树+mutation 11/11） | **未对齐** |
| REV-06 | NOT_RUN | NOT_RUN | 对齐 |
| REV-07 | NOT_RUN | PASS（无 Key/恒 BLOCKED 负例） | **未对齐** |
| REV-08 | NOT_RUN | PARTIAL（定向/unit/ruff/scanner PASS；OCI/Node/Host full NOT_RUN） | **未对齐** |

次要时态差（候选，需按 ID 级证据最终确认）：R0-01..05 的 reviewer 列仍 `PENDING_INDEPENDENT_REVIEW`，
但最终 Review 已独立复算 R0 身份/canonical/旧冻结字节（R-REV1）；R4-01..06/12/13 为 PARTIAL 快照，
其中 R4-01/02/03/04/06 的“Packet 全树/篡改检测”已被 R-REV5 PASS 覆盖（R4-05 backup provenance /
R4-12 path correction / R4-13 LiveGate 4-reason equality 需 Stage-2 逐 ID 复核，保留 PARTIAL/UNVERIFIED）。
R5-01..03、RG-05/08/12 与最终 Review 的 UNVERIFIED/NOT_RUN 结论基本对齐。

### 2.3 结论与要求

- 冻结 CSV **不得改字节**；需 **append-only `REVIEW_STATUS_RECONCILIATION.md`**
  （`case_id, frozen_status, reviewer_status, evidence_path, sha, reviewer_ran_by_self, utc`）由
  Owner-Docs 产出、Reviewer Stage-2 逐行核对（本报告 §2.2 可直接作为期望表）。
- **A0-02 状态：PARTIAL**——分布/行数独立复验 PASS；对账文档尚未产出，且“最终矩阵全 PASS”禁止宣称。
- 证据矩阵 `UT/AUDIT_REQUESTS.md A-Q6` 的 REV 逐 ID 对照必须引用上述 mapping，不得只报分布数字。

---

## 3. 基线 sanity（Reviewer 亲自运行，不引用 Owner 数字）

```text
cwd=/root/Autonomous Teacher/worktrees/a-next-review  HEAD=fd1d3a6  branch=docs/a-next-review
$ PYTHONPATH=src /root/Autonomous Teacher/.venv/bin/python -m pytest \
    tests/g4r_packet tests/unit/security/test_authorization.py -q -p no:cacheprovider
59 passed in 31.43s   (exit 0)
```

- 环境：Python 3.11.15 / pytest 9.2.0；**0 真实 Key/Provider/HTTP**（测试为 TEST_ONLY 合成 fixture）。
- 说明：本 sanity 仅覆盖 packet builder/verifier 测试与 authorization 单测（59 项子集），
  **不代表** G4-R 全量/矩阵终态；全量/L2 属阶段 2。
- `pytest tests/g4r_packet` 含 40-hex impl id delta 后用例；未发现 baseline 级失败。

---

## 4. A0-03 冻结 rootfs 防写（当前状态：**NOT_RUN，需实现+独立证据**）

- Reviewer 只读复算当前冻结 rootfs canonical：
  `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . | sha256sum`
  → **`25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`**（= G4-R 冻结值）；
  `podman ps -a` = 0 容器。
- 但仓库既有 OCI 命令（旧测试矩阵中大量实例）**直接 `--rootfs /root/Autonomous Teacher/artifacts/security/rootfs`**
  （`git grep -- "--rootfs" HEAD -- docs/` 可见 G3C/G4 矩阵命令），这正是 G4-R P1 事故的机制。
- 基线 `fd1d3a6` **没有**新增“冻结 rootfs 拒绝直接 `--rootfs`/强制工作副本/T0-T1 校验”的实现或独立测试
  （`git grep` 未发现相关 guard 代码；仅 G4-R 文档记载事故与限制）。
- **要求（A-PR0/A-PR4 实现门）**：runner 层强制 (a) 禁止把 frozen rootfs 作为 `--rootfs`（拒绝/自动复制
  writable copy）；(b) 每次 OCI 前后 canonical T0/T1 比对，漂移 STOP；(c) 输出目录/evidence 目录
  pre-existing/在冻结树下检测；(d) 独立测试证明拒绝路径与正常路径。**在实现+Reviewer 证据前，
  A0-03 不得写 PASS。**
- 另注：G4-R Packet v2 已记录 drift/cleanup 链与“非全程 NO_DRIFT、L2 需独占窗口”，该事实继续有效。

---

## 5. Owner 设计文档可用性 + 逐 PR 设计门（本版本：BLOCKED 待文档）

Reviewer 于 `2026-11-20T19:36–19:44Z` 在多工作树搜索：

```text
find /root/Autonomous Teacher/worktrees -maxdepth 3 -name "A_NEXT_*.md"   -> 无结果
A_NEXT_BRANCH_RECONCILIATION.md (a-impl-docs)   -> NOT PRESENT（worktree 不存在）
A_NEXT_AUTH_RECORD_REPORT.md    (a-g4r-auth)    -> NOT PRESENT（a-next-auth-record 仅有未跟踪测试草稿 2 文件）
A_NEXT_RUN_ADMISSION_DESIGN.md  (a-impl-fix)    -> NOT PRESENT
a-next-* 工作树 HEAD 均 = fd1d3a6（未提交设计文档）
```

因此本版本**不能**对 A-PR0/A-PR1/A-PR2/A-PR3 给出 PASS/PARTIAL/FAIL 结论——**Owner 设计文档缺失即
设计门未满足**：

| PR | 设计文档 | 本版本裁定 | 是否允许进入实现 |
|---|---|---|---|
| A-PR0 baseline-and-branch-arbitration | A_NEXT_BRANCH_RECONCILIATION.md + REVIEW_STATUS_RECONCILIATION.md | **BLOCKED（文档缺失）**；Reviewer 侧事实矩阵 §1/§2 已提供，Owner docs 到达后核对 | **否（待文档+本报告核对）** |
| A-PR1 auth-record-and-admission | A_NEXT_AUTH_RECORD_REPORT.md（设计部分）| **BLOCKED（文档缺失）** | **否** |
| A-PR2 registry-authority-decision | （方案 A/B 决策文档）| **BLOCKED（文档缺失）** | **否** |
| A-PR3 rrev6-l2-failure-matrix | A_NEXT_RREV6_* / 设计说明 | **BLOCKED（文档缺失）** | **否** |
| A-PR4 packet-freeze-and-review | 阶段 2 下达 | 本阶段不评 | — |

Owner 文档出现后 Reviewer 将逐份审阅并给出：**每 PR PASS/PARTIAL/FAIL + 是否安全降级（明确允许/拒绝
进入实现）**，重点前置约束（来自 handoff + 本报告独立发现）：
1. **A1**：body `authorization_id` 校验必须绑定 expected auth id（不能只比 run_epoch）；不匹配稳定
   `AUTHORIZATION_USE_RECORD_INVALID`（不得伪装 replay）；维持 fail-closed/不 fallback 旧直写；
   合法 replay 同/异 epoch、body id 错配、损坏/截断/symlink/hardlink/FIFO、并发 2/10/50、crash
   before link/after link/before dir fsync 全覆盖。
2. **A2**：run-level 一次消费（非每 dispatch），拒绝伪造/重放/别的 Run/epoch/超预算期限/工具漂移/
   `DURABILITY_UNKNOWN` 时 **0 Reserve、0 Fake、0 new attempt**；admission token 仅受信 principal
   生成/验证；LiveGate 仍 BLOCKED，禁止新增 Live allow path。
3. **A3**：Registry 保持 UNVERIFIED，除非有独立可信测量/绑定通道 + 独立 attack 证明；不得以
   candidate 自报 JSONL/schema 升级为 attestation；方案 A/B 由人决定。
4. **A4**：R-REV6 必须独占窗口 + 工作副本 rootfs + frozen Stage/Runtime SHA + 逐字段 digest 对账
   （prepared==claim.request_digest、payload==receipt.raw_sha256 等），未跑即 NOT_RUN。
5. **A5**：新 Packet 必须新目录/新身份（不改旧 v1/v2），mutation 拒绝未列文件/sidecar/symlink/
   hardlink/mode/hash 变化；69 deselects 与 host 5 failures 逐项归类。
6. **H0 F-02**：不得通过 cherry-pick H0 代码“修复”；G4-R 已覆盖（§1.4），A1 设计只需**保留**
   G4-R 的 dir fsync/DURABILITY_UNKNOWN 语义。

---

## 6. 阶段 1 结论、风险与 STOP

- **A0 事实门**：A0-01 PASS；A0-02 PARTIAL（对账文档待 Owner，冻结 CSV 不改）；A0-03 NOT_RUN（待实现）；
  baseline sanity PASS（59 项子集）。
- **设计门**：A-PR1/A-PR2/A-PR3 **BLOCKED（Owner 设计文档缺失）**——任何“已审阅通过/允许实现”结论
  在本版本均不成立；实现方不得据本报告开始实现。Owner 文档出现后 Reviewer 补审并更新本章节。
- **H0 仲裁**：canonical=G4-R；**H0 cherry-pick = 0（禁止）**；H0 仅选择性吸收已审阅非代码产物。
- **门状态不变**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`、`B03/E5-P04=UNVERIFIED`。
- **STOP（阶段 1）**：等待 Owner 设计文档与 Lead 的阶段 2 指令；不进入实现、不部署、不调用 Provider。

---

## 附录 A：本阶段证据命令与原始输出位置

- 证据等级：本报告所有运行均为 `INDEPENDENTLY_REEXECUTED_THIS_TURN`（Reviewer 本机、no-key）；
  未复制 Owner 数字。原始日志暂存 Reviewer 运行目录（`/tmp/a-next-review-*`），关键输出已内联本报告；
  阶段 2 将把原始对账 JSONL/日志作为独立证据归档（append-only）。
- 命令清单：
  1. `git rev-parse {work/g4r,work/m0-g4h0,main}` / `git merge-base` / `git diff --stat|name-status`
     / `git show <branch>:src/...` / `git grep`（§1）。
  2. Python `csv.DictReader` 解析 65 行 + `Counter(status)` + REV 行提取（§2）。
  3. `pytest tests/g4r_packet tests/unit/security/test_authorization.py -q` = 59 passed/31.43s（§3）。
  4. `tar --sort=name --mtime=@0 ... | sha256sum` rootfs = `25491e45…`；`podman ps -a` = 0（§4）。
  5. `find .../worktrees -maxdepth 3 -name "A_NEXT_*.md"` = 无结果（§5，Owner 文档状态）。
