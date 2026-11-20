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
| 设计门 A-PR1（A1+A2） | A1 报告（`a-next-auth-record/docs/A_NEXT_AUTH_RECORD_REPORT.md`，**未提交草稿**）与 A2 ADR（`feat/a-next-run-admission` @ **960724b**，DESIGN_ONLY）已出现并逐份独立审阅：A1 设计 **PASS（条件：先提交设计文档）**；A2 设计 **PASS（带前置条件 C1–C8，见 §7）**；均**允许进入实现（条件式）** | **PASS（条件式）** |
| 设计门 A-PR0/A-PR2/A-PR3 | `A_NEXT_BRANCH_RECONCILIATION.md` 等仍未出现（§5） | **BLOCKED（等待文档）** |
| H0 F-02（dir fsync）是否被 G4-R 覆盖 | **是，已覆盖**：G4-R 在 link 后 `_fsync_directory` + 失败返回 `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`（fail-closed，不返回成功），并有定向测试；H0 分支**无**目录 fsync/该错误码/相关测试（§1.4） | **VERIFIED（源码+测试行号）** |

> **设计门裁定（本版本）**：A-PR0 事实项 PASS（除 A0-03 待实现）；**A-PR1（A1+A2）设计门
> = PASS（条件式，见 §7）**——A1 设计文档须先提交为 commit（当前为 worktree 未跟踪草稿），
> A2 实现须满足 §7 的 C1–C8 前置条件；**A-PR2/A-PR3 = BLOCKED（设计文档未出现）**；
> A-PR4 属阶段 2。安全降级若出现即拒绝进入实现。
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

观察到的在制品（**无设计文档、未提交 ⇒ 不构成本阶段可审材料**）：`a-next-oci-hygiene/scripts/a_next/`
（`rootfs_guard.py`/`oci_guard.py`/`ci_guard.py`/`_common.py`，untracked，mtime 19:41-19:42）与
`a-next-registry/scripts/a_next/registry/`（`run_matrix.py`/`fake_bridge.py`/`probe_plugin/`，untracked）；
A-PR0/A-PR2 设计门在这些文档提交前保持 BLOCKED。

因此本版本**不能**对 A-PR0/A-PR2/A-PR3 给出 PASS/PARTIAL/FAIL 结论——**Owner 设计文档缺失即
设计门未满足**：

| PR | 设计文档 | 本版本裁定 | 是否允许进入实现 |
|---|---|---|---|
| A-PR0 baseline-and-branch-arbitration | A_NEXT_BRANCH_RECONCILIATION.md + REVIEW_STATUS_RECONCILIATION.md | **BLOCKED（文档缺失）**；Reviewer 侧事实矩阵 §1/§2 已提供，Owner docs 到达后核对 | **否（待文档+本报告核对）** |
| A-PR1 auth-record-and-admission | A1 `A_NEXT_AUTH_RECORD_REPORT.md`（worktree 未提交草稿）+ A2 `A_NEXT_RUN_ADMISSION_DESIGN.md`（ait 960724b）| **PASS（设计门，条件式；见 §7）**：A1 设计先提交后实现；A2 带 C1–C8 条件允许实现 | **是（条件式）** |
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
- **设计门**：**A-PR1（A1+A2）= PASS（条件式，允许进入实现，见 §7）**；A-PR2/A-PR3 仍 BLOCKED（文档缺失）。
  A1 设计文档必须先提交为 commit；A2 实现须满足 §7 C1–C8；未满足条件不得开始实现。
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


---

## 7. A-PR1 设计门（A1 + A2）独立审查（2026-11-20T19:47–20:05Z）

### 7.1 审阅对象与证据绑定

| 对象 | 位置/提交 | 状态 |
|---|---|---|
| A1 设计报告 | `worktrees/a-next-auth-record/docs/A_NEXT_AUTH_RECORD_REPORT.md`，branch `fix/a-next-auth-record` @ **`0df36de765b510feeadf52c54706d4559f651c1d`**（design commit，parent fd1d3a6；111 行） | **已提交（C1 已满足）**；Reviewer 审阅内容 = 该 commit blob |
| A1 设计测试骨架 | 同 commit `0df36de`：`tests/integration/a_next_auth/{conftest,test_a1_use_record_integrity}.py`（553 行；Reviewer 解析该 commit：**20 个 test 函数 / 6 个 `@PENDING_A1` 标记**）。Reviewer 另在提交前草稿（untracked 版本）上实际运行：**24 passed / 15 xfailed / 93.70s**（`xfail(strict=True)` 符合“未实现契约”预期；**该数字绑定草稿而非 commit**，commit 版本的独立运行待 Stage-2 实现 commit 复跑） | 已提交；**不是实现通过证据** |
| A1 实现（进行中） | 同 worktree `git diff --stat`：`src/…/authorization.py` M（+69/-?）、测试文件 M（-11 行，取消 xfail）；**未提交** | Stage-2 在实现 commit 上独立复跑验收（不得以未提交工作树判 PASS） |
| A2 设计 ADR | `worktrees/a-next-run-admission/docs/A_NEXT_RUN_ADMISSION_DESIGN.md`，branch `feat/a-next-run-admission` @ **`960724b37bab31a017786cff28c0cbf85ee172e9`**（parent fd1d3a6，仅 docs 1 文件） | 已提交，DESIGN_ONLY |

### 7.2 现网证据独立复核（A2 §1 声明，Reviewer 亲自 grep）

```text
$ git grep -n "consume_execution_authorization" fd1d3a6 -- src/
src/autoteacher_m0/security/authorization.py:988:def consume_execution_authorization(...)
# → src/ 内仅定义，0 生产调用方：与 A2 §1.2 一致

$ git grep -n "load_execution_authorization\|require_execution_authorization" fd1d3a6 -- src/
security/__init__.py:10,11,110,113（import/export）；authorization.py:478 def / :700 def；
live_controller.py:29 import, :132 调用
# → 唯一生产调用点是 inspect-only live_controller.authorization_decision()；
#   live_controller 仍永远 BLOCKED、从不 consume（:66 ALWAYS_BLOCKED_REASONS，:251/263-265）。
#   注：A2 附录说“仅 live_controller.py:29/132”，严格说还有 __init__ import/export 行（不构成调用方），
#   结论“0 生产 consume 调用方”成立；建议附录措辞精确化。
```

- `tests/`+`scripts/` 中 `consume_execution_authorization` 出现 10 处（fixture/探针），属非生产；
  不能作为生产接线证据（A2 已如实承认 A-Q3=0 调用方，**未夸大**）。
- A2 附录 A 的 `git rev-parse HEAD # fd1d3a6` 是其**提交前**采集值；审阅对象 ADR 实际提交为
  `960724b`，实现报告应更正为“design commit 960724b + 采集时 fd1d3a6”（nit）。

### 7.3 A1 设计审查（P2-01 body id 完整性）

**独立核对文档行号/事实**（`git show fd1d3a6:src/autoteacher_m0/security/authorization.py`）：

| 文档声明 | Reviewer 实测 | 结论 |
|---|---|---|
| `_read_use_record` L802–L847 | def 在 **L802**，函数体至 ~L845 | 基本准确 |
| `_read_use_record_settled` L850–L870 | def L850 | ✓ |
| `_replay_reason` L872–L874 | def L872 | ✓ |
| 写入侧 id 校验 L521–L525 | L521–L525 为 `authorization_id` `_IDENTIFIER` 校验 | ✓ |
| `record_path` L1034 / 快路径 L1038–L1041 | L1033–34 计算、L1038 快路径 | ✓（±1 行） |
| `_fsync_directory`/DURABILITY_UNKNOWN | L918/L1095 | ✓ |
| `os.open(...O_RDONLY|O_NOFOLLOW|O_CLOEXEC)` **L809** | 实际 **L813** | **nit（文档行号偏 4 行，需修正）** |
| `_UTC_TEXT` 用于 `consumed_utc` 校验 | `_UTC_TEXT` 存在（L112），写入侧 `moment.strftime("%Y-%m-%dT%H:%M:%SZ")` | ✓ 设计可行、不会误杀既有合法记录 |
| 读取侧完全不校验 `authorization_id` | 实测 L842–845 仅校验字段集合/schema/run_epoch | ✓ 缺口属实 |

**设计质量判定**：
- 校验规则（id 类型/`_IDENTIFIER`、body↔path `sha256(id)+".json"`、body↔expected id、
  `consumed_utc` 严格格式、多 key/坏 JSON 仍 INVALID）**严格单调收紧、无放宽**；不新增错误码；
  不引入旧直写回退；`expected_authorization_id` 为内部关键字参数（唯一生产调用方 consume 传入
  已验证签名 id）——与 A2 契约 C-1..C-7 一致，未见冲突（§7.5）。
- FIFO 阻塞修复（`O_NONBLOCK`）属 P2-01 之外的附加 fail-closed 加固；方向正确且不改变普通文件语义，
  但**必须**由定向测试（fork+timeout、无挂起）+ `S_ISREG` 拒绝证明；建议在实现报告中单列。
- 三态语义（REJECTED_NO_CONSUMPTION / CONSUMED_DURABILITY_UNKNOWN / NO_CONSUMPTION）与 G4-R
  fail-closed 一致。
- 测试骨架（20 个 test 函数 + 参数化）覆盖 spec 要求，且以 `xfail(strict=True)` 标注未实现契约
  （Reviewer 基线运行 24 passed/15 xfailed 符合预期，**不是**实现通过证据）。
- **文档未提交**：当前为 worktree 未跟踪文件（`git status` 显示 3 个 untracked）→ 无法绑定 SHA、
  不可作为归档证据；实现前必须先提交（C1）。

**A1 设计裁定：`PASS（条件式）`；允许进入实现（条件 C1 + 实现验收 C4–C8）。**
- 实现验收点：取消 xfail 后 **全部新测试通过**；`AUTHORIZATION_USE_RECORD_INVALID` 不得变成
  REPLAYED；合法同/异 epoch replay 仍分类正确；FIFO 用例证明不阻塞（子进程超时控制）；
  无 `src/` 网络/Key/新 env 开关；`_read_use_record` 私有签名变更不得影响其它调用方（仅 consume + tests）。

### 7.4 A2 设计审查（run-level 一次性消费接线）

**INV-R1..R8 维持性判断**（设计层面）：

| 不变量 | 设计是否维持 | Reviewer 说明 |
|---|---|---|
| INV-R1 一次消费是进入 Reserve 的必要条件 | **是** | `begin_run_admission` 在 Broker 构造前调用；失败 exit、Broker/Fake 未创建（结构性 0） |
| INV-R2 同 Run 多次合法 calls 不误判重放 | **是** | run-level 仅消费 1 次；per-dispatch token（ordinal≤min(auth,admission) max_calls） |
| INV-R3 run 身份 vs business call 身份分离 | **是** | run_epoch 由 admission_id+nonce+run_id 派生；call_id 保持现有 request identity；审计并列 |
| INV-R4 任一校验/未知失败 → 不 Reserve/Claim/Fake、无新 Attempt | **是（设计）** | §7 R-01..R-26；`DURABILITY_UNKNOWN`→BLOCKED_PENDING_RECONCILE；结构断言（Broker 进程未创建/requests=0） |
| INV-R5 token 默认拒绝/跨 Run 不可复用 | **是（设计）** | `_issued[id(token)] is token` 身份 registry + ordinal + digest + TTL；JSON/复制对象 deny |
| INV-R6 历史 PENDING/UNCERTAIN hold 只读不改写 | **是（设计）** | R-22 明确唯一既有 hold 例外；只读计数；无 release/resend/settle 新路径 |
| INV-R7 无 Key/网络/Live allow path | **是（设计）** | 仅 test-only harness；LiveGate/CLI/Adapter/run_live 零 diff（实现须静态+负例证明） |
| INV-R8 审计不含 Key/原始 prompt/敏感内容 | **是（设计）** | §5.1 封闭 allowlist（枚举/标识符/hex 摘要）；§5.2 禁止项明确 |

**契约自洽性 / 绕过与重放窗口审查**：
- run_epoch 派生（admission nonce 确定性）：同 Run 重启 → `AUTHORIZATION_REPLAYED`；新 Run（新 nonce）
  → `AUTHORIZATION_EPOCH_MISMATCH`；与 call_id 分离——**自洽**。错误使用 admission 文档（同 nonce
  二次启动）会 REPLAYED 拒绝（fail-closed，运维需新 Admission）——已在 §10.1(5) 声明。
- **发现 F-A2-1（须写入 A2 实现验收，非设计否决）**：`begin_run_admission` 先
  `load_execution_authorization` 得到授权身份，随后 `consume_execution_authorization` **内部会再次
  load**（G4-R 语义），两次 load 间 external 文件存在 TOCTOU/替换窗口。虽然 consume 内部再次校验
  且 record_path 由它自己加载的 id 推导，但可能出现“RunAdmissionContext 绑定 id A、实际消费记录属于
  id B”的审计错配。**前置条件 C2**：consume 成功返回后必须断言
  `use.authorization_id == context.authorization_id` 且 `use.run_epoch == run_epoch`，
  不匹配 → `RUN_ADMISSION_AUTHORIZATION_DRIFT` fail-closed（BLOCKED_PENDING_RECONCILE，不发送），
  并对授权文件 sha256 在 load 前后做绑定记录。
- **F-A2-2（opt-in 绕过面，Lead Q1）**：默认 `run_admission=None` 保留冻结行为是合理的兼容策略；
  但若 trusted entry 的 strict policy 未启用 run admission 就静默走旧路径，则“生产强制”不成立。
  **前置条件 C3**：trusted entry 在 `run_admission_required: true` 时若缺失 context/配置 →
  启动前 fail-closed 拒绝；“opt-in 未启用”只能显式标注为 legacy/test，并列 **G4-H1 BLOCKER**
  （人类 handoff + Packet limitations），不得在 Packet 中以“已强制”表述。
- **F-A2-3（crash-after-consume-before-Broker）**：设计 R-24 已承认同 Run 重启 → REPLAYED、
  需人工对账。**接受**（fail-closed），前置条件 C4：Runbook/audit 明确“已消费未启动 Broker”的人工
  对账步骤，且不得自动重发/自动清理 use record。
- **F-A2-4（retry vs ordinal）**：token ordinal 按 dispatch 计数；需明确现有 dispatch 内部
  `max_attempts` 重试不额外消耗 ordinal（一次 `_handle_payload_serial` 至多 1 token），否则可能把
  合法重试误判 `RUN_BUDGET_CALLS_EXCEEDED`。前置条件 C5：实现与测试显式覆盖重试不增 ordinal。
- 其余：token pre-Reserve consume 可测试（A2-H10/H11）；拒绝对 Broker 进程/requests=0/attempts=0/fake=0
  的断言设计合理；审计 allowlist 无 Key/原始请求（已核字段表）。

**A2 设计裁定：`PASS（条件式）`；允许进入实现（条件式），L2 不在本 PR。**
前置条件清单（**全部满足才可在实现完成后判 PASS；设计门允许开始实现**）：
- **C1**：A1 设计文档先提交为 commit（当前 untracked），A1 实现 commit 取消 xfail 且新测试全绿。
- **C2**：consume 后授权身份/epoch 一致性校验（F-A2-1）+ 文件摘要绑定；不符 fail-closed 不发送。
- **C3**：Q1 采纳“opt-in 默认不变 + strict policy 强制模式 fail-closed”；G4-H1 BLOCKER 书面化；
  Packet/矩阵不得声称已强制。
- **C4**：crash-after-consume-before-Broker 人工对账路径写入 Runbook/audit；禁止自动重发/清理 final。
- **C5**：dispatch 内部重试不增 ordinal 的测试；budget/deadline 在 token pre-Reserve 拒绝。
- **C6**：§7 R-01..R-26 逐行落地为 host/Fake 测试；launcher-deny 需断言 Broker 进程未创建
  （或结构性 0），token-deny 断言 requests=0/reservations=0/attempts=0/fake=0。
- **C7**：test-only/no-key + 无 Live allow path 的静态与负例证据（gates/run_live/cli/adapter 零 diff、
  LiveGate BLOCKED、CLI smoke --live exit 3、新增代码无网络/Key env、默认路径 1420 回归不变）。
- **C8**：A2 只做 host/Fake L1；A2-01/02/03 的 L2 判据保持 `NOT_RUN`，由 A-PR3 独占窗口执行
  （Lead Q7 立场 Reviewer **接受**）。
- **另**：附录 A 采集口径更正（design commit 960724b）；`_read_use_record` 文档行号 L809→L813。

### 7.5 A1 ↔ A2 契约冲突核查（C-1..C-7）

| 契约 | A2 声明 | A1 设计实际 | 判定 |
|---|---|---|---|
| C-1 consume 公共签名/返回不变 | 只调 public consume | A1 只改 `_read_use_record`（私有）返回 tuple/加 kwarg；consume 签名不变 | **无冲突** |
| C-2 错误码语义稳定 | 依赖既有码 | A1 不新增码、不放宽 | **一致** |
| C-3 body id 不符 → INVALID 非 REPLAYED | 映射依赖 | A1 §3.1(5) 明确 INVALID | **一致** |
| C-4 不得在 reader 加 expected-epoch | 需保留 EPOCH_MISMATCH | A1 不改 epoch 比较（仍由 `_replay_reason`） | **一致** |
| C-5 record_path 语义不变 | 失败归因依赖 | A1 保留 path 映射 | **一致** |
| C-6 原子发布/dir fsync/DURABILITY_UNKNOWN 不变 | 依赖 | A1 明确不 fallback、保持 | **一致** |
| C-7 A2 不 import A1 私有函数 | — | A1 私有签名可变 | **一致** |
| Q6（先 body/path 校验再 epoch 分类） | 建议 | A1 设计正是先校验后返回 epoch | **一致** |

**未发现 A1/A2 设计契约冲突。** 唯一协同要求：A1 需先合入并冻结、A2 rebase（A2 §11 已列）。

### 7.6 Lead Q1 / Q7 立场判定

- **Q1（本轮 opt-in、默认不变、G4-H1 前强制化）**：**有条件接受**（C3）。理由：默认 `None` 才能
  保持 1420 回归与冻结行为；但必须在 trusted entry 有 `run_admission_required` fail-closed 模式 +
  G4-H1 BLOCKER + Packet 不得声称“已强制”。若实现只做“可选、无 required 模式”，则判 **安全降级→拒绝**。
- **Q7（L2 由 A-PR3 窗口，A-PR1 只 host/Fake L1）**：**接受**（C8）；A2-01/02/03 矩阵在 L2 证据前
  保持 `NOT_RUN`，不得以 host 结果冒充 L2。

### 7.7 本阶段 A-PR1 设计门结论

| 对象 | 裁定 | 是否允许进入实现 |
|---|---|---|
| A1 设计（P2-01 body id） | **PASS（条件 C1/C4–C8）** | **允许（条件式）**：先提交设计文档 + 实现验收 |
| A2 设计（run admission） | **PASS（条件 C2–C8）** | **允许（条件式）**：按 C2–C8 实现/测试；L2 不在本 PR |
| A-PR1 总体设计门 | **PASS（条件式）** | **允许进入实现**；实现完成后由 Reviewer Stage-2 逐项验收（C1–C8 全部满足才 PASS，否则 PARTIAL/FAIL） |
| A-PR2 / A-PR3 / A-PR0 对账文档 | **BLOCKED（文档未出现）** | **否** |

> 本裁定仅设计门；**未**验证任何实现/测试结果，**未**改变门状态；A2 现网仍无 run-level 强制
> （P2-02 保持开放直至实现合入+Fake/L2 证据）。

---

## 附录 B：阶段 1 追加证据命令（§7）

```text
$ git -C worktrees/a-next-run-admission rev-parse HEAD -> 960724b37bab31a017786cff28c0cbf85ee172e9
$ git -C worktrees/a-next-run-admission log --oneline -2 -> 960724b docs(a-next): design run-level ...; fd1d3a6 merge...
$ git grep -n "consume_execution_authorization" fd1d3a6 -- src/
  -> only src/autoteacher_m0/security/authorization.py:988 (definition); 0 production callers
$ git grep -n "load_execution_authorization\|require_execution_authorization" fd1d3a6 -- src/
  -> __init__ import/export; authorization.py:478/:700 defs; live_controller.py:29/:132 (inspect-only, BLOCKED)
$ git grep -n "consume_execution_authorization" fd1d3a6 -- tests/ scripts/ | wc -l -> 10 (non-production only)
$ cd worktrees/a-next-auth-record && pytest tests/integration/a_next_auth -q
  -> 24 passed, 15 xfailed in 93.70s (xfail strict design-contract skeleton on baseline fd1d3a6)
$ git -C worktrees/a-next-auth-record status --porcelain -uall
  -> ?? docs/A_NEXT_AUTH_RECORD_REPORT.md; ?? tests/integration/a_next_auth/{conftest,test_a1_use_record_integrity}.py
     (uncommitted -> evidence not yet SHA-bound; C1)
```


---

## 8. 阶段 2（第一批）独立复核 — 2026-11-20T19:50Z–20:25Z

> 本章节为 append-only 阶段 2 记录；阶段 1 裁定与日期保留（A1 设计 **PASS(C1)**、A2 ADR **PASS(C2–C8)**、
> A0-01 PASS、A0-02 PARTIAL、A0-03 NOT_RUN）。本批将阶段 1 裁定绑定到实际提交 SHA：
> A1 设计报告 `0df36de`、A2 ADR `960724b`、A1 实现 `e6f3aa6`（新增审阅对象）。所有结论仍限 **no-key** 范围。

### 8.0 环境重大变化（P1-OBS，必须先记录）

在本批审阅过程中（**2026-11-20T19:52:06Z→19:53:28Z 之间**），主工作树的冻结环境根
`/root/Autonomous Teacher/artifacts/` **被清空**（目录改为空，mtime 19:53）：

```text
19:52:06Z  rootfs_guard.py --rootfs <main artifacts frozen rootfs> --expected-sha 25491e45…
           -> verdict OK / sha_matches_expected=true / mount.read_only=false      (Reviewer 实测)
19:53:28Z  同一路径 -> stat: No such file or directory；artifacts/ 为空（仅 . ..）
19:54Z+    canonical 副本仍在 worktrees/a-next-rrev6/artifacts/security/rootfs，
           tar 规范化 sha256 = 25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0（Reviewer 实测）
           （该 worktree 还有 artifacts/foundation/deps 副本；推测为 A4/R-REV6 独占窗口环境迁移，
           未由 Lead 确认，本报告不臆断动机）
```

**影响与要求**：
1. **A0-03 工具对“真实冻结树”的现场验证窗口被环境迁移打断**：19:52:06 的真实树检查结果有效（工具行为正确），
   19:53 起主 artifacts 路径不再存在；本报告不再能对“当前 canonical 冻结树”复算 `25491e45`。
2. **不得**在 Packet v3/任何 OCI 前假定环境未变；需 Lead 确认 canonical 环境根位置（主 artifacts 恢复、
   或明确 a-next-rrev6 副本为输入）。在此之前 Packet/OCI 相关项保持 `NOT_RUN`。
3. 本报告 A0-03 结论只覆盖**工具行为与声明**（fake-tree + 19:52 真实树窗口），**不**覆盖真实部署防写。

### 8.1 A-PR0 文档（`docs/a-next-baseline` @ `e1fa0b9`，3 docs / +564）——**PARTIAL**

**独立核验（Reviewer 命令，UTC 19:50–20:05Z）**：

```text
$ git -C worktrees/a-next-baseline diff --name-status fd1d3a6..e1fa0b9
A docs/A_NEXT_BASELINE.md / A docS/A_NEXT_BRANCH_RECONCILIATION.md / A docs/A_NEXT_REVIEW_STATUS_RECONCILIATION.md
  → 只新增 3 个 docs；冻结 CSV/Review/src/tests 零改动

$ sha256sum docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv   -> 741d7d55…1382 (== 冻结值)
$ sha256sum docs/REVIEW_G4R_INDEPENDENT.md                                  -> 0599856a…446c (== 冻结值)
$ find docs/g4r_review_evidence -type f | wc -l                             -> 43
$ sha256sum * | sort | sha256sum (evidence dir)                             -> 8326e4ca… (== 文档声明)
$ 解析 A_NEXT_REVIEW_STATUS_RECONCILIATION §2 表：65 行；frozen 计数 29/14/12/4/6；
  与冻结 CSV 逐行对比 mismatch=0；表内无 CSV 之外 case_id
$ Reviewer 终态映射：PASS 25 / PARTIAL 18 / NOT_RUN 10 / UNVERIFIED 2 / NO_DIRECT 4 / N/A 6 = 65
```

**通过项（如实）**：
- 65 行逐 case 对账**数据一致**：frozen 列与 CSV 逐行相等；REV-01..08 终态与 Reviewer 报告完全一致
  （PASS/PASS/PARTIAL/PARTIAL/PASS/NOT_RUN/PASS/PARTIAL）；无“最终矩阵全 PASS”伪报；明确保留
  R2 L2 `PARTIAL`、R4-09/10 `NOT_RUN`、R5 `NOT_RUN`、G4-H `N/A(HUMAN)`。
- append-only 声明属实（新增 3 docs；§6 版本记录 + 冻结字节未改证明；未重打包 Packet）。
- H0 F-02 结论与 Reviewer 独立仲裁一致：G4-R 目录 fsync + `DURABILITY_UNKNOWN` 覆盖 H0 缺口 ⇒ cherry-pick=0。
- 证据 SHA（矩阵 `741d7d55`、Review `0599856a`、evidence dir `8326e4ca`、Packet v2 三 SHA）与 Reviewer
  实测一致；“交接写 45 份、实测 43 份”的 `NOTE` 正确（**Reviewer 早前消息写 45 为 Reviewer 笔误，以 43 为准**）。

**未通过项（须 append-only v2 更正，不得删原行）**：
1. **`R4-05`（SQLite backup provenance）被映射为 `PASS`（依据 `r_rev5_packet_verify`）——无 Reviewer 直接证据**。
   Reviewer 的 R-REV5 验证覆盖 Packet 全树/哈希/mutation 与 SQLite **只读可打开/immutable**，**未验证备份来源
   provenance**；Reviewer 报告正文亦未提 R4-05。应改为 `NO_DIRECT`/`PARTIAL`（保留 frozen PARTIAL）并注明。
2. **`R4-12`（Evidence path correction）被映射为 `PASS`（同上）——无 Reviewer 直接证据**。R-REV5 verifier 证据
   JSON 只有 `packet/status/expected_impl_sha/mutation_undetected/issues` 键，不含 path-correction 校验；
   Reviewer 报告只在 P2-02 观察中提到 F2-07 旧路径缺失/实际路径存在，不等于该行 PASS。
   （`R4-13` LiveGate reason snapshot equality 有 R-REV5 livegate 快照一致性支撑，保留 PASS 可接受。）

**裁定：PARTIAL**（数据/append-only/F-02 均属实；2 行过度归因 PASS）。**是否允许集成**：**可以（docs）**，
但必须先在 `A_NEXT_REVIEW_STATUS_RECONCILIATION.md` **追加 v2 更正 2 行**（保留原行；给出 old→new + 依据），
或在 Packet v3 引用时显式标注“R4-05/R4-12 无 Reviewer 直接证据、不作为 PASS 依据”。更正后本项可升 PASS。

### 8.2 A-PR0 工具（`chore/a-next-oci-hygiene` @ `16a4187`，9 files / +2244）——**PASS（条件）**

**范围**：仅新增 `docs/A_NEXT_ENV_HARDENING.md` + `scripts/a_next/{_common,oci_guard,rootfs_guard,ci_guard}.py`
+ `tests/a_next_hygiene/**`（**无 `src/`、无冻结件改动**）。

**Reviewer 亲自运行（20:00–20:15Z）**：

```text
$ pytest tests/a_next_hygiene -q -p no:cacheprovider        -> 38 passed in 3.09s (exit 0)

独立 fake-tree 探针（/tmp 隔离，未写冻结 rootfs）：
oci_guard:  check-rootfs frozen(path/hash) -> 10；workcopy(内容不同) -> 0；
            preflight 已存在 evidence -> 11；新 evidence -> 0；run 成功 -> 0；
            T0/T1 drift（wrapped 命令污染 fake frozen）-> 20 ("DRIFT")；
            pre-existing drift -> 23；run 以 frozen 为 --rootfs -> 10
rootfs_guard: OK -> 0；wrong sha -> 31；group/other writable(sha 匹配) -> 30；
              --require-ro-mount 在可写 tmp -> 32；missing path -> 33
ci_guard:    protected（真实 review 仓库，仅 docs 变化）-> 0；
            protected 违规（临时 git repo 改 security/gates.py）-> 33
真实冻结树（迁移前 19:52:06Z）：rootfs_guard -> OK / sha_matches=true / mount.read_only=false
```

**判定**：工具拒绝路径与退出码均按文档工作，测试真实（无 skip/弱化）；残余风险自述**如实**：
`--require-ro-mount` 在现 rw 挂载下 exit 32 是真实限制、hash 是事后证据、单 writer 锁是协作约定、
env 脱敏仅名称匹配、“已知 SHA 的内容副本也会被识别为 frozen（预期）”。**不构成安全边界**，与文档一致。

**前置条件（集成前）**：
1. Lead 确认 canonical 环境根后，在真实冻结树上复跑 `rootfs_guard`/`oci_guard check-rootfs` 并把输出绑定 UTC/SHA
   （当前主 artifacts 为空，见 §8.0）；**不得**以 rw 挂载声称“物理只读已达成”。
2. 在集成树复跑 `pytest tests/a_next_hygiene`（本批 38 passed 基于 16a4187 工作树）。
3. 使用守卫的 OCI 批次仍需按文档 T0/T1 执行；守卫仅为工程卫生层，不替代部署侧只读挂载/权限强制。

**裁定：PASS（条件）**。**是否允许集成**：**是**（scripts/tests/docs，均为新增卫生工具；不改 runtime/security 行为）；
但集成后 OCI/rootfs 结论仍不得写成 OS 强制或“全程无漂移”。

### 8.3 A-PR1/A1 实现（`fix/a-next-auth-record` @ `e6f3aa6`）——**PASS（条件）**

**范围独立核对**：`git diff --name-status fd1d3a6..e6f3aa6` = 4 files：`docs/A_NEXT_AUTH_RECORD_REPORT.md`
（A）、`src/autoteacher_m0/security/authorization.py`（M，+69/−18）、`tests/integration/a_next_auth/{conftest,test_a1_use_record_integrity}.py`（A）。
无其它 `src/`/受保护文件改动。

**Reviewer 亲自运行（20:01–20:12Z）**：

```text
$ pytest tests/integration/a_next_auth -q -p no:cacheprovider
  -> 39 passed in 80.54s (exit 0)
$ pytest tests/integration/g4r_auth tests/unit/security/test_authorization.py -q -p no:cacheprovider
  -> 73 passed in 298.66s (exit 0)   (G4-R R1 旧套件回归 + authorization 单测)
```

**Reviewer 自建对抗探针（/tmp，独立于 Owner 测试；9 组全部 PASS）**：
同 epoch 二次消费 `REPLAYED` / 异 epoch `EPOCH_MISMATCH`；**A 的合法 body 写入 B 的 record 文件名 →
`AUTHORIZATION_USE_RECORD_INVALID` 且不产生新 final**；reader expected-id 不匹配 → INVALID，匹配 → 返回 `(id, epoch)`；
`consumed_utc` 非法 → INVALID；截断 JSON → INVALID；`nlink==2`（final+崩溃 temp）→ `REPLAYED`（容忍窗口保持）；
**FIFO → INVALID 且 <5s 不阻塞**；8 线程×5 轮并发恰 1 accepted、其余稳定 REPLAYED；模块路径绑定到本 worktree `src`。

**代码审阅**：校验严格单调收紧（`_IDENTIFIER`、`sha256(id)+".json"` path 绑定、expected-id、`_UTC_TEXT` 三处新增），
不新增错误码、无 `os.replace`/O_CREAT 直写 final 回退、`O_NONBLOCK` 仅影响特殊节点、私有签名变更仅 2 个内部调用点
+ 测试；`DURABILITY_UNKNOWN`/dir fsync 语义不变。Owner 报告 §6 的 A1 测试/回归计数与 Reviewer 独立结果一致
（39 passed；回归 73 passed 为本报告口径，Owner 拆分计数不同但无矛盾）。

**前置条件（集成前）**：
1. 合入顺序：A1 先冻结、A2 rebase（A2 ADR §11 已列）；A1 合入后复跑 `tests/integration/a_next_auth` +
   `tests/integration/g4r_auth`。
2. A1 报告 §6.4“提交后 HEAD 复跑”以 Reviewer 本次 `e6f3aa6` 独立结果为准（39 passed）；若后续再次改分支须重新绑定。
3. A6 Handoff 的 BLK-08/D-14 在 A1 合入后需 append-only 更新（见 §8.4）。
**裁定：PASS（条件）**。**是否允许集成**：**是**（安全加严、no-key；不改变任何门状态）；条件 1 未完成前不得宣称
“P2-01 已在 canonical 线关闭”。

### 8.4 A6 文档（`docs/a-next-handoff` @ `13e39a4`，4 docs / +760）——**PASS（条件）**

**独立核对**：
- 只新增 4 个 docs（HUMAN_HANDOFF / G4H1_RUNBOOK / PROVIDER_CONTRACT / PRICE_USAGE），**零 `src/`/冻结件/状态常量改动**。
- 状态常量未改写：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`（逐文档出现且一致）。
- **D-01..D-22 = 22 行全部 `UNSIGNED`**；文档声明“Agent 代签/代批=0、全部空白”；签署方式要求人类填 ACCEPT/FIX/BLOCK/DEFER+姓名/UTC/依据。
- **BLK-01..BLK-18 = 18 项**（`grep -c '| BLK-'`=18）；抽查 BLK-01（route/egress 不一致，`egress.py:31-34` opencode.ai
  allowlist）、BLK-06（LiveGate 常量）、BLK-07/08（P2-02/P2-01）、BLK-09（DURABILITY_UNKNOWN 无消费方）、
  BLK-14（dsh target profile）、BLK-17（R-REV6 NOT_RUN）均**有源码/审查依据**，不是空话。
- X-01..X-08 差异表抽查行号真实：`gates.py` 6 个 reasons（含 `BASELINE_OR_CONFIGURATION_CHANGED`）、
  `live_controller.py:66-70` 5 项 `EXTERNAL_*` 恒 BLOCKED、`settings.py` 默认 `deepseek-official`、
  `authorization.py:988-1097` 原子 publish 描述、`egress.py` 第三方 allowlist——与 Reviewer 既有认知一致。
- Provider/Price 文档明确“**2026-11-19 研究快照、未获批、未真实调用**”，未把研究事实写成 Live 验证；
  价格/usage 状态如实标 `UNVERIFIED`/`PARTIAL`（不冒充 PASS）。

**发现（须 append-only 更新，不否决）**：
- `BLK-08`（P2-01 body id 未交叉校验）与 `D-14`（P2-01/P2-02 处置）仍按“P2-01 OPEN”写在 `fd1d3a6` 基线；
  A1 实现已在独立分支 `e6f3aa6` 修复 P2-01（Reviewer 本批验证）→ **合并后必须 append-only 更新**为
  “P2-01 已由 A1 e6f3aa6 修复，待合入/复测；P2-02 仍 OPEN”，不得删旧行。
- `D-02` 引用 Packet v2 身份；A-PR4 将建 Packet v3 时应追加引用新身份（新目录/新 SHA/旧包只读）。

**裁定：PASS（条件）**。**是否允许集成**：**是（docs）**；条件是同步 append-only 更新 BLK-08/D-14（A1 合并后）、
且保持全部 D 项 `UNSIGNED`、18 BLK 不减项；不得凭本包宣称任何门通过。

### 8.5 本批汇总（Stage-2 batch-1）

| 对象 | 提交 SHA | 裁定 | 是否允许集成 | 前置条件 |
|---|---|---|---|---|
| A-PR0 文档（baseline/branch/review-status） | `e1fa0b9` | **PARTIAL** | 可以（docs），需先 v2 更正 | 更正 R4-05/R4-12 过度归因；append-only 保留原行 |
| A-PR0 工具（OCI/rootfs/CI hygiene） | `16a4187` | **PASS（条件）** | **是** | canonical 环境确认后真实树复跑；集成树 38 tests 复跑；不得宣称 OS 只读 |
| A-PR1/A1 实现（P2-01） | `e6f3aa6` | **PASS（条件）** | **是** | A1 先冻结→A2 rebase→合并后复跑；A6 BLK-08/D-14 更新 |
| A6 文档（human handoff/runbook/provider/price） | `13e39a4` | **PASS（条件）** | **是（docs）** | 合并后 append-only 更新 BLK-08/D-14；D 全 UNSIGNED、BLK 不减项 |
| A0-02 终态 | — | **PARTIAL**（v2 更正后 PASS） | 同 A-PR0 文档 | 同上 |
| A0-03 终态 | — | **PASS（工具层）/ NOT_RUN（真实部署防写）** | 工具同 A-PR0 工具 | 真实树复跑 + 人类部署只读；19:53 环境迁移未确认 |
| 阶段 1 裁定绑定 | A1 设计 `0df36de`；A2 ADR `960724b`；A1 实现 `e6f3aa6` | 维持 | — | A2 实现 SHA 待 Lead 提供后追加 |

**本批未改变任何门状态**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`；P2-02 仍 OPEN；B03/E5-P04 仍 UNVERIFIED；
R-REV6 仍 NOT_RUN。**本报告不构成任何 PASS 授权、部署许可或 M0 GO。**

### 8.6 下一批（等待 Lead）

- 待落定后审：A2 实现（run admission 接线）、A3 registry、A4 R-REV6 L2（独占窗口/双 principal/Fake-only）、
  A-PR0 文档 v2 更正、Packet v3 全树 mutation（未列文件/sidecar/symlink/hardlink/mode/hash/删除）、65+19 矩阵逐 ID 终态。
- 环境项：Lead 确认 canonical artifacts 根后，Reviewer 重跑真实冻结树 rootfs_guard/oci_guard 并绑定 SHA/UTC。

---

## 附录 C：阶段 2（第一批）证据命令（绑定 §8）

```text
A-PR0 docs:  git -C worktrees/a-next-baseline diff --name-status fd1d3a6..e1fa0b9  -> 3 A docs
             sha256sum 冻结 CSV -> 741d7d55…；REVIEW -> 0599856a…；evidence 43 files -> 8326e4ca…
             Python 解析 §2 表 -> 65 rows / frozen 29,14,12,4,6 / mismatch 0 / reviewer 25,18,10,2,4,6
A-PR0 tools: pytest tests/a_next_hygiene -q -> 38 passed in 3.09s
             /tmp fake-tree probes: oci_guard 10/0/11/0/0/20/23；rootfs_guard 0/31/30/32/33；ci_guard 0/33
             19:52:06Z real rootfs_guard -> OK sha_matches=true mount.read_only=false
             19:53:28Z main artifacts/ -> empty（环境迁移；canonical copy at a-next-rrev6 = 25491e45…）
A1 impl:     pytest tests/integration/a_next_auth -q -> 39 passed in 80.54s
             pytest tests/integration/g4r_auth tests/unit/security/test_authorization.py -q -> 73 passed in 298.66s
             Reviewer 自建 /tmp/a1_adversarial_probe.py -> 9 groups PASS（foreign body id / expected / FIFO / nlink2 / 并发…）
A6 docs:     git -C worktrees/a-next-handoff diff --name-status fd1d3a6..13e39a4 -> 4 A docs
             grep 状态常量/UNSIGNED/BLK -> 22 D rows UNSIGNED、18 BLK、状态常量一致
```


---

## 9. 环境事件 `INCIDENT_20261121`（append-only；Lead 披露 + Reviewer 独立复验）— 2026-11-20T19:53Z

> 本章节按 Lead 指令追加，**不改动已提交的阶段 1/§8 字节**；阶段 1 的 rootfs=25491e45… 记录早于事件，
> 事件后经恢复仍为 25491e45…，二者不矛盾（§9.4）。本章节所有“原因/操作”归因以 Lead 披露为来源
> （`LEAD_REPORTED`），Reviewer 只对**可复验结果**负责。

### 9.1 时间线（UTC，2026-11-20）

| 时间 | 事件/证据 | 来源 |
|---|---|---|
| ≤19:52:06 | Reviewer 真实冻结树探针：`rootfs_guard --rootfs <main artifacts frozen rootfs> --expected-sha 25491e45…` → verdict `OK`、`sha_matches_expected=true`、`violation_count=0`、`read_only=false` | **Reviewer 实测（pre-incident）** |
| 19:53Z | Lead 清理陈旧 `/tmp` bind mount 时误删主仓库 gitignored `artifacts/`：`rm -rf /tmp/at-f4-clean` 递归进入其 bind 子挂载 `/tmp/at-f4-clean/artifacts` → 即 repo `artifacts/` | `LEAD_REPORTED` |
| 19:53:28 | Reviewer 独立观察到主 `artifacts/` 为空、原路径 `stat: No such file or directory`；`find` 全盘未见 v1 Packet 目录 | **Reviewer 实测（事件当时）** |
| 19:56 | 备份 tar 生成：`/root/a-next-artifacts-restored-20261121.tar`（916,480,000 bytes），**sha256 `11172f0268cdf2dc2bde08e90d9d93c0a444b134f8eaab9a712057c9d5159d42`**（Reviewer 独立复算一致） | Lead + Reviewer 实测 |
| 19:56+ | 恢复来源：`/tmp/at-g4f-review/artifacts` + 各 worktree artifacts 副本，no-clobber 合并；Lead 复算 rootfs/deps/Packet v2 | `LEAD_REPORTED` |
| 20:25–20:35 | Reviewer 独立复验：rootfs canonical=`25491e45…`；deps canonical=`e07729d7…`；Packet v2 独立 verifier=**PASS**（issues=[]/mutation_undetected=[]）；v1 Packet 全盘/备份 tar 均无副本 | **Reviewer 实测（post-restore）** |

### 9.2 损失清单（不可恢复项）

**`LOST_IN_INCIDENT_20261121`**：

1. **v1 Packet 原始字节**：`artifacts/review-packet-g4f-e7d92967…` 目录及其文件（记录值 manifest `4aed2a92…1d7f2`、
   hashes `421b07ae…9d3d`）——全盘 `find -name "*e7d92967*"` 无结果、备份 tar 列表中无该目录 ⇒ **原始字节不可再核验**；
   记录的 manifest/hashes 值只能作为**历史登记值**引用，不得再作为可复算证据。
2. **部分 G4-R 原始运行证据**：`artifacts/g4r/**` 仅部分恢复（当前 116M，含 final-prep/integration/r0/r1/r2/r4/registry/logs
   等子目录），**完整性不可证明**；依赖这些原始日志逐字节复算的结论降级为历史记录。
3. 任何“v1 Packet 未改写/可核验/环境全程 NO_DRIFT”类结论 → 一律标记 **`LOST_IN_INCIDENT_20261121`（不可再核验）**，
   不得写入任何当前或未来 PASS 依据。

### 9.3 独立复验结果（Reviewer 命令，post-restore）

```text
$ tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . | sha256sum
  -> 25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0   (canonical 一致)
$ tar ... -C artifacts/foundation/deps . | sha256sum
  -> e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98   (Lead 声明 e07729d7 一致)
$ sha256sum /root/a-next-artifacts-restored-20261121.tar
  -> 11172f0268cdf2dc2bde08e90d9d93c0a444b134f8eaab9a712057c9d5159d42   (与 Lead 一致)
$ python scripts/g4r_review/r_rev5_packet_verifier.py       --packet artifacts/review-packet-g4r-v2-d33e0aab… --expected-impl-sha d33e0aab…
  -> {"status":"PASS","issues":[],"mutation_undetected":[]}  (Reviewer 自建 verifier，复活旧 R-REV5 工具独立复验)
$ rootfs_guard.py --rootfs artifacts/security/rootfs --expected-sha 25491e45… --emit-commands
  -> verdict OK / sha_matches_expected=true / violation_count=0 / mount.read_only=false   (exit 0)
$ oci_guard.py check-rootfs <restored frozen rootfs> --frozen-rootfs … --frozen-sha 25491e45…
  -> verdict rootfs_is_the_frozen_tree   (exit 10)
$ find / -maxdepth 8 -name "*e7d92967*"            -> 无结果
$ tar -tf /root/a-next-artifacts-restored-20261121.tar | grep -i "review-packet-g4f" -> 无结果
```

### 9.4 对既有结论的影响（逐项）

1. **阶段 1 的 rootfs 记录**（`25491e45…`，19:35Z 复算）**保留有效**，且与事件前 19:52:06 探针、事件后 20:3x
   恢复复验三处一致；**不矛盾**。事件只破坏中间带外状态，不改变该哈希的历史事实。
2. **G4-R 冻结 Review（`e72255d`/`0599856a…`，本报告只读引用）**：其中
   “v1 Packet 未改写/可核验”结论（§1.3/R-REV1/R-REV5 的 v1 部分）标记 `LOST_IN_INCIDENT_20261121`；
   该 Review 的 **R-REV5 对 Packet v2 的验证仍有效**（本次已用 Reviewer 自建 verifier 对恢复后 v2 独立复核 PASS）。
3. **A-PR0 文档（`e1fa0b9`）**：`A_NEXT_BASELINE.md` §5 的 A0-04“v1/v2 Packet 只读哈希核对 PASS”中 **v1 部分
   → LOST_IN_INCIDENT_20261121**（A0-04 降为 **PARTIAL/LOST**）；`A_NEXT_REVIEW_STATUS_RECONCILIATION.md` §4 的
   v1 证据行同样标注 LOST。该文档的其余 65 行对账/append-only/F-02 结论不受影响。
4. **A-PR0 工具（`16a4187`）**：恢复后真实树 rootfs_guard/oci_guard 已可独立复验（§9.3 结果）；工具本身行为
   与 §8.2 一致。但 OCI/rootfs 的未来证据必须标注“**输入恢复自经哈希验证的副本**”。
5. **A0-03（rootfs 防写/不可变）**：当前 canonical 树已恢复且哈希匹配，但 **provenance 含恢复步骤**；
   A0-03 工具层结论维持 **PASS（条件）**，但条件扩展为：任何 OCI/L2 证据须注明
   `rootfs/deps restored 2026-11-21 from hash-verified copies（backup tar sha 11172f02…），非原始 in-place 链`；
   真实部署只读仍 **HUMAN_REQUIRED / NOT_RUN**；不得写“全程 NO_DRIFT”。
6. **A5（Packet/证据卫生）**：v1 Packet 丢失 + `artifacts/g4r` 部分恢复 ⇒ A5 不能宣称“全部 Packet/证据可核验”；
   **A5-hygiene 降为 PARTIAL**。Packet v3 必须在 manifest/report 中披露本事件与恢复来源，并附恢复证据。
7. **A6 文档（`13e39a4`）**：原 BLK-18/D-08 只覆盖 G4-R rootfs 漂移/旧 junit 事件，**未覆盖本事件**；
   保持 §8.4 PASS（条件），新增条件：append-only 追加本事件披露（新 BLK 项/扩展 D-08 与 D-10）、
   Runbook 补充恢复/备份/防再发程序；不得改写状态常量。

### 9.5 最终裁定必要条件（Lead 要求：事件披露 + 恢复证据 + 未来防再发）

以下为后续任何 A0/A5/Packet v3/最终裁定要判 PASS 的**必要条件**（不满足即不得 PASS）：

1. **事件披露（Disclosure）**：在 A-PR0 baseline/reconciliation 与 A6 handoff/runbook 的 append-only 章节记录
   本事件（时间线、影响、损失、`LOST_IN_INCIDENT_20261121` 标记）；所有 Packet v3/报告/矩阵不得出现
   “全程 NO_DRIFT/环境无损/证据完整”表述。
2. **恢复证据（Restore evidence）**：保留并登记 `backup tar sha 11172f02…`、恢复来源清单、恢复后 rootfs
   `25491e45…`/deps `e07729d7…`/Packet v2 verifier PASS 的复算记录；恢复操作与验证者分离
   （Lead 执行、Reviewer 独立复核，本报告 §9.3 即样例）；Packet v3 manifest 附恢复说明与源 SHA。
3. **未来防再发（Prevention）**：
   - 清理/删除操作前检查 bind mount 与真实路径（禁止对可递归进入挂载点的目录执行 `rm -rf`；先 stop/umount 并
     `realpath`/`findmnt` 确认目标）；
   - gitignored artifacts（Packet/rootfs/deps/Stage/证据）必须有**仓库外备份/校验清单**（备份 tar + sha256 登记）；
   - 环境完整性检查前置化（rootfs_guard/oci_guard T0/T1；Packet 独立 verifier）并写入 Runbook；
   - 任何恢复后继续使用的证据标注“恢复自经哈希验证副本”，不得冒充连续原始链。

### 9.6 门状态（不变）

本事件及本章节**未改变**任何门：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`；P2-02 OPEN、B03/E5-P04 UNVERIFIED、
R-REV6 NOT_RUN。本报告不构成部署许可/M0 GO。

---

## 附录 D：事件复验证据（§9）

```text
backup tar: /root/a-next-artifacts-restored-20261121.tar 916480000 bytes
            sha256 11172f0268cdf2dc2bde08e90d9d93c0a444b134f8eaab9a712057c9d5159d42
rootfs:     tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner ... | sha256sum
            = 25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0
deps:       same recipe -> e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98
packet v2:  Reviewer r_rev5_packet_verifier.py --packet <restored> --expected-impl-sha d33e0aab…
            -> {"status":"PASS","issues":[],"mutation_undetected":[]}
v1 packet:  find / -maxdepth 8 -name "*e7d92967*" -> none; tar -tf backup.tar | grep review-packet-g4f -> none
```


---

## 10. 阶段 2 batch-2：A-PR2 Registry 裁决独立复核 — 2026-11-20T20:00Z–20:50Z

### 10.1 审阅对象与范围（独立核对）

| 项 | 值（Reviewer 实测） |
|---|---|
| 分支/HEAD | `feat/a-next-registry` @ **`e09ac7c47c0193a54a7e541edde3185d88bf66a0`**（parent `fd1d3a6`；`c4500f8` 脚本/测试 + `e09ac7c` docs） |
| 变更 | `git diff --name-status fd1d3a6..e09ac7c` = **6 A 文件、+1635**：`docs/A_NEXT_REGISTRY_DECISION.md`、`scripts/a_next/registry/{run_matrix.py,fake_bridge.py,forged_replay_attack.py,probe_plugin/lib/index.js}`、`tests/a_next_registry/test_registry_attack_matrix.py` |
| 未改 | `git diff fd1d3a6..e09ac7c -- src/ config/` = **空**；`config/g4/runtime-policy.json` sha256 **d0851a41…**（与基线一致）；`registry_status` = `UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT` **未改**；`config/g3d/candidate/bridge.patch.yml` sha **0cf5d340…**（与 identity 一致） |
| 边界 | 0 容器/0 podman/0 frozen rootfs 直挂（`grep podman|docker|--rootfs` 无）；0 真实 Key/Provider/HTTP（见 §10.5）；A4 独占窗口期间 Reviewer **未跑 OCI** |

### 10.2 独立复跑（不采信 Owner）

```text
$ pytest tests/a_next_registry -q                       -> 6 passed, 1 skipped (skip=gated runtime, 0.12s)
$ ruff check scripts/a_next tests/a_next_registry       -> All checks passed!
$ G4R_RUN_RUNTIME=1 G4R_STAGE=<恢复后 stage> pytest tests/a_next_registry -q
  -> 7 passed in 17.46s（与 Owner 自称 7 passed/17.49s 一致；runtime 集成被真实执行，非 skip）
$ python scripts/a_next/registry/run_matrix.py --all --stage <恢复后 stage> --out /tmp/a-next-registry-reviewer-run
  -> 11/11 modes EXIT=0；verdict 与 Owner 矩阵逐项一致（baseline/register-unregister/schema-drift/
     duplicate-name/internal-execute/observer-loss/late-bash-before-dispatch/two-turn-bash/
     two-turn-internal-execute/two-turn-title/resume）；/work 已清理、worktree status=clean
```

**恢复后 stage 独立校验（因 INCIDENT_20261121 原 path 已删）**：使用
`worktrees/a-next-rrev6/artifacts/g3c/stage`（restored copy），**逐文件 SHA 与 identity/policy 完全一致**：
bridge build `2cb42461…`（== policy `stage_binding.adapter_built_js_sha256`）、skill `521bc0f1…`、
dsh-tools `5d95d7f4…`、dsh-llm `45f7d934…`、cordis `70be1056…`；Runtime binary **1cc41d5a…** 一致。
=> Owner 声称的 runtime 证据可在恢复副本上**按 SHA 复现**（Reviewer 已复现 7 passed + 11/11 modes）。

### 10.3 forge / replay / suppress 攻击独立验证（Reviewer 自写 verifier，不 import Owner 攻击脚本）

对 Owner 原始 L1 记录（genuine=`20261120T194522Z-late-bash-before-dispatch`，8 条；clean=baseline，4 条）
用 Reviewer 自写 naive verifier（dispatch face 全部命中 approved `{skill_lookup}` 才接受）：

```text
genuine (未篡改)          -> accepted=false, unapproved=["bash"]   (命中 true 负面基线)
forge   (改 face 为干净)  -> accepted=true                          (攻击成功)
replay  (干净 run 换 label)-> accepted=true                         (攻击成功)
suppress(删违规+补干净)   -> accepted=true                          (攻击成功)
record 字段扫描: 无 MAC/signature/nonce/controller-binding 字段（trust_binding_fields=[]）
REVIEWER A-PR2 ATTACK PROBE: PASS
```

结论与 Owner `attack-report.json` 一致：**L1 自报 JSONL 可被 forge/replay/suppress，不能升格为 attestation**；
该结论是**负面安全结论**，不是“Registry 通过”。

### 10.4 观测链与内部执行证据审核

- `two-turn-bash`（Owner run，Reviewer 复现）：turn1 face `[skill_lookup]` 放行 → turn 间注册 `bash` → turn2
  face `[bash, skill_lookup]`、`unknown=[bash]`、`enforcement_denial=true`、**fake bridge 只收到 1 次 request**
  ⇒ “不只检查首轮”成立（turn2 未到 adapter）。
- `late-bash-before-dispatch`：`denial=true`、face 含 bash/unknown；Reviewer 独立 —all 复现同 verdict
  （该 run 即 Owner attack-report 的 genuine 来源 **`attack_run`**）。
- `two-turn-internal-execute`：原始 probe 证据显示 turn1 dispatch face `[skill_lookup]` → 两 turn 间
  `between_turns:marker:registered`（epoch2）→ `internal_execute` 成功（sentinel `19:45:40.224Z`）→
  `marker:unregistered`（epoch3）→ turn2 dispatch face **仍为 `[skill_lookup]`**；fake bridge 仅 2 个 request、
  `tools` 均只 `[skill_lookup]` ⇒ 内部工具执行确实可完全不出现在 Provider request；Owner doc 判
  `MEASURED_PASS`（机制观测）合理。
- `observer-loss`：probe 只写 2 条即停（`failAfterRecords=2` **注入故障**，Owner 表已注明），Runtime exit 0 且继续运行；
  Owner 判为“evidence gap 已证、非 fail-open”**分类诚实**（Reviewer 独立复现 probe_records=2/exit 0）。
- `resume`/`two-turn-title`：Reviewer 独立复现 `two-turn-title` 2 dispatch/2 bridge request、无 title purpose；
  resume 进程 2 成功 dispatch；`compaction-effective-registry` 保持 `UNVERIFIED`（未启用/未触发）——**诚实**。

### 10.5 裁决诚实性核验（A3-01/A3-02 / B03/E5-P04 / 无 Key）

- **A3-01**（handoff：`Either independent trusted snapshot and tool-exec deny or explicitly UNVERIFIED`）：
  文档 §0 三选一明确给出 **`UNVERIFIED`**，并给出 A 要件缺失（无 candidate-immutable registry 导出；唯一
  registry 入口是同进程/同 UID Cordis 插件）——与 Reviewer 独立代码/证据一致；**满足“explicitly UNVERIFIED”**。
- **A3-02**（two-turn resumed late registration + observer-loss 分类诚实）：L1 分类诚实（见 §10.4）；
  但**真实 DSH resumed late-registration / observer-loss 的 L2 未执行**（Owner 标 `NOT_RUN`/`UNVERIFIED`），
  矩阵行不得升级为 PASS。
- **B 补偿控制**：文档明确 B ≠ Registry 关闭，内部工具风险依赖 OS sandbox（**A4 L2 NOT_RUN**），
  `B03/E5-P04` **维持 `UNVERIFIED`**，E5-Full/G5 不因 B 放行——**诚实，无安全降级**。policy `registry_status`
  未被改写（Reviewer 实测 sha 与基线一致）。
- **无 Key/无 Provider/无 HTTP**：`env -i` + `unshare -n`（代码实测）、fake bridge AF_UNIX、无 http/net import、
  `real_provider_calls=0`（注意：`real_key_present`/`real_provider_calls` 字段是 runner **硬编码声明**而非实测，
  属 P3 证据措辞 nit；结构上由隔离/合成 bridge 支持）。
- **未误改 config/registry_status**：见 §10.1（diff 空 + sha 一致）。

### 10.6 发现（本批无 P0/P1；P2/P3 如下）

- **P2-A3-1（复现路径断裂/事故 provenance）**：`run_matrix.py` `DEFAULT_STAGE = /tmp/at-f4-clean/artifacts/g3c/stage`
  （INCIDENT_20261121 已删除）；identity.txt 与各 run-summary `stage_dir` 也指向该已消失路径。文档“复现命令”
  `python3 scripts/a_next/registry/run_matrix.py --all` 不带 `--stage` 现在会失败。**要求**：显式 `--stage`（或更新
  DEFAULT_STAGE 为恢复后路径）+ 文档/identity append-only 注明“stage 恢复自经哈希验证副本（a-next-rrev6，
  bridge 2cb42461…）；Reviewer 已按恢复副本复现 7 passed + 11/11 modes”。
- **P2-A3-2（矩阵行遗漏）**：§2.2 状态表未列 `late-bash-before-dispatch`（该 run 是 attack-report 的 genuine
  `attack_run`，也是 denial 证据源之一）；应补一行（L1 MEASURED，denial/unknown 分类）或在 §3 攻击证据处显式引用。
- **P2-A3-3（“host 复验 19:56Z”无可核文件）**：`ATTACK_MATRIX_INDEX.json` 只有 `generated_utc 19:54:00` 与 runs，
  无 host-verification 记录；文档首页“host 复验 19:56Z 前后”**缺少对应证据文件**。要求：补证据或删掉该表述
  （Reviewer 本批已独立复跑 7 passed/17.46s + 11/11 modes，可作为独立 host 复验替代记录）。
- **P3-A3-4（状态词汇）**：表中 #14–16 用 `MEASURED_PASS` 表示“攻击成功（负面结论成立）”，虽同表说明
  但易被误读为安全 PASS；建议改标 `ATTACK_CONFIRMED（负面结论）`，并在 A3-01/A3-02 记录中保留 “not Registry PASS”。
- **P3-A3-5（identity 行内不一致）**：identity.txt `# worktree … head: fd1d3a6` 与同文件 `final_commits … head=e09ac7c` 不一致
  （按最终提交 e09ac7c 为准即可；不影响证据哈希）。
- **P3-A3-6（summary 字段）**：`real_key_present=false`/`real_provider_calls=0` 为 runner 常量声明，非独立测量；
  建议改为“由 design/isolated runner 保证”措辞，避免被当作量测证据。

### 10.7 裁定（A-PR2）

| 项 | 裁定 | 是否允许集成 | 前置条件 |
|---|---|---|---|
| **A-PR2 Registry 裁决（A3-01 `UNVERIFIED` + B 补偿控制）** | **PASS（条件）** | **是（docs/scripts/tests；无 runtime/config 变更）** | C1–C5 |
| A3-01 终态 | **UNVERIFIED**（保留，不得升级） | — | 由人类/安全 Reviewer 决定是否投入方案 A |
| A3-02 终态 | **L1 分类 PASS；L2 真实 DSH resumed late-registration/observer-loss = NOT_RUN** | 矩阵行不得写 PASS | A4 L2 独立证据 |
| B 补偿控制 | **条件式可用**（依赖 OS sandbox 证明） | 条件式 | A4 L2 `NOT_RUN` 前不得作为 G4-H1 放行依据 |
| B03/E5-P04 | **UNVERIFIED（不变）** | — | 不得以本 PR 关闭 |
| 误改 config/registry_status | **未发生（实测）** | — | 保持 |

**C1（必做，Packet v3 前）**：修复 `DEFAULT_STAGE`/复现路径 + identity/run-summary 恢复 provenance 标注（P2-A3-1）。
**C2（必做）**：§2.2 补 `late-bash-before-dispatch` 行/引用（P2-A3-2），并补/删“host 复验”表述（P2-A3-3）。
**C3（必做）**：A3-01/A3-02 状态按 §10.7 写入矩阵与 Packet v3；A3-01 保持 `UNVERIFIED`；A3-02 仅 L1-classified，
L2 行 `NOT_RUN`。
**C4**：B 补偿控制只在 A4 L2 OS sandbox 证据到位后可作为 G4-H1 前置；`B03/E5-P04` 保持 `UNVERIFIED`，
不得出现“Registry 已关闭/已通过”。
**C5**：状态词汇/identity/summary 字段修正（P3-A3-4/5/6）；保留本事件/恢复 provenance（§9）与 `ATTACK_CONFIRMED`
负面结论性质。

> **本 PR 不改变任何门**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
> `M0=DECISION_PENDING`；`B03/E5-P04=UNVERIFIED`；A-PR2 为“诚实 UNVERIFIED + 攻击矩阵 L1”，**不是** Registry 通过。

---

## 附录 E：A-PR2 复核命令与输出（§10）

```text
$ git -C worktrees/a-next-registry diff --name-status fd1d3a6..e09ac7c  -> 6 A files
$ git -C worktrees/a-next-registry diff fd1d3a6..e09ac7c -- src/ config/ -> empty
$ sha256sum config/g4/runtime-policy.json -> d0851a41…8066 (unchanged); registry_status unchanged
$ pytest tests/a_next_registry -q -> 6 passed, 1 skipped (0.12s)
$ ruff check scripts/a_next tests/a_next_registry -> All checks passed!
$ G4R_RUN_RUNTIME=1 G4R_STAGE=worktrees/a-next-rrev6/artifacts/g3c/stage     pytest tests/a_next_registry -q -> 7 passed in 17.46s
$ python scripts/a_next/registry/run_matrix.py --all --stage <restored stage> --out /tmp/a-next-registry-reviewer-run
  -> 11/11 modes exit 0, verdicts match Owner matrix; /work cleaned; worktree clean
$ reviewer /tmp/a-pr2_independent_attack_probe.py
  -> genuine rejected UNAPPROVED bash; forge/replay/suppress accepted; trust_binding_fields=[]
  -> REVIEWER A-PR2 ATTACK PROBE: PASS
恢复 stage 哈希: bridge 2cb42461… / skill 521bc0f1… / dsh-tools 5d95d7f4… / dsh-llm 45f7d934… /
                cordis 70be1056… / runtime 1cc41d5a…（均 == identity/policy）
```


---

## 11. 阶段 2 batch-3：A-PR2 条件修正复核（`748fd0a`）— 2026-11-20T20:18Z–20:30Z

### 11.1 对象与范围

| 项 | Reviewer 实测 |
|---|---|
| 分支/HEAD | `feat/a-next-registry` @ **`748fd0a529270a11b42ca4be23c096fb1b6f9e14`**（parent `e09ac7c`；`4cc3a26` fix(C1/C5) + `748fd0a` docs(C2/C3/C5)） |
| 变更 | `git diff --name-status e09ac7c..748fd0a` = **3 M**：`scripts/a_next/registry/run_matrix.py`、`docs/A_NEXT_REGISTRY_DECISION.md`、`tests/a_next_registry/test_registry_attack_matrix.py`（+135/−24） |
| 未改 | `git diff fd1d3a6..HEAD -- src/ config/` = **空**；policy `registry_status` 仍 `UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT` |

### 11.2 C1（复现路径 + fail-closed SHA）——**通过**

代码核对（`run_matrix.py`）：`DEFAULT_STAGE = /tmp/at-f4-clean/...` 已删除；新增
`DEFAULT_STAGE_CANDIDATES = (<repo>/artifacts/g3c/stage, worktrees/a-next-rrev6/artifacts/g3c/stage)`、
`EXPECTED_STAGE_SHA256`（bridge/skill/dsh-tools/dsh-llm/cordis 五值，与 identity/Reviewer 已核值一致）、
`STAGE_RECOVERY_NOTE`；`locate_stage()` 启动前逐文件校验 SHA（`STAGE_SHA_MISMATCH` fail-closed），
无候选则 `STAGE_MISSING`；run-summary 新增 `stage_verification`/`stage_recovery_note`/`exit_code`；
argparse `--stage` 默认 `""`（不再硬编码已消失路径）。

Reviewer 独立运行（**不带 `--stage`**）：

```text
$ run_matrix.py --mode baseline --out /tmp/a-next-registry-c1-review
  -> run 20261120T201850Z-baseline, exit 0, verdict MEASURED_PASS
     stage_dir=/root/Autonomous Teacher/worktrees/a-next-rrev6/artifacts/g3c/stage
     stage_verification.verified=true（5 个 expected SHA 全部列出）
     stage_recovery_note="stage recovered from hash-verified copy (a-next-rrev6 worktree, INCIDENT_20261121)…"
$ run_matrix.py --mode baseline --stage /tmp/fake-stage-c1   -> exit 1, ValueError: STAGE_SHA_MISMATCH（fail-closed）
$ run_matrix.py --mode baseline --stage /tmp/does-not-exist  -> exit 1, FileNotFoundError: STAGE_MISSING（fail-closed）
```

Owner 复跑 run `20261120T200752Z-baseline` / `20261120T200757Z-two-turn-bash`：`stage_verification.verified=true`、
`exit_code=0`、`stage_recovery_note` 存在；`identity.txt` 已更正（base `fd1d3a6` vs final head 关系、Stage 恢复声明、
新脚本 SHA `8067fcea…` 与当前文件一致）。`pytest tests/a_next_registry -q` = **8 passed, 1 skipped**（新增 2 个 C1
fail-closed 单测）；runtime 集成 = **9 passed in 17.33s**（Owner 9/17.44s，一致）；ruff All checks passed。

### 11.3 C2（矩阵行 / 无可核表述 / 引用独立复验）——**通过**

- §2.2 新增 **7a 行**：`late-bash-before-dispatch`（genuine attack run 供 #14–16 使用），记录
  face=`[bash, skill_lookup]`/unknown=[bash]/enforce deny/未到 adapter（无 bridge 请求）。
- 文档头部删除无证据的“host 复验 19:56Z”表述，改为“更正轮复跑 20:07:52Z/20:07:57Z（默认 Stage 恢复副本）”。
- 文档明确引用 **Reviewer 独立复验**（7 passed/17.46s + 11/11 modes），标注为 Reviewer 结论而非 Owner 自证。

### 11.4 C3（裁决映射）——**通过**

新增 §0.1 映射表：`A3-01 = UNVERIFIED（保留）`、`A3-02 = L1 分类 PASS / L2 NOT_RUN`、
`B03/E5-P04 = UNVERIFIED（维持）`、B 补偿控制“条件式，依赖 A4 L2 OS sandbox 证明”、
Registry **未关闭**（不得表述为 verified/closed）。

### 11.5 C5（措辞/identity/隔离声明）——**通过**

- #14–16 状态由 `MEASURED_PASS = attack succeeded` 改为 **`ATTACK_CONFIRMED（负面结论…）`**，并加注
  “ATTACK_CONFIRMED 更不是 PASS”。
- `key_and_provider_nonuse` 替代硬编码 `real_key_present/real_provider_calls`，明确“由隔离设计保证、非运行时实测”；
  identity.txt 同步为设计声明并列出恢复 Stage 的 5 个 SHA。
- `ATTACK_MATRIX_INDEX.json` 已重生成（generated_utc 20:10:00Z），含 corrections/historical_fields/stage_recovery
  notes 与新增 2 个恢复 Stage run；`/work` 清理、worktree clean。

### 11.6 残余 nit（P3，不阻塞）

1. fail-closed 以裸 `ValueError`/`FileNotFoundError` 抛出（exit 1 + traceback）；行为 fail-closed 正确，
   若接入 CI 建议改为稳定 enum/退出码（非本 PR 安全缺陷）。
2. 行 7a 括注“另 `20261120T200757Z-two-turn-bash` 为默认 Stage 复跑”与 late-bash 行并列略易混（措辞 only）。
3. `DEFAULT_STAGE_CANDIDATES` 中 `<repo>/artifacts/g3c/stage` 当前为失效自指 symlink（自动落到 rrev6 副本；不影响结果）。

### 11.7 裁定

| 项 | 结论 |
|---|---|
| A-PR2 条件修正（C1/C2/C3/C5） | **PASS（条件已满足）** |
| 是否允许集成 | **是**（仅 docs/scripts/tests；`src/`/`config/` 零 diff；无 runtime 行为变更） |
| A3-01 / A3-02 / B03 / E5-P04 / B | **UNVERIFIED / L1 PASS·L2 NOT_RUN / UNVERIFIED / UNVERIFIED / 条件式（依赖 A4 L2）** |
| C4（A4 L2 OS sandbox） | 仍 **NOT_RUN**，由矩阵/Packet v3 记录；不因本 PR 放行 |

> 本批 **未跑 OCI**（A4 独占窗口至 20:50Z 的约束保持）；未改变任何门状态；A2 等待 rebase 后 SHA 再复核（不审 `25b09ae` 旧树）。

---

## 附录 F：batch-3 命令与输出（§11）

```text
$ git -C worktrees/a-next-registry diff --name-status e09ac7c..748fd0a -> 3 M files (+135/−24)
$ git -C worktrees/a-next-registry diff fd1d3a6..HEAD -- src/ config/ -> empty
$ pytest tests/a_next_registry -q -> 8 passed, 1 skipped (0.02s)
$ G4R_RUN_RUNTIME=1 G4R_STAGE=worktrees/a-next-rrev6/artifacts/g3c/stage pytest tests/a_next_registry -q
  -> 9 passed in 17.33s
$ ruff check scripts/a_next tests/a_next_registry -> All checks passed!
$ run_matrix.py --mode baseline（不带 --stage）-> exit 0, stage verified=true, run 20261120T201850Z-baseline
$ run_matrix.py --mode baseline --stage /tmp/fake-stage-c1 -> exit 1 STAGE_SHA_MISMATCH (fail closed)
$ run_matrix.py --mode baseline --stage /tmp/does-not-exist -> exit 1 STAGE_MISSING (fail closed)
Owner reruns: 20261120T200752Z-baseline / 20261120T200757Z-two-turn-bash -> verified=true, exit_code=0
identity.txt: run_matrix sha 8067fcea… (== current), test sha 81f664b2… (== current)
```


---

## 12. 阶段 2 batch-3：A-PR0 v2 append-only 更正复核（`86edfd7`）— 2026-11-20T20:25Z–20:40Z

### 12.1 对象与分支提交链

| 项 | Reviewer 实测 |
|---|---|
| 分支/HEAD | `docs/a-next-baseline` @ **`86edfd7e4a18423906216547f533c88dd1d9efad`** |
| 提交链 | `e1fa0b9`（v1 三 docs）→ `94c81a1`（**修改** baseline/branch 两 v1 docs：protected-file 分组 + F-02 行号，13 行/文件）→ `fbea535`（新增 `A_NEXT_ENVIRONMENT_INCIDENT.md` 246 行）→ `86edfd7`（新增 2 个 v2 addendum，+182） |
| 新增 v2 文件 | `docs/A_NEXT_REVIEW_STATUS_RECONCILIATION_V2_ADDENDUM.md`（88 行）、`docs/A_NEXT_BASELINE_ADDENDUM_V2.md`（94 行） |
| 未改 | 冻结 CSV `741d7d55…`、Review `0599856a…`、`docs/g4r_review_evidence/**`：`git diff fd1d3a6..HEAD -- <冻结件>` = **空**；`src/`/`config/`/`scripts` 零改动 |

### 12.2 append-only 核验

- **对账 v1 字节未动**：`A_NEXT_REVIEW_STATUS_RECONCILIATION.md` sha256 **`81ecae3c…ce59b`**、
  git blob **`5729eb74…`**（与 addendum 声明一致）；`git diff e1fa0b9..HEAD -- 该文件` = **0 行**。✓
- **v2 只新增自身**（`86edfd7` 仅 A 两个文件）；A0-02 的 65 行 v1 表保留原值，v2 另表给出 old→new。✓
- **但发现披露不完整（P2-A0-1，见 §12.6）**：`94c81a1` 曾**就地修改** v1 `A_NEXT_BASELINE.md` 与
  `A_NEXT_BRANCH_RECONCILIATION.md`（各 13 行）；`A_NEXT_BASELINE_ADDENDUM_V2.md` 引用 baseline
  “v1, commit `e1fa0b9`; sha256 `597811ff…`”，但 **`597811ff…` 是 `94c81a1` 之后的当前字节**
  （`e1fa0b9` 时实测 sha 为 `5ebbe39c…`、blob `265a2663…`）。addendum 未记录这次 pre-v2 就地更正，
  “v1 字节不改”的表述在 baseline 上不严谨（对账 v1 本身确实未改）。

### 12.3 更正内容准确性（R4-05 / R4-12 / R4-13）

- `R4-05` SQLite backup provenance：v1 reviewer `PASS`（归因 R-REV5）→ v2 **`PARTIAL`**（reviewer final=`NO_DIRECT`，
  frozen PARTIAL 保留）。Reviewer 复核：与 §8.1 建议一致；`r_rev5_packet_verify.json` 顶层键实测确为
  `expected_impl_sha/issues/mutation_undetected/packet/status` **5 键**，无 provenance/path 字段 → **correct**。
- `R4-12` Evidence path correction：v1 `PASS` → v2 **`UNVERIFIED`**（reviewer final=`NO_DIRECT`，frozen PARTIAL
  仅为 Owner 记录）。Reviewer 复核：可取“更严格”的 UNVERIFIED（我的 §8.1 建议为 NO_DIRECT/PARTIAL；
  UNVERIFIED 属保守上界，未夸大）→ **acceptable**。
- `R4-13` LiveGate reason snapshot equality：维持 `PASS`（R-REV5 livegate 快照一致性支撑）→ **correct**。
- 更正后计数：v1 `25/18/10/2/4/6 = 65` → v2 **`23/19/10/3/4/6 = 65`**
  （−2 PASS、+1 PARTIAL、+1 UNVERIFIED，其余不变），推导与 Reviewer 独立解析一致；未出现“全 PASS”表述。✓

### 12.4 A0-04 / A0-03 / A5 终态复核

| 项 | v2 自报 | Reviewer 判定 | 依据 |
|---|---|---|---|
| **A0-04**（Packet/Review 冻结） | `PASS` → **`PARTIAL / LOST`** | **同意**：v1 Packet `LOST_IN_INCIDENT_20261121`（全盘/备份 tar 均无副本，Reviewer §9 已独立确认）；v2 Packet 恢复副本经 Reviewer 自建 verifier **PASS**（`issues=[]`/`mutation_undetected=[]`）；需注明“恢复 provenance、非原始 in-place 链” | 本报告 §9.3/§9.4 |
| **A0-03**（rootfs 防写/不可变） | 真实部署 **`NOT_RUN`**；工具层 PASS(条件) | **同意**：19:52Z 真实树 rootfs_guard=OK/sha 匹配（pre-incident），恢复后再次 OK（`25491e45…`，`mount.read_only=false`）；真实防写仍 HUMAN_REQUIRED；事件后 OCI/L2 必须标注恢复来源 | 本报告 §8.2/§9.4；`16a4187` 已复核 |
| **A5**（Packet/证据卫生） | **`PARTIAL`** | **同意**：v1 Packet LOST、`g4f` 0 files、`g4` 仅 `c/` 13,246 files、`g4r` 2,982 files（多副本合并，完整性不可证）——Reviewer 独立复核上述计数/状态一致；Packet v3 必须披露事件+恢复证据+backup tar sha | 本报告 §9.4；§12.5 |

### 12.5 环境事故记录（`A_NEXT_ENVIRONMENT_INCIDENT.md`）独立抽查

Reviewer 抽查（不是全文采信）：

```text
g4f files = 0；g4 = 13,246 files（仅 c/）；g4r = 2,982 files
顶层 symlink g3a-provider-bridge / g3c / g3d：均自指且 test -e=false（RESTORE_ANOMALY）
backup tar sha256=11172f02…159d42（916,480,000 bytes，mtime 19:56:30Z）——与 Reviewer §9 实测一致
v1 Packet：全盘找不到、backup tar 0 entries；rootfs=25491e45…、deps=e07729d7…（恢复后与冻结值一致）
```

事故文档自述状态 `PARTIAL_RECOVERY`、v1 `LOST_IN_INCIDENT_20261121`、backup tar 为**恢复后**快照而非事故前备份、
禁止“全程 NO_DRIFT/证据完整”表述——**与 Reviewer §9 结论一致，无淡化/夸大**。
（事故文档中 `L-02/L-03` 的 G4-F/G4-D/E5 丢失清单属 Owner 记录；Reviewer 仅抽查了可计数项，其余标注 `NOT_RUN` 不背书完整性。）

### 12.6 发现

- **P2-A0-1（披露/元数据不一致，必须在 Packet v3 前修正）**：v2 baseline addendum 把 `94c81a1` 更正后的
  baseline 字节标为“v1, commit e1fa0b9; sha 597811ff…”，与 `e1fa0b9` 实际 sha `5ebbe39c…` 不符；且未在
  append-only 版本记录中登记 `94c81a1` 的就地修改（2 文件各 13 行）。要求：追加 v3 澄清
  “e1fa0b9 原字节 sha=5ebbe39c…；94c81a1 就地更正 2 文件（列出 diff/sha）；v2 addendum 只追加不改这些字节”，
  并保持对账 v1 未被修改的事实。**不影响 v2 更正内容本身的正确性**。
- **P3-A0-2**：baseline addendum 对 v2 Packet 的描述“来自 worktree g4r-packet-final 副本”应与事件文档的恢复源
  清单（`/tmp/at-g4f-review/artifacts` + 各 worktree 副本）保持措辞一致；建议统一。
- 其余内容（v1 对账表字节未动、更正行与计数、batch-1 条件登记、A0-04/A5 降级、状态常量）**准确、无伪报 PASS**。

### 12.7 裁定

| 项 | 裁定 | 是否允许集成 |
|---|---|---|
| A-PR0 docs v2 更正（`86edfd7`） | **PASS（条件：P2-A0-1 披露修正）** | 可以（docs）；Packet v3 前必须追加 v3 澄清，且更正后不得自称“A-PR0 docs 已 PASS”超出本报告范围 |
| **A0-02 终态** | **PASS**（fp；65 行对账准确、v1 字节未动、2 行过度归因已更正；冻结 CSV 仍 741d7d55…） | — |
| **A0-04 终态** | **PARTIAL / LOST**（v1 LOST；v2 恢复副本可验证） | Packet v3 需披露恢复 provenance；不得称“冻结件全部可核验” |
| **A0-03 终态** | **NOT_RUN（真实部署防写）/ PASS(条件)（工具层 `16a4187`）** | 真实部署 HUMAN_REQUIRED；OCI/L2 证据须注明 rootfs/deps 恢复来源 |
| **A5 终态** | **PARTIAL** | Packet v3 必须含事件披露+恢复证据+backup tar sha；不得称“全部证据可核验” |

> 本批未跑 OCI（A4 窗口约束保持）；未改变任何门状态；A0-02 的 PASS 仅指“对账文档准确/append-only”，
> **不是** G4-R 矩阵整体 PASS，也不改变 R2 L2/R4-09/R4-10/R5/R-REV6 的 NOT_RUN/PARTIAL/UNVERIFIED。

---

## 附录 G：batch-3（A-PR0 v2）命令与输出（§12）

```text
$ git -C worktrees/a-next-baseline log --oneline -4 -> 86edfd7 / fbea535 / 94c81a1 / e1fa0b9
$ sha256sum docs/A_NEXT_REVIEW_STATUS_RECONCILIATION.md -> 81ecae3c…ce59b (git blob 5729eb74…);
  git diff e1fa0b9..HEAD -- 该文件 -> 0 行（v1 对账字节未动）
$ git show e1fa0b9:docs/A_NEXT_BASELINE.md | sha256sum -> 5ebbe39c…（addendum 引用的 597811ff… 实为 94c81a1 后字节）
$ git diff fd1d3a6..HEAD -- src/ config/ scripts/ -> empty；冻结 CSV 741d7d55… / Review 0599856a… 未变
$ v2 计数：23 PASS / 19 PARTIAL / 10 NOT_RUN / 3 UNVERIFIED / 4 NO_DIRECT / 6 N/A = 65
$ 事故抽查：g4f=0 files；g4=13246 files(c/ only)；g4r=2982 files；3 个 symlink 自指悬空；
  backup tar sha256=11172f02…；v1 Packet 不存在；rootfs=25491e45… / deps=e07729d7…
```


---

## 13. 阶段 2 batch-3：A-PR1/A2 实现独立复核（`c7eb74e`）— 2026-11-20T20:29Z–21:35Z

### 13.1 对象与范围

| 项 | Reviewer 实测 |
|---|---|
| 分支/HEAD | `feat/a-next-run-admission` @ **`c7eb74e1c2192d3b3732e780e019456d4a47aa3f`** |
| 提交链 | `e6f3aa6`(A1) → `d7bbf3b`(ADR) → `07eccb9`(impl) → `6556967`(errata) → `ff44ef6`(R-25) → `69c2932`(报告) → `c7eb74e`(R-07 真文件用例+合体核对)；`git merge-base --is-ancestor e6f3aa6 HEAD` = **true** |
| A1 文件 | `git diff e6f3aa6..HEAD -- src/.../authorization.py` = **0 行**（A2 未改 A1） |
| 新增/修改 | `src/.../bridge/run_admission.py`（1255 行新）、`controller.py` M（run_admission 接线 + required 模式）、`scripts/a_next/admission/{trusted_launcher,l2_admission_cases}.py`、`tests/integration/a_next_admission/**`、docs |
| 受保护文件 | `gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py`/`live_controller.py` 相对 fd1d3a6 **零 diff**；`config/` 零 diff |

### 13.2 Reviewer 独立运行（全部亲自执行）

```text
tests/integration/a_next_admission            -> 73 passed in 90.14s   (exit 0)
tests/integration/a_next_auth + tests/g4r_packet -> 50 passed, 1 skipped in 92.98s  (39+11; skip=packet v1 未在本树)
tests/integration/g4_a                        -> 223 passed in 145.23s (exit 0)
tests/integration/g4_f5 + g4_f2               -> 41 passed, 1 skipped in 14.84s (12+29+1)
tests/unit + tests/security                   -> 402 passed, 1 failed in 87.18s
pytest --collect-only -q                      -> 1532 tests collected (exit 0)
ruff check run_admission/controller/tests/a_next_admission/scripts  -> All checks passed
```

**唯一失败的安全测试独立分类（EXISTING / ENVIRONMENT，非 A1/A2 引入）**：
`tests/security/test_scan_git_secrets.py::test_repository_worktree_and_history_is_clean` 报 history finding：
`commit be92c3f70604` / `path fixtures/m1_teacher/judge/sentinels/sentinels.json:101` /
`kind env-key-assignment` / `masked SENTINEL_SECRET_TOKEN=SENTIN…`。Reviewer 在 **main@3e7afee**、
**基线 fd1d3a6 worktree**、A2 worktree **三处完全复现同一 finding**（A2 报告 `artifacts/a-next/run-admission/20261120T201321Z/baseline-fd1d3a6-secret-scan.json` 与我的复现一致）。
⇒ 这是 **B 线 m1_teacher fixtures 共享 git 历史的 pre-existing scanner finding**；与 A1/A2 改动无关、
非回归，不定级为 A2 FAIL；需在矩阵/handoff 记为 `EXISTING/ENVIRONMENT` 并由人类/B 线处置（本报告不修改历史）。

### 13.3 实现审阅（关键点）

- **Consume 恰一次 + C2 TOCTOU**：`_begin_run_admission_impl` 先 `load_execution_authorization(pre_start)` →
  复制前文件 sha → `consume_execution_authorization(pre_reserve)`（内部再次完整验证）→ post-consume 断言
  `use.authorization_id==authorization.authorization_id`、`use.run_epoch==identity.run_epoch`、
  use record 文件名==`sha256(id)+".json"`；不符/文件在 load↔consume↔consume 后变化 →
  `RUN_ADMISSION_AUTHORIZATION_DRIFT`，`consumed=UNKNOWN` fail-closed 不发送。测试 3 个（id/epoch/file-change）在 73 passed 内。
- **C3 required 模式**：`controller.main` 在 **任何 socket mkdir/Broker/Fake 之前**校验
  `run_admission_required`：required-but-missing→exit 6、inactive/foreign→exit 7；Reviewer 自建最小配置
  独立实测：**exit 6、socket/attempt_db 均未创建**；非 bool 配置→`CONFIG_INVALID` SystemExit。
  默认 `run_admission=None` 分支与冻结行为一致（`test_default_path_without_run_admission_is_unchanged` + F2/g4_a 全绿）。
- **C4 crash-after-consume**：同 Run 重启→`AUTHORIZATION_REPLAYED`→`RUN_ADMISSION_ALREADY_CONSUMED`；
  use record 不清理/不改写；报告 §7 有人工对账说明（无自动重发）。
- **C5 结构证明**：controller 全文仅 **1 处** `begin_dispatch(`、**1 处** `consume_dispatch(`，
  且位于唯一 `_broker_reserve()` 之前；`test_c5_one_token_per_payload_payload_count` 断言
  `_consumed_ordinals=={1}`；frozen Admission `max_attempts=1`（报告已声明未来若加重试须重评）。
- **C6 拒绝矩阵/零账本**：测试含 R-01..R-26 覆盖（伪造签名/未知 key/过期/撤销/漂移/预算/期限/日志满/
  durability unknown/token 复制/跨 Run/过期/ordinal 越界等）；`test_r19_token_denial_creates_zero_ledger_traces`
  断言 requests/reservations/attempts/fake=0；launcher subprocess deny 断言 Broker socket/attempt DB 未创建。
- **C7 no-key/no-Live**：受保护文件零 diff；静态测试确认新代码无 socket/requests/urllib/http/
  deepseek_harness/os.environ/API_KEY；LiveGate=BLOCKED、CLI `smoke --live`=exit 3、run_live 未改；默认路径回归全绿。
- **C8 L2 边界**：`A2-01..A2-03` 明确 **NOT_RUN**（报告 §6/§10）；`l2_admission_cases.py` 仅 host synthetic 验证，
  真实 OCI 属 A-PR3 窗口。
- **A1↔A2 R-07 真实文件用例**（4 个，73 passed 内）：真实 consume 后 body id 改为外来 id → `RUN_ADMISSION_RECORD_INVALID`
  （consumed=NO，非 REPLAYED/EPOCH_MISMATCH）、body id 与存储名不符→INVALID、非法 `consumed_utc`→INVALID、
  未篡改记录→`ALREADY_CONSUMED`（对照）；final 记录不被 A2 清理。
- **审计 allowlist**：无 Key/原始 prompt/messages/tool args/session 文本；call_id 仅 SHA-256；`attempt_db_touched=false`、
  `historical_holds_modified=false`（测试 `test_audit_records_are_allowlisted_and_content_free`）。

### 13.4 发现

- **P3-A2-1**：per-dispatch token 在 revocation/identity claim/Broker 之前消费；被拒绝的 payload 也会消耗
  ordinal（fail-closed 设计使然，但“effective_max_calls 计的是 dispatch 尝试而非成功发送”未在报告 §7 明说）。
  建议文档补一句 + 测试保留现状（安全上无升级面，属可用性/预算语义说明）。
- **P3-A2-2**：`_map_consume_reasons` 以拼接字符串子串匹配分类（DURABILITY_UNKNOWN→REPLAYED→EPOCH→INVALID→…）；
  当前 reason 集封闭、顺序正确，但未来 reason 增加时易脆；建议改为精确集合映射（非阻断）。
- **P2-A2-1（分类登记项）**：上述 pre-existing security history finding 必须在矩阵/handoff 显式记为
  `EXISTING/ENVIRONMENT（m1_teacher 历史 fixtures；基线/ main 可复现；非 A1/A2）`，不得写成 A2 回归或静默忽略；
  人类/B 线处置（扫描器规则或历史清理）另立工作项。

### 13.5 裁定

| 项 | 结论 |
|---|---|
| **A-PR1/A2 实现（c7eb74e）** | **PASS（条件）** |
| 是否允许集成 | **是**（A1 先冻结→A2 已 rebase；无 runtime/config 变更；默认路径逐字节不变） |
| 条件 | ① 矩阵/handoff 登记 pre-existing security finding 为 EXISTING/ENVIRONMENT；② A2-01..03 保持 **NOT_RUN**（A-PR3 窗口前不得写 L2 PASS）；③ G4-H1 前必须把 `run_admission_required` 升级为唯一生产启动路径（报告 §8 BLOCKER，人类 Gate）；④ 集成 HEAD 上由 Reviewer 复跑 a_next_admission/auth + F2/F5/g4_a 全套；⑤ P3 措辞/映射改进（可选） |
| 门状态 | `LiveGate=BLOCKED`、G4-H=NOT_AUTHORIZED、G5=BLOCKED、G6=NOT_RUN、M0=DECISION_PENDING 不变；`B03/E5-P04=UNVERIFIED`；P2-01 已由 A1 修复（待合入验收），P2-02 由本 PR 提供 opt-in 接线、**生产强制仍未完成** |

---

## 14. 阶段 2 batch-3：A4 R-REV6 L2 Owner 证据 host 级独立审核（`95a020b`）— 2026-11-20T20:29Z–21:40Z

### 14.1 对象

| 项 | Reviewer 实测 |
|---|---|
| 报告分支/HEAD | `test/a-next-rrev6` @ **`95a020b27ccf05ae3cd504d8c138bc279706fee2`**（parent `d083c54` run HEAD） |
| 证据根 | `worktrees/a-next-rrev6/artifacts/a_next/rrev6/l2/run-20261120T202039Z/`（13 个 case 目录 + R6-13 audit-only；14 case 状态） |
| 变更范围 | 仅新增 docs/scripts/tests（报告 + `scripts/a_next/rrev6/*` + `tests/a_next_rrev6/test_prep_contract.py`）；`src/`/`config/` 零 diff；**冻结矩阵 CSV/Review 未被修改**（`git diff fd1d3a6..HEAD -- …` 空） |
| 报告性质 | 明确写“这是 Owner 证据，不是 Reviewer 独立复跑；R-REV6 PASS 仍以独立 Reviewer 自行复跑为准”——**未冒充 Reviewer**（抽查确认） |

### 14.2 Reviewer host 级独立审计（自建脚本 `/tmp/a4_audit2.py`，全部只读）

```text
6 个顶层文件 sha256 全部匹配 Lead 给值（t0/t1/summary/audit/matrix/evidence-index）
T0=T1: rootfs=25491e45…、deps=e07729d7…（canonical=true；t0/t1 均记录恢复 provenance note）
containers_after=[]（t1/summary）；podman ps -a 现为空
Stage：manifest sha=34b3db73…；Reviewer 独立 tar 重算 stage tree=2b9edab8…、trusted=dbf3ca36…、
        candidate=b2c73100… 全匹配；base_sha=d083c54…；adapter builtJs=2cb42461…
summary/audit：14/14 PASS（R6-01..R6-13 + R6-04B），0 partial/not_run
evidence-index：114 个文件条目逐一 sha256/bytes 校验通过（`receipts` 键路径见 §14.4）
digest joins：prepared==claim.request_digest = 11 行；payload==receipt.raw_sha256 = 9 receipt；
              prepared!=payload 恒成立；0 mismatch
关键 case：R6-01/02/03 receipts=1/2/2；R6-05 0 dispatch/0 reserve/0 attempt/0 receipt；
          R6-09/10 reservation PENDING、0 attempt；R6-11 Broker=FAILED + attempt WORST_CASE_HELD + receipt=1
uid-map/peercred 存在；报告 limitation（R6-04 DSH replay、R6-09 SIGKILL pre-attempt、R6-11 terminal
FAILED）与证据一致
```

### 14.3 结论范围（重要）

- 本审计是 **host 级对 Owner L2 证据的独立核验**（文件哈希/T0-T1/Stage 身份/digest 绑定/终态分类），
  **不是** Reviewer 自己重跑 OCI L2。因此：
  - **A4/R-REV6 总裁定 = PARTIAL**：Owner L2 证据 host 级可信（PASS 级证据质量），但
    **Reviewer 独立 OCI 复跑 = NOT_RUN**；`A4-01..A4-03` 在矩阵中保持 **NOT_RUN**（按 Lead 规则，
    只按 Reviewer 独立复跑结果定状态）。
  - 建议 Lead 在集成后给一个 **最小独立 OCI 窗口**（≥3 case：R6-01 baseline、R6-04B 字节级 replay、
    R6-05 pre-Reserve 或 R6-11 fake-crash），Reviewer 用同一脚本按 SHA 独立复跑；通过后 R-REV6 才能升级。
  - 本报告**不**写 R-REV6 PASS、不改变任何门。

### 14.4 发现

- **P2-A4-1（证据索引路径 typo）**：`evidence-index.json` 用 `receipts` 键，实际目录为 `receipt/`
  （Reviewer 按映射校验 114 个文件 sha 全部通过；若按索引字面路径访问会 miss）。应修索引生成器或报告注明
  `receipts`→`receipt/` 映射，否则“逐文件 sha 见 evidence-index”无法按字面复核。
- **P3-A4-2（索引覆盖措辞）**：索引覆盖每 case 的 9 类核心证据（case-runner/db snapshot/receipts/
  dispatch-window/lifecycle/sqlite 等），**不覆盖** cleanup/env/peercred/mountinfo/logs/commands 等辅助文件；
  报告“逐文件 sha 见 evidence-index”应收窄为“核心证据文件”。
- **P3-A4-3（case 计数措辞）**：报告“13 case + R6-04B”与实际目录（12 个容器 case + R6-04B = 13 个 case 目录，
  R6-13 为 audit-only 无目录）+ summary 14 条状态存在口径混合；建议统一写明“14 个 case 状态（13 个容器 case 目录）”。
- 其余：限制说明诚实（R6-04 真实 DSH 层 replay 限制、R6-09 SIGKILL 落 pre-attempt、R6-11 Fake crash
  但 Broker FAILED 终态权威），approval/token 语义未见夸大。

### 14.5 裁定

| 项 | 结论 |
|---|---|
| A4 Owner L2 证据（host 级复核） | **PASS（证据质量/一致性）** |
| R-REV6（独立 L2） | **NOT_RUN（Reviewer 未重跑 OCI）⇒ A4/R-REV6 = PARTIAL** |
| A4-01..A4-03 矩阵 | 保持 **NOT_RUN**（直到 Reviewer 独立 OCI 复跑） |
| 是否允许集成 | 允许 docs/scripts/tests 集成（无 runtime 变更）；但不得以本证据宣称 R-REV6/L2 PASS |
| 条件 | ① 修 evidence-index `receipts` 路径/措辞；② Lead 批准最小独立 OCI 窗口后 Reviewer 复跑 ≥3 case；③ 任何 L2 证据继续标注 rootfs/deps 恢复 provenance；④ 矩阵 A4-01..03 不得提前升级 |

---

## 附录 H：batch-3（A2/A4）命令与输出

```text
A2: git -C a-next-run-admission rev-parse HEAD -> c7eb74e1…；merge-base --is-ancestor e6f3aa6 HEAD=true
    pytest tests/integration/a_next_admission -q -> 73 passed / 90.14s
    pytest tests/integration/a_next_auth tests/g4r_packet -q -> 50 passed, 1 skipped
    pytest tests/integration/g4_a -q -> 223 passed / 145.23s
    pytest tests/integration/g4_f5 tests/integration/g4_f2 -q -> 41 passed, 1 skipped
    pytest tests/unit tests/security -q -> 402 passed, 1 failed（history scanner EXISTING，见 §13.2）
    pytest --collect-only -q -> 1532 collected；ruff -> All checks passed
    Reviewer required-mode probe -> exit 6, socket/attempt_db not created；非 bool -> CONFIG_INVALID
    controller: begin_dispatch=1、consume_dispatch=1、_broker_reserve 在其后
A4: 6 顶层文件 sha 匹配；stage tree 独立 tar 重算匹配（2b9edab8/dbf3ca36/b2c73100）；
    digest joins prepared=11/payload=9、0 mismatch；R6-05/R6-09/R6-10/R6-11 终态如 §14.2；
    evidence-index 114 文件校验通过（receipts 路径 typo 见 §14.4）；podman ps -a 空；冻结 CSV 未改
```


---

## 15. 阶段 2 batch-4：A4 R-REV6 **Reviewer 独立 OCI L2 复跑**（2026-11-20T20:45–21:10Z 批准窗口）

### 15.1 窗口与准备（Reviewer 独立执行）

Lead 批准独占窗口 **2026-11-20T20:45:00Z–21:10:00Z**；Reviewer 未借用 Owner 结果，独立执行：

- **临时 Reviewer worktree**：`git -C main worktree add --detach /tmp/reviewer-l2 d083c54…`（Owner worktree 未改动；
  用后 `worktree remove --force` 清理）。
- 从 Owner 工作树复制**已哈希验证的冻结输入**到临时 worktree：rootfs=`25491e45…`、deps=`e07729d7…`
  （复制后重算 canonical 一致）。
- Stage 采用 Owner 构建的 **`stage-20261120T202016Z`**（Lead 允许；Reviewer 先以
  `validate_stage_g4(base_sha=d083c54, verify_git=True)` 复核：`ok=true`、manifest `34b3db73…`、
  tree `2b9edab8…`、trusted `dbf3ca36…`、candidate `b2c73100…`、adapter builtJs `2cb42461…`）。
- 每次 case 使用 **独立可写 rootfs 工作副本**（runner 复制后校验 canonical，case 后删除）；
  **从未** `podman --rootfs <frozen>`；网络 `--network none`/Fake-only/无 Key。

### 15.2 尝试 1（无效，未计入证据；暴露 runner fail-open）

运行起点 `20:44:43Z`（**比批准窗口早 17 秒**，Reviewer 调度误差；当时 podman 空、无其它 OCI 并发）。
所有 case `launch_case` 因 Reviewer 临时 worktree 缺少 runner fixture 目录
`artifacts/g4/c/runs` 失败（case-runner `failure=INTERNAL FileNotFoundError`）；
**但 runner 仍 `EXIT=0` 且 summary `ok:true`**（13 case PARTIAL、R6-13 PASS）——说明 Owner runner
**不按 case 成功/审计失败设置退出码（fail-open）**。该 run 目录保留为
`…/l2/run-20261120T204440Z`（attempt1），**不作为 A4 证据**。

### 15.3 尝试 2（Reviewer 正式独立 L2 证据）

补齐 runner fixture（从 Owner worktree 复制 `artifacts/g4/c` 与 `plugins/offline-fixture/node_modules`）后重跑：

| 项 | Reviewer 实测 |
|---|---|
| 运行窗口 | **20:46:56Z – 20:49:54Z**（批准窗口内） |
| run root | `/root/Autonomous Teacher/worktrees/a-next-review/artifacts/a_next/rrev6-reviewer/l2/run-20261120T204654Z-attempt2` |
| HEAD / Stage | `d083c54e…` / stage `stage-20261120T202016Z`（manifest/tree/trusted/candidate 同上） |
| T0/T1 | rootfs **25491e45…**、deps **e07729d7…**（canonical=true；T1==T0；`frozen_*_unchanged=true`） |
| containers | `containers_after=[]`；运行后 `podman ps -a` 亦空 |
| 结果 | **14/14 PASS**（R6-01..R6-13 + R6-04B；13 个容器 case 目录；R6-13 audit-only） |
| digest 绑定 | prepared==claim.request_digest **11 行**、payload==receipt.raw_sha256 **9 receipt**、0 mismatch、prepared!=payload 恒成立 |
| 关键终态 | R6-05 0 dispatch/0 reserve/0 attempt/0 receipt；R6-09/R6-10 PENDING + 0 attempt；R6-11 Broker **FAILED** + WORST_CASE_HELD；R6-12 PENDING（Broker restart 后守恒） |
| per-case checks | Reviewer 自建审计脚本：全部 case `checks_failed=[]`（Owner `evidence_audit` 复核亦 14/14 PASS） |
| uid-map/peercred | 各 case 均在（R6-01/10/12 抽查） |

**证据 SHA256（Reviewer 独立 run）**：

```text
t0.json       b79c3b141a7766bcfe3f5ccb6754ae42fba39ec92ecedeee5cbfd24ce60a9410
t1.json       b16f713bc3c796426d19b7325fc49f237779fbfc3695de9521fb30214672910d
summary.json  098cd26b70d0a522c21dbafa8a03a83137be60c0f816a98bd7a19f92d2ea8fcf
matrix.json   6ccf85aa0ad3093a105efa9630897c00f4c38f5d97a047915c1390c358361f25
audit.json    bff414ba392770ffe24c4c5f4a87478b649eda9fc3d49bbc9a79acf567109353
REVIEWER_EVIDENCE_MANIFEST.json 88def328d195db0e2e1e13af4123fb4040488d7c73af0fca2c2148c37c073bb4
             （覆盖 run root 下 1691 个文件；每个 case 目录逐文件 sha 见该 manifest）
```

**与 Owner run（`20261120T202039Z`）一致性**：14/14 case 状态**完全相同**；T0/T1 相同；containers 相同；
digest join 计数相同（11/15→11/9）；**未发现 Owner 证据与 Reviewer 复跑不一致**；R6-04/R6-09/R6-11 的
限制说明（DSH 层 replay、SIGKILL 落 pre-attempt、Fake crash→Broker FAILED 终态权威）在复跑中同样成立。

### 15.4 A4-01..A4-03 矩阵（Reviewer 独立 L2 结果）

| 矩阵行 | 要求 | Reviewer 独立证据 | 状态建议 |
|---|---|---|---|
| **A4-01** R-REV6 dual principal / Echo Tool Resume Replay + authentic digest joins | Reviewer independently reruns | R6-01/02/03/04/04B + R6-13 审计：14/14 PASS；digest joins 11/9、0 mismatch | **PASS（L2-REAL-DSH-FAKE，no-key）** |
| **A4-02** Candidate crash / Controller alive | Injection proves no duplicate dispatch + held unknown cost | R6-10（candidate SIGKILL at after_reserve：Broker PENDING、0 attempt、0 Fake、held>0、无 FREE/重复 dispatch）；R6-08/09 一并复跑 PASS | **PASS（保守限制：R6-09 SIGKILL 落 pre-attempt；R6-04 DSH 层 replay 限制）** |
| **A4-03** Broker crash/restart | Reserve/Claim/receipt/settlement conservation, no double charge | R6-12（broker SIGKILL→restart：PENDING held、0 settle、同 DB 恢复）+ R6-11（Fake crash→Broker FAILED 权威终态、不双结算）+ R6-06/07 held PENDING：全部 PASS | **PASS（L2-REAL-DSH-FAKE）** |

**限制（必须与结论同读）**：Fake-only、`--network none`、0 真实 Provider/Key、0 外部 HTTP；R6-04 的
真实 DSH 同 session replay 在 SDK 侧被拒（字节级 Controller replay 由 R6-04B 覆盖）；R6-09 的 SIGKILL
落在 test-only pre-attempt 窗口；R6-11 以 Broker `FAILED` 终态为权威。**不得**外推 E5-Full/G5/G4-H1/M0 GO。

### 15.5 发现

- **P2-A4-2（runner fail-open）**：case 全部 `INTERNAL` 失败时 runner 仍 `EXIT=0`/`ok:true`（仅检查 T0/T1/
  containers）。建议 Owner 修正：审计/矩阵出现非 PASS 时 runner 必须非零退出；本项不影响 attempt2 结果。
- **P2-A4-3（独立复跑前置未文档化/未 fail-fast）**：fresh worktree 除 staged rootfs/deps 外还需 runner
  fixture 目录（`artifacts/g4/c/runs` 等）与 `plugins/offline-fixture/node_modules`；否则首 case 即 INTERNAL。
  建议 runner 启动前检查并 fail-fast + 在报告复现步骤列出。
- **P3-A4-4（程序性偏差，已披露）**：attempt1 于 20:44:43Z 启动（比批准窗口早 17 秒，Reviewer 调度误差）；
  该 run 无效、未计证据；attempt2 在窗口内。运行期间 podman 空、无其它 OCI 并发。
- **P2-A4-1（沿用）**：Owner `evidence-index.json` `receipts` vs `receipt/` 路径 typo 仍待 a-g4r-recovery v2；
  Reviewer 证据用自建 manifest 规避。

### 15.6 裁定（更新 §14）

| 项 | 结论 |
|---|---|
| **A4 / R-REV6** | **PASS（Reviewer 独立 L2，L2-REAL-DSH-FAKE，no-key）** — §14 的 PARTIAL 由本节独立 OCI 复跑升级；§14 历史保留 |
| A4-01 / A4-02 / A4-03 | **PASS（限定上述 L2-REAL-DSH-FAKE 范围与限制；矩阵需记录 Reviewer 独立证据路径/SHA）** |
| 是否允许集成 | 是（Owner docs/scripts/tests 无 runtime 变更）；Owner 需按 P2-A4-1/2/3 修正/说明，不影响 Reviewer 证据 |
| 不得外推 | E5-Full / G5 / G4-H1 / M0 / 真实 Provider / Live 均**不**因此解锁；`LiveGate=BLOCKED` 等门不变 |

### 15.7 清理

Reviewer 临时 worktree `/tmp/reviewer-l2` 与 `/tmp` 工作副本已删除；podman 容器 0；Owner worktree 未被修改；
Reviewer 证据仅存于 `worktrees/a-next-review/artifacts/a_next/rrev6-reviewer/l2/`（gitignored），
本评审文档仅提交 docs。

---

## 附录 I：batch-4（Reviewer OCI）关键命令与 SHA

```text
git -C main worktree add --detach /tmp/reviewer-l2 d083c54…        # 临时 Reviewer worktree（用后 remove）
cp -a a-next-rrev6/artifacts/{security/rootfs,foundation/deps} …    # 重算 25491e45… / e07729d7…
validate_stage_g4(stage-20261120T202016Z, base_sha=d083c54, verify_git=True) -> ok
cd /tmp/reviewer-l2 && python scripts/a_next/rrev6/run_l2_matrix.py   --stage …/stage-20261120T202016Z --out <reviewer-evidence>/run-20261120T204654Z-attempt2   --work-root /tmp/reviewer-l2-work2 --expected-head d083c54…
  -> EXIT=0；utc 20:46:56–20:49:54Z；14/14 PASS；containers_after=[]；T0=T1=25491e45…/e07729d7…
reviewer audit: prepared=11/payload=9，0 mismatch；R6-05/09/10/11/12 终态如 §15.3
evidence manifest: 1691 files，sha256 88def328…
attempt1（无效）: 20:44:43Z 起，缺 artifacts/g4/c/runs → 13 case INTERNAL/PARTIAL，runner 仍 EXIT=0（P2-A4-2）
```


---

## 16. 终审 batch-4（前段）：集成树独立复核 `work/a-next@bbbcb37` — 2026-11-20T21:16Z–21:35Z

> 本节基于 Lead 给定冻结 SHA `bbbcb37c7468ed3f8c1d5f9ac83402fd68996c74`；**最终裁定以 Lead 后续给的新冻结 SHA
> 与新 Packet 为准**。旧 Packet v3（bbbcb37 候选）因可复现性缺陷已被 Lead 判定重建，标记
> `SUPERSEDED_BY_NEW_FREEZE`（见 §16.6），不作为最终 PASS 依据。

### 16.1 集成树身份与结构（Reviewer 实测）

| 项 | 结果 |
|---|---|
| 树/分支 | `/root/Autonomous Teacher/worktrees/a-next` @ **`bbbcb37`**（branch `work/a-next`，status clean）；代码 HEAD = `4d7c282`（bbbcb37 为其 docs-only child，仅 `A_NEXT_IMPLEMENTATION_REPORT.md` +2 行） |
| 变更规模 | `git diff fd1d3a6..bbbcb37` = **69 files / +17298 / −22**（与 Lead 声明一致） |
| 冻结件 | 冻结 CSV `741d7d55…`、`REVIEW_G4R_INDEPENDENT.md`、`M0_G4R_REVIEW_ERRATA.md`、`g4r_review_evidence/**`、`gates.py`、`run_live.sh`、`dsh_adapter.py`、`cli.py`、`live_controller.py`、`config/`：**零 diff** |
| 受保护文件 | 仅 3 个：`M src/autoteacher_m0/security/authorization.py`（A1 +69/−18）、`M src/autoteacher_m0/bridge/controller.py`（A2 +82/−4）、`A src/autoteacher_m0/bridge/run_admission.py`（A2 新入口）——与 Lead 声明一致 |
| 合并结构 | `git rev-list --count --merges fd1d3a6..HEAD` = **10**；覆盖 **8 个唯一分支 tip**（A1 e6f3aa6、A2 c7eb74e、baseline bf312c8、hygiene 7d7c0a5、handoff 13e39a4、registry 748fd0a、packet ce914c1、rrev6 95a020b；rrev6 另以 addendum 0735d7b 与 fc935bd 各合并一次）；10 个 merge 均为 **2-parent**、所有 tip `merge-base --is-ancestor HEAD` = true；工作区/索引 clean、0 冲突标记 |

> Lead 表述“无冲突合并 9 分支”与实测“10 merges / 8 unique branch tips（rrev6 三次合并）”在计数口径上略有差异，
> 实质一致（未发现未审 merge）；建议 Packet 文档按“8 分支 + rrev6 两次 addendum（共 10 merges）”精确表述（P3）。

### 16.2 A-PR0 v3 / A6 append-only / 矩阵状态（P2-A0-1 落实）

- **A-PR0 v3 `bf312c8` 已合入**（merge `6fcb87a`），`A_NEXT_BASELINE_ADDENDUM_V3.md` 存在且 **P2-A0-1 已落实**：
  Reviewer 独立复算 `git show e1fa0b9:docs/A_NEXT_BASELINE.md` sha **5ebbe39c…**、`94c81a1:` **597811ff…**
  （= 当前字节）、blob `265a2663…`/`3cc3d6b0…`；`A_NEXT_BASELINE_ADDENDUM_V2.md` sha **540f216b…** 未改；
  `A_NEXT_REVIEW_STATUS_RECONCILIATION.md` sha **81ecae3c…**（v1 字节未改）；v3 唯一载体 sha **a9607137…**；
  `94c81a1` 的就地修改（2 文件/+17/−9）已在 v3 §2 披露，v1/v2 冻结字节未改——**正确**。
- **A6 append-only 更新已合入**：`13e39a4..bbbcb37` 对 Handoff `+27` 行、Runbook `+33` 行，含 §9 集成身份/
  D-14/BLK 状态/incident/EXISTING finding、§10 Reviewer 终态（A4-01..03=PASS、A2 NOT_RUN、A1/A3/A5/A0 PARTIAL、
  A6 BLOCKED）、Runbook §16 INCIDENT/P2-ENV-1 防再发检查。**状态常量未改写**。
- **矩阵（A_NEXT_EVIDENCE_RECONCILIATION）**：冻结 65 行未预填（Reviewer 列 `TBD`）；A-NEXT 19 行 §5 初始
  `NOT_RUN`/`BLOCKED` 保留，**§10 append-only 追加终态**：A4-01/02/03=**PASS**（限 Reviewer 独立 L2）、
  R-REV6=PASS、A2-01..03=**NOT_RUN**、A1/A3/A5/A0=PARTIAL、A6=BLOCKED。Reviewer 确认 §10 与 §15 结论一致。
- **P3（文档一致性）**：`§5` 行级 `final_status` 仍 `NOT_RUN`/`TBD` 而 `§10` 已 PASS；`A5-02` 行仍写
  “OCI 待登记”；`IMPLEMENTATION_REPORT.md` 顶部摘要仍写 “OCI filtered=NOT_RUN/65 files” 而正文/§6 已有
  有效 OCI run 与 69 files（且合并表未列 #8.2）——均属 append-only 历史/摘要未回改；建议 Packet v3 后续
  addendum 明确“以 §10/§6 为准”，避免读者引用旧行（P3，不改变安全结论）。

### 16.3 Host 独立复跑（Reviewer 在最终集成树执行）

```text
cwd=/root/Autonomous Teacher/worktrees/a-next  HEAD=bbbcb37
PYTHONPATH=src pytest tests -q -p no:cacheprovider
-> 7 failed, 1619 passed, 18 skipped in 700.99s；总计 1644（= bbbcb37 collect-only 1644）
```

- 7 failures 与 Integrator JUnit（`host-full-junit.xml`：1626/1601/7/18，运行于 1dfb24c）逐 nodeid **完全相同**；
  差量 +18 = #8.2 新增 rrev6 runner fail-closed tests（1626→1644）——**Reviewer 在最终 HEAD 补跑了 Integrator
  报告“final HEAD host full NOT_RUN”的限制**。
- 逐项独立复现失败并分类：g3d stale-baseline（ENVIRONMENT_ONLY）、g4_b ×3 = 缺 gitignored
  `artifacts/g3d/stage-20261117T221955Z`（全局不存在 ⇒ **INCIDENT/ENVIRONMENT**）、g4_d PermissionError
  `/root/.../.venv/bin/python`（ENVIRONMENT_ONLY）、runtime target profile mode 0644（ENVIRONMENT_ONLY）、
  scanner history m1_teacher sentinel（**EXISTING/ENVIRONMENT**）。**6 ENV + 1 EXISTING、0 REAL_REGRESSION** —
  与 Integrator 分类一致，g4_b 因 G3-D Stage 丢失符合 INCIDENT 归因。
- 其他：A-NEXT 6 套件组合 **223 passed / 1 skipped**；G4 组合（g4_a/g4_f5/g4_f2/g4r_packet）**276 passed / 1 skipped**；
  两者均 exit 0。Ruff/Node/LiveGate/SQLite 结论引用 Integrator 证据（Reviewer 未重复 Node/LiveGate 容器执行）。

### 16.4 OCI（Integrator 窗口）独立核验

- JUnit `junit-oci-filtered.xml` 实测：**1287 tests / 97 failures / 54 errors / 31 skipped**（= 151 F/E）✓ 与
  `oci-meta-20261120T211004Z.json` counts 一致；deselect **44 条目 = 69 cases（43 legacy + 26 g4r_auth）**；
  exit 1；stage `stage-20261120T210101Z` base `c687738`、manifest `b3fd4cbc…`、trusted `5c9b3958…`；
  T0/T1 rootfs `25491e45…`、deps `e07729d7…`；run 于 **c687738**，其后 #8.2/bbbcb37 未跑 OCI ⇒
  **final HEAD OCI = NOT_RUN**（Integrator 已如实披露）。
- Reviewer 对 151 F/E 独立分桶：66 缺 host `git`/`tar`、63 uid/owner（`EXTERNAL_AUTHORIZATION_INVALID` 等）、
  21 env-assert 衍生、1 其它 no-such-file；**全部可归因环境**、无产品逻辑失败（docs 自称 64/61/26，分桶口径差异，
  结论一致）⇒ **A-NEXT 测试 OCI 可移植性 NOT_VERIFIED 的披露诚实**；未静默扩大 deselect。
- **P2-ENV-1**：Integrator 证据披露早期 Stage build 经 `artifacts/security` symlink 使 `--rootfs` resolve 到冻结
  rootfs（Lead 20:57Z 检测；frozen hash 未变）；Reviewer 实测当前 `artifacts/security` 为真实目录、rootfs
  重算 **25491e45…**，Runbook §16.4/meta invalidated attempts 均已记录——**披露诚实、纠正有效**；
  但“早期 frozen-symlink 尝试”本身属 P2 流程缺陷（已修复+披露）。

### 16.5 发现（前段，待新冻结复核后定稿）

- P0/P1：**无**。
- 待定 P2（Packet 重建后仍需满足）：①Packet 可复现性（见 §16.6，Lead 已确认缺陷）；②最终 Packet 内的
  文档一致性（§16.2 P3 类应通过 addendum/README 明确“以 §10/§6 为准”）；③A-NEXT OCI 可移植性 NOT_VERIFIED
  必须随 Packet 披露（不得被“OCI run 已执行”表述覆盖）。
- P3：merge 计数口径、IMPLEMENTATION_REPORT 顶部摘要/65 files/合并表 #8.2 未回填、A5-02 行 stale 文本、
  矩阵 §5 与 §10 并存需明示优先级。

### 16.6 旧 Packet v3（bbbcb37 候选）= `SUPERSEDED_BY_NEW_FREEZE`

- Reviewer 于 21:19Z 曾见到候选包 `artifacts/review-packet-a-next-v3-bbbcb37…`（manifest builder_sha `e4494382…`、
  content `a227abea…`、tree `db32da87…`、373 files/0 symlink），但该目录随后被重建移除；
  **未完成独立全树/逐文件/mutation 终审**。
- Lead 审计已确认**可复现性缺陷**：冻结 builder 的 `packet_name` 使用临时目录名，首包曾用未提交本地 3 行修复
  重建，`identity.builder_sha256` 与实际冻结源码不一致 ⇒ **Packet 不能从冻结 commit 复现**。
  Reviewer 记录为 **P2-A5-1（Packet reproducibility）**：旧包 `SUPERSEDED_BY_NEW_FREEZE`、**不得作为最终 PASS 依据**；
  新 Packet 终审将强制检查：
  1. `identity.builder_sha256` == 冻结 commit 中 `scripts/a_next/build_packet_v3.py` 的 sha256；
  2. `packet.name`/目录名 == 冻结 identity（非临时目录名）；
  3. 用冻结 commit 的 builder 从 staging 可复现（至少 builder 自校验/重建同身份）；
  4. manifest/hashes/README 的 builder/content/tree 自洽。
- 旧 Integration/Host/OCI 事实（§16.1–16.4）仍作为**新冻结前**的独立证据保留；最终裁定以新冻结 SHA + 新 Packet 为准。

> 本节不构成最终 PASS；门状态不变：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
> `M0=DECISION_PENDING`；`B03/E5-P04=UNVERIFIED`；人类决策仍 UNSIGNED。

---

## 附录 J：batch-4 前段命令/输出

```text
git -C worktrees/a-next rev-parse HEAD -> bbbcb37c7468ed3f8c1d5f9ac83402fd68996c74 (clean)
git diff fd1d3a6..HEAD -> 69 files, +17298/-22；frozen/protected 例外如 §16.1
git rev-list --count --merges fd1d3a6..HEAD -> 10；各 tip ancestor=true；merge parents 均 2
PYTHONPATH=src pytest tests -q -> 7 failed, 1619 passed, 18 skipped (700.99s, 1644 total)
7 failures reproduced individually: g3d stale / g4_b ×3 stage manifest missing / g4_d PermissionError /
  runtime profile mode / scanner history EXISTING -> 6 ENV + 1 EXISTING, 0 REAL_REGRESSION
A-NEXT suites: 223 passed, 1 skipped；G4 suites: 276 passed, 1 skipped
OCI junit: 1287/97/54/31；meta deselect 44 entries/69 cases；151 F/E all environment-attributable
P2-A0-1 hashes: e1fa0b9 5ebbe39c… / 94c81a1 597811ff… / v2 540f216b… / reconciliation-v1 81ecae3c… / v3 a9607137…
```
