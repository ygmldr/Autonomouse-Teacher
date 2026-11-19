# G4-H0 — 基线冻结与只读证据核对（A0）

- **文档 ID**：`G4H0-BASELINE-v1`
- **执行者**：`a-impl-core`（A 线实施者；非 Lead、非独立 Reviewer）
- **采集时间（UTC）**：`2026-11-19T17:36Z` → `2026-11-19T17:48Z`
- **工作树 / 分支**：`/root/Autonomous Teacher/worktrees/m0-g4h0-core` / `work/m0-g4h0-core`
- **冻结基线**：`3e7afee077845a071cd364e93ab209cac20b2d5f`（执行方案 §3 指定起点）
- **文档性质**：只读事实核对 + 本地无 Key 证据工程记录。**不是** G4-H0 的 PASS、不是独立复核结论、不是任何授权；不改变任何门状态（G4-H/G5/G6/LiveGate/M0/E5）。
- **本阶段硬约束遵守**：0 真实 Key 读取/生成；0 真实 Provider HTTP；0 付费出网；未修改任何 `src/` 代码；未修改冻结 docs/Packet/历史证据；未修改 `LiveGate`/无 Key 语义；未 `push`/`merge`/`checkout` 其它分支；未修改主工作树和其它 worktree；本线写入面仅 `docs/g4h0/`（另在自身 worktree 的 gitignored `artifacts/g4h0/` 生成 v2 Packet，未提交）。

---

## 0. 摘要

1. 实际 `HEAD` 与冻结基线 `3e7afee…` 一致；主工作树与 core 工作树均为 clean（`git status --porcelain -uall` 0 行）。
2. 50 个 `src/**.py` 文件的工作树字节 = HEAD 提交字节，已逐个记录 sha256；`src` 树对象 `66edfac3…`，HEAD 树对象 `feccda00…`。本线对 `src/` 写入为 0。
3. `docs/` 冻结 Packet 的 11 个关键文件 sha256 已记录并与 `docs/M0_G4F_REVIEW_ERRATA.md` 中已登记的哈希（Reviewer 报告 `b17977d1…`、归档矩阵 `0f4e25ae…`）一致；本线未改写任何冻结字节。
4. 旧 G4-F Review Packet **未被改写**：177 files / 0 symlink、`sha256sum -c hashes.sha256` **173/173 OK**（构建前后两次复算一致，mtime 未变）；P2-01 的 2 个 post-build SQLite sidecar 与 payload tree 漂移按实测复算复现（全量 `111c1361…`，剔除 sidecar 后 `e464b9b1…` = manifest 值）。
5. **P2-01 证据工程（离线完成）**：用仓库现有 `scripts/g4/build_packet_g4f.py` 在自身 worktree 的 gitignored `artifacts/g4h0/packet-v2` 重建了干净 v2 Packet：**175 files / 0 symlink / 173 hashed OK / payload 172 / payload tree 自校验一致 / 0 sidecar**，完整文件哈希清单见 `docs/g4h0/evidence/P2-01_v2.sha256`。v1 保持不可变，未删除、未改写、未重打包。
6. 6 个状态常量全部维持冻结值（见 §5）；`LiveGate` 既有代码证据（`gates.py:70/82`、`live_controller.py:66-72`、`run_live.sh:5`）与本地负例（`run_live.sh` exit 3）一致。
7. 本阶段 0 真实 Key：Key 名扫描 0 命中、已知 Key 变量全部 UNSET、无 `.env`；`podman ps -a` 为空；未执行任何 Provider 调用。
8. **未做/未验证**：独立 Reviewer 复核、完整 A-07 负例矩阵复跑、`rootfs/deps` 全量 canonical 复算、真实 Provider/TLS/账单。以上按 §8 分类为 HUMAN_REQUIRED / PARTIAL / NOT_RUN，不写成 PASS。

---

## 1. 冻结身份与 Git 状态

### 1.1 冻结 SHA 与工作树

| 项 | 冻结/期望 | 实测 | 分类 | 证据 |
|---|---|---|---|---|
| 仓库冻结基线 | `3e7afee077845a071cd364e93ab209cac20b2d5f` | 同值 | **VERIFIED** | `BASELINE_COMMANDS_20261119T174015Z.log` §1 |
| core 工作树 HEAD | 同基线 | `3e7afee…` | **VERIFIED** | 同上 |
| core 分支 | `work/m0-g4h0-core` | 同值 | **VERIFIED** | 同上 |
| 主工作树 `/root/Autonomous Teacher` HEAD | `3e7afee…` | 同值 | **VERIFIED** | 同上 |
| 主工作树状态 | clean | `git status --porcelain -uall` → 0 行 | **VERIFIED** | 同上；构建 v2 前后均复核 |
| core 工作树状态（写入文档前） | clean | 0 行 | **VERIFIED** | 同上 |
| `HEAD^{tree}` | — | `feccda00a78f10a8ee89b49b130838e464d98c46` | **VERIFIED** | 同上 |
| `HEAD:src` | — | `66edfac399c0af8e15f28f6064cb85be8e1dd11d` | **VERIFIED** | 同上 |
| `HEAD:docs` | — | `689b266809072e615c73fd3928c8e8813063ec20` | **VERIFIED** | `BASELINE_HASHES_20261119T174453Z.txt` |
| `HEAD:scripts/g4` | — | `32082390e4778048486db7b5f7acdee9695e9ba4` | **VERIFIED** | 同上 |
| `merge-base(HEAD, 冻结基线)` | 冻结基线本身 | `3e7afee…` | **VERIFIED** | 同上 |
| 远端 | `origin git@github.com:ygmldr/Autonomouse-Teacher.git` | 已配置；本轮 0 fetch / 0 push | **VERIFIED**（观察） | 本线未联网 |
| 工作树列表 | — | 11 条（见 §7） | **VERIFIED**（观察） | `git worktree list` |

### 1.2 与 G4-F 历史冻结身份的关系（避免混淆）

| 对象 | 冻结值 | 实测/说明 | 分类 |
|---|---|---|---|
| G4-F implementation `impl_sha` | `e7d92967ec0ece80de4a1a3705f637e8eb9bde99` | 是当前 HEAD 的**祖先**；`git diff e7d9296..HEAD -- src` 为空（src 自 impl 后未变） | **VERIFIED** |
| G4-F v1 Packet `docs_sha` | `d12df4165108d59a2a4f08ba3ba93a35935df846` | 当前 HEAD `3e7afee` 是 **post-packet docs 归档提交**（Reviewer 报告/ERRATA/矩阵 `REV-01..05` 最终化），因此不是 v1 Packet 的 `docs_sha` | **VERIFIED** |
| G4-F v1 Packet `build_sha` / head | `0d5e5e09cd607aef6ba39608b8a3b33a0d2c7705` | 当前 HEAD 的父提交链上可观察到；v1 Packet 未重打包 | **VERIFIED** |
| 当前 HEAD 相对 impl 的差异面 | 仅 `docs/` + `scripts/g4/build_packet_g4f.py` | `git diff --name-only e7d9296..HEAD` 实测：8 个文件，7 个 docs + 1 个 packet builder；**无 `src/`** | **VERIFIED** |

> 结论：**“冻结基线 3e7afee”是仓库 HEAD/文档归档状态；G4-F 代码与实现身份仍是 `e7d9296`，二者不矛盾。** 任何把 `3e7afee` 写成 v1 Packet `docs_sha` 的说法都是错误的。

### 1.3 源码树 sha256 清单（关键受信文件 + 全量清单）

50 个 `src/**.py` 文件全部已记录；完整逐文件 sha256 见**附录 A**（并落盘于 `docs/g4h0/evidence/BASELINE_HASHES_20261119T174453Z.txt`）。下表为安全/运行时关键文件：

| 文件 | 工作树 sha256（= HEAD 字节） | Git blob（SHA-1） |
|---|---|---|
| `src/autoteacher_m0/security/gates.py` | `3ed0863440d26105f30f84579f07105c298ed586cbd8e4616c15fad495afb23a` | `edf7f45fdbd058f89177a8e8f8d918274516b9d4` |
| `src/autoteacher_m0/runtime/dsh_adapter.py` | `888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a` | `86ae5d6e6f8bf50f68972e28744530af4f109dcf` |
| `src/autoteacher_m0/cli.py` | `31555386ec3cbeb6ed4584a861b1da3313fa1e00b026cd8f43cd05227ba2c940` | `b68822fdd376ab816e0179e0482dd1a4266de8d1` |
| `src/autoteacher_m0/security/authorization.py` | `5696b2c812c21194b82e56a17344c81c631e56becec660b47abcc851a8a7b5b2` | `6899b740964c570d02ec75a5e812d4a5290eb159` |
| `src/autoteacher_m0/security/live_controller.py` | `d50a55a18b45044f0cc65b266491a42469d8b452f63bbe348a47e1df8e0bdba0` | `0551dade978ded32500b53caa097ca98153d74f8` |
| `src/autoteacher_m0/security/egress.py` | `cb4961db034c9d5ad62192841c1beb8d965a8392fa3f3226181135ec7073602e` | `4d0c82025872a9aa7109762e900eb751f8479ee5` |
| `src/autoteacher_m0/security/watchdog.py` | `42e1d061ed1e54264d120e4ae7dbffc0b7534abdcac4d9280a636bef58edb965` | `96dfc56772bf33b8b1ab71d589472db23137b1fd` |
| `scripts/run_live.sh` | `a8a2753fd6b6b096b66adecfbdde044b42c6c4a26630c24f0fc269b1fe5f957a` | — |
| `AGENTS.md` | `1d97a7e369a3831267516a968070ee5bca0950350c350e2ebbd9eed91cf30133` | — |
| `SECURITY.md` | `3a6cc50f6fea35c5f30a9e7481e11ad577f0e8c40ce31955257a9ebdb5485618` | — |

上表 4 个受保护文件（`gates.py`/`dsh_adapter.py`/`cli.py`/`run_live.sh`）的 sha256 与 `docs/REVIEW_G4F_INDEPENDENT.md` §2.1 记录的字节身份一致（`3ed08634…`/`88891149…`/`31555386…`/`a8a2753f…`）——**交叉验证一致，未漂移**。

### 1.4 本线写入面

- 阶段一写入仅：`docs/g4h0/BASELINE.md`、`docs/g4h0/RISK_DISPOSITION.md`、`docs/g4h0/evidence/*`。
- `artifacts/g4h0/packet-v2` 在自身 worktree 的 gitignored `artifacts/` 内，**不进入 git 提交**。
- 构建 v2 时曾临时创建 2 个**只读 symlink 输入**（`artifacts/g4f` → 主工作树 `artifacts/g4f`；`artifacts/g4/c/stages/stage-20261119T142828Z` → 主工作树同名 stage），构建完成后**已删除**；主工作树的 Packet/Stage 未被写入（见 §3.3 复核）。

---

## 2. docs 冻结 Packet 与只读约束

### 2.1 冻结 docs 清单（工作树字节 = HEAD 字节）

| 文件 | sha256 | 说明 | 分类 |
|---|---|---|---|
| `docs/REVIEW_G4F_INDEPENDENT.md` | `b17977d1ff8506de440996f7bd411149ae968cef6564391b74b28980468ddc4b` | 34433 B；与 ERRATA §1.3 登记值一致 | **VERIFIED** |
| `docs/M0_G4F_REVIEW_ERRATA.md` | `7b8209db9c15897e6b4d271361703e4425a9a3a361cb3818d53e5fd92eb9b42b` | append-only 归档勘误；28536 B | **VERIFIED** |
| `docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv` | `0f4e25ae76632ff60e0c644d34a19bf6c602cf49e347112a1fb3be87a091dba3` | 与 ERRATA §6.1 归档后哈希一致；46 行 43/2/0/1 | **VERIFIED** |
| `docs/M0_G4F_HUMAN_HANDOFF.md` | `cd26d1e158258ebf457636ba9fd19f6e500271d3232a551fd4197155a49624b0` | 人类待决项 | **VERIFIED** |
| `docs/M0_G4_HUMAN_HANDOFF.md` | `f7a2101bcc2ed5073ac7bda452703d98df5534574a534e565bb6b77c0132b16f` | 人类待决项（G4） | **VERIFIED** |
| `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md` | `bdeefd378b8feb4af153d6e791b26afe231cdb5e4df01ff1817c7b6bca0caa80` | 无 Key 安全设计 | **VERIFIED** |
| `docs/SECURITY_APPROVALS.md` | `a42719784394534cb566622e7f3859419b308ab93a56b969f2f0e66af9522ee3` | 审批模板（BLOCKED/未签署） | **VERIFIED** |
| `docs/M0_G4F_F1_REPORT.md` | `f6408d57bb80f7c740d83405e3d6218a0de1450e386055df6e01773c5aa2b049` | F1 scanner 报告 | **VERIFIED** |
| `docs/M0_G4F_IMPLEMENTATION_REPORT.md` | `7af6518ec7372fb4db991aa9e49ce8fb2021300e1c5a438ee2552b83fc11cd4f` | F1–F6 实现报告 | **VERIFIED** |
| `docs/M0_G4F_REVIEW_REQUEST.md` | `a3d7c099ee1d3f116886d92d8aff19b943bb16f972db47356e4b3e9fe21e8018` | Review Request（R0–R8） | **VERIFIED** |
| `docs/M0_G4F_FINDINGS_AND_DISPOSITION.md` | `bd062fe5e605e78a6dcca7ae3d17e18eb533b6f1d246bdafec3b1606b15a5be4` | 残余/UNVERIFIED 登记 | **VERIFIED** |

> 前 3 项是 v1 Packet 冻结/归档链上已有哈希承诺的文件，实测**全部一致**；其余 8 项为 G4-F closeout 文档，本轮首次记录工作树字节哈希（HEAD blob 身份另见 `BASELINE_HASHES_…txt`）。**不修改**是硬约束：本线未写入上述任何文件。

### 2.2 只读约束与 append-only 规则（本线遵守情况）

1. **冻结 Packet 只读**：v1 Review Packet 与旧 G3/G4 证据只做读取；校验前后文件数（177）、hash 结果（173/173）与 sidecar mtime（`15:09:08Z` / `15:11:07Z`）均未变化（见 §3.1）。
2. **append-only**：`docs/M0_G4F_REVIEW_ERRATA.md` 只追加、不改写既有字节；本线未修改该文件。
3. **v1 Packet 不重打包**：按 ERRATA §7，Reviewer 报告/ERRATA/矩阵 `REV-01..05` 是 post-packet 产物；本线 v2 为**新目录**，v1 保持不可变。
4. **证据不 shared**：未与其它 worktree/agent 共享 `artifacts/`、rootfs/deps、Session、Broker DB、Socket、Policy、Authorization 或任何凭据。

---

## 3. Review Packet v1 完整性与 P2-01（v2 证据工程）

### 3.1 v1 Packet 是否被改写：**未改写（VERIFIED）**

- 路径（主工作树，gitignored，只读访问）：`/root/Autonomous Teacher/artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99/`
- 实测（`P2-01_packet_v1_verify_20261119T174453Z.log`）：

| 项 | 值 | 分类 |
|---|---|---|
| 普通文件数 / symlink | 177 / 0 | **VERIFIED** |
| `sha256sum -c hashes.sha256` | **173/173 OK，exit 0**（17:41Z、17:42Z 两次一致） | **VERIFIED** |
| manifest `files.count` / `payload_tree_sha256` | 172 / `e464b9b1d6ab0bf4406ccc7868863d207f594fa898ee4affaa3e901d9f1caaa0` | **VERIFIED** |
| 全量 payload（含 2 sidecar）复算 tree（174 files） | `111c1361417ea6ee6958ecffebdb78164f655b082ae8cf911dca221f57794b5a` → **≠ manifest** | **VERIFIED（漂移复现）** |
| 剔除 2 sidecar 后复算 tree（172 files） | `e464b9b1d6ab0bf4406ccc7868863d207f594fa898ee4affaa3e901d9f1caaa0` → **= manifest** | **VERIFIED** |
| sidecar 1：`f4/sqlite-readonly/resume-attempts.sqlite3-shm` | 32768 B；sha256 `fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`；非零字节数 40；mtime `2026-11-19 15:11:07Z` | **VERIFIED**（字节统计） |
| sidecar 2：`f4/sqlite-readonly/resume-attempts.sqlite3-wal` | 0 B；sha256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`；mtime `2026-11-19 15:11:07Z` | **VERIFIED** |
| Packet 创建时间（integrity report） | `2026-11-19T15:09:08Z`；sidecar mtime 晚 ~2 分钟 | **VERIFIED** |
| sidecar 内容语义“无业务数据” | 本线**未在 v1 上打开 SQLite**（避免再产生 sidecar）；行级判断沿用 ERRATA §4.1 的历史独立复核结论（WAL 为空、SHM 仅空 frame header） | **PARTIAL（本线仅字节级）** |

**结论**：v1 Packet 的已哈希文件全部逐字节未变，sidecar 漂移是构建后只读 SQLite 副本产生的副作用，**不是内容/密钥/账本篡改**；但“177/173 的未哈希 payload 只有元数据”不成立——v1 的全量 payload tree 自校验确实漂移。此结论与 `REVIEW_G4F_INDEPENDENT.md` §2.2/P2-01、ERRATA §4.1 一致，并由本线独立复算复现。

### 3.2 sidecar 排除规则（规范性定义，供 v2/packet builder 复用）

1. **完整性口径**：冻结 packet 的 payload tree 必须覆盖除 3 个设计排除项外的**所有普通文件**——`hashes.sha256`（自哈希排除）、`packet-integrity-report.txt`（设计排除）、`manifest.json`（单独在 `hashes.sha256` 中按文件哈希覆盖，不计入 `files.count`）。
2. **SQLite 只读副本**：只能字节复制，**不得在原位打开**；任何解析/校验（如 `sqlite3` 只读游标）必须针对 `/tmp` 临时副本执行，且临时副本不得写回 packet。
3. **sidecar 处理**：若因任何读取仍产生 `*-wal`/`*-shm`，冻结前必须：(a) 确认无进程持有；(b) 记录其大小/sha256/mtime；(c) 删除 sidecar 后**重新生成** `hashes.sha256` 与 payload tree（`manifest.files.count`/`payload_tree_sha256` 同步更新）；或 (d) 在 builder 中显式排除并以独立清单记录被排除文件元数据。**不得在旧 Packet 上原地修补**。
4. **版本规则**：修复只产生新版本（v2/v3…）；v1 保持不可变，任何 v1 引用必须同时披露 P2-01。

### 3.3 Packet v2 离线重建（本地完成）

- **构建命令**（cwd = core 工作树；`ROOT` 由脚本自身定位）：
  ```text
  PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B \
    scripts/g4/build_packet_g4f.py \
    --docs-sha 3e7afee077845a071cd364e93ab209cac20b2d5f \
    --out "/root/Autonomous Teacher/worktrees/m0-g4h0-core/artifacts/g4h0/packet-v2" \
    --force
  ```
- **输入**：`artifacts/g4f/f6/integration/**`、`artifacts/g4/c/stages/stage-20261119T142828Z` 来自主工作树的只读证据（构建时以只读 symlink 提供，构建后删除）；`docs/`、`src/`、`scripts/` 取自本 worktree（HEAD 字节）。
- **结果**（`P2-01_packet_v2_verify_20261119T174135Z.log`；构建输出 `P2-01_packet_v2_build_20261119T174016Z.log`）：

| 项 | 值 | 分类 |
|---|---|---|
| 文件数 / symlink / sidecar 数 | 175 / 0 / **0** | **VERIFIED** |
| `sha256sum -c hashes.sha256` | **173/173 OK** | **VERIFIED** |
| `P2-01_v2.sha256`（全 175 文件清单）复核 | **175/175 OK** | **VERIFIED** |
| payload 文件数 / tree（复算 vs manifest） | 172 / `ffae8b3bb48cd3c1f78fa2aa49dd8a616ec8a3b76cbb5aed782b1f4d572bac8c` = manifest 值 | **VERIFIED** |
| integrity report | `PASS`；`sensitive pattern hits: 0`、`host home paths: 0`、`sha256 mismatches: 0` | **VERIFIED** |
| manifest / hashes / report sha256 | `40d7f006…6285f` / `6e37b56b…7a5e3` / `53048eba…420077` | **VERIFIED** |
| 身份字段 | `impl_sha=e7d9296`；`docs_sha=build_sha=head_at_packet=3e7afee`；`worktree_clean=true` | **VERIFIED** |
| 无 Key/无 Live 字段 | `live_gate=BLOCKED`、`real_model_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`、`key_present=false`；`live_gate_reasons` 4 项 | **VERIFIED** |
| 矩阵副本 | 归档后矩阵（46 行：43 PASS / 2 UNVERIFIED / 1 BLOCKED），`case_statuses` 同步 43/2/0/1（v1 为 38/2/5/1，差异来自 docs 归档推进，**不是新证据**） | **VERIFIED** |
| 主工作树 v1 未被写 | 构建后 v1 仍 177 files、173/173 OK、sidecar mtime 未变；主工作树 `git status` 0 行 | **VERIFIED** |

**v2 的已知限制（必须披露，不得外推）**：

1. v2 是**目录完整性修复重建**，不是新一轮独立复核，也不产生新的通过证据；`contract.reviewer=NOT_ASSIGNED`、`reviewer_status=PENDING_INDEPENDENT_REVIEW` 保留 builder 冻结字段，v2 未修正。
2. **P2-02 未修**：v2 的矩阵副本仍是冻结矩阵字节，`F2-07` 错误路径保留（46 行中 F2-07 行）。
3. **P2-07 未修**：v2 `env/zero-key.json` 的 `live_gate_reasons` 仍只有 1 项（实测），manifest 与 `review/livegate.json` 为 4 项；v2 不解决该一致性问题。
4. v2 位于自身 worktree 的 gitignored `artifacts/`，**未 commit / 未 push / 未交给独立 Reviewer**；本线只把可复核哈希清单提交（`docs/g4h0/evidence/P2-01_v2.sha256`）。
5. v2 payload tree 与 v1 不同是**预期**（`docs_sha`/manifest 时间/矩阵状态变化），不能用于否定 v1 的冻结。

**复现/复核 recipe**（无需网络、无需 Key）：

```text
# 0) 进入 core 工作树；确认 clean
cd "/root/Autonomous Teacher/worktrees/m0-g4h0-core"
git status --porcelain -uall            # 期望 0 行
# 1) 只读输入（构建后删除）：
mkdir -p artifacts/g4/c/stages artifacts/g4h0
ln -sfn "/root/Autonomous Teacher/artifacts/g4f" artifacts/g4f
ln -sfn "/root/Autonomous Teacher/artifacts/g4/c/stages/stage-20261119T142828Z" \
        "artifacts/g4/c/stages/stage-20261119T142828Z"
# 2) 构建 v2
PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B scripts/g4/build_packet_g4f.py \
  --docs-sha 3e7afee077845a071cd364e93ab209cac20b2d5f \
  --out "$PWD/artifacts/g4h0/packet-v2" --force
# 3) 校验（payload tree 自校验 + hashes + 全文件清单）
cd artifacts/g4h0/packet-v2 && sha256sum -c hashes.sha256   # 期望 173/173 OK
cd artifacts/g4h0/packet-v2 && sha256sum -c \
  "/root/Autonomous Teacher/worktrees/m0-g4h0-core/docs/g4h0/evidence/P2-01_v2.sha256"  # 期望 175/175 OK
# 4) 清理只读 symlink
rm artifacts/g4f "artifacts/g4/c/stages/stage-20261119T142828Z"
```

> 复跑注意：`--docs-sha` 必须仍是“最后一个 docs 提交”且 `impl` 是其祖先、worktree clean，否则 builder 会 fail-closed（这是设计行为）。复跑得到的 v2 manifest 因 `created_utc` 不同会有不同 sha256，但 payload tree 与 hashes 清单应对同一输入保持稳定。

### 3.4 分类结论

- v1 未改写：**VERIFIED**。
- sidecar 漂移复现与“非业务数据”判断：**PARTIAL**（本线字节级 + 历史 ERRATA 语义结论）。
- v2 本地完整性：**VERIFIED**（本地、离线、自校验）。
- v2 独立复现/签收：**PARTIAL / HUMAN_REQUIRED**（未由第二方重跑，未签收；不构成 PASS）。

---

## 4. 工具版本（实际存在项）

| 工具 | 实测版本 / 路径 | 分类 | 备注 |
|---|---|---|---|
| Python（host 系统） | `3.12.3`（`/usr/bin/python3`） | **VERIFIED** | 非 G4-F 证据用解释器 |
| Python（host 固定） | `3.11.15`（`/root/.local/bin/python3.11`） | **VERIFIED** | 与 G4-F Reviewer 记录的 host Python 一致；v2 builder 使用 |
| uv | `0.11.6`（`/root/.local/bin/uv`） | **VERIFIED** | |
| podman | `4.9.3` | **VERIFIED** | `podman ps -a` 为空 |
| Node | `v22.23.2`（`/usr/bin/node`） | **VERIFIED** | 与 G4-F Reviewer 记录一致 |
| git | `2.43.0` | **VERIFIED** | 未 fetch/push |
| jq | `1.7` | **VERIFIED** | |
| sha256sum | `/usr/bin/sha256sum` | **VERIFIED** | |
| `dsh`（host CLI） | `0.2.1-rc.2`（`/usr/bin/dsh`） | **PARTIAL（观察）** | **与冻结 G4-F 运行时 `0.2.2-rc.2`（`stage-summary.dsh_sdk_version=0.2.2rc2`，runtime sha `1cc41d5a…`）不是同一二进制**；G4-F 身份以 stage 工件为准。本阶段未用 host `dsh` CLI 产生任何 M0 证据 |
| ruff | `0.17.5`（仅经 `uv run`/项目环境可见；直接 `ruff` 不在 PATH） | **PARTIAL** | 版本与 G4-F Reviewer 一致；本阶段未运行 |
| pytest | 直接 `pytest`/`python3.11 -m pytest` 均不可用；项目测试经 `uv` 环境 | **NOT_RUN** | 本阶段无 `src/` 变更，未运行测试 |
| `bug` CLI | **不存在** | **VERIFIED（不存在）** | 执行方案提到的 `bug` 工具在本机不可用 |
| sqlite3 CLI | 不存在；Python `sqlite3` 模块 `3.50.4`（python3.11） | **VERIFIED** | 本阶段未打开任何 packet 内 SQLite |

---

## 5. 状态常量证据（代码/文档引用行号）

| 常量 | 冻结值 | 证据（文件:行） | 分类 |
|---|---|---|---|
| `G4-H` | `NOT_AUTHORIZED` | `docs/REVIEW_G4F_INDEPENDENT.md:35`（§1）、`:372`；`docs/M0_G4F_REVIEW_ERRATA.md:92`、`:247`；`docs/M0_G4F_HUMAN_HANDOFF.md:6`；`docs/M0_G4_HUMAN_HANDOFF.md:4` | **VERIFIED**（文档级；治理状态，无代码开关） |
| `G5` | `BLOCKED` | 同上；`http` 无批准入口；v1 Packet `manifest.contract.state_constants.G5=BLOCKED` | **VERIFIED**（文档/工件级） |
| `G6` | `NOT_RUN` | 同上 | **VERIFIED**（文档级） |
| `LiveGate` | `BLOCKED` | **代码**：`src/autoteacher_m0/security/gates.py:66-82`（`inspect()` 恒返回 `GateDecision("BLOCKED", …)`；`:70` 首条 reason `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`；`:84-86` `require_live()` 抛 `SecurityBlocked`）；`src/autoteacher_m0/security/live_controller.py:66-72`（`ALWAYS_BLOCKED_REASONS` 含 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`/`EXTERNAL_CREDENTIAL_BROKER_NOT_DEPLOYED`/`EXTERNAL_EGRESS_PROXY_NOT_DEPLOYED`/`EXTERNAL_WATCHDOG_NOT_DEPLOYED_REHEARSAL_ONLY`/`LIVE_GATE_CLOSED`，`:263` 在 `inspect()` 中追加）；`scripts/run_live.sh:2-5`（硬停 `exit 3`）。**动态负例**：`sh scripts/run_live.sh` → 打印 BLOCKED、`exit 3`（`ENV_TOOLS_LIVEGATE_20261119T174800Z.log`）。v1/v2 Packet `live_gate=BLOCKED`。 | **VERIFIED（代码 + 本地负例）** |
| `M0` | `DECISION_PENDING` | `docs/SECURITY_APPROVALS.md:61`；`docs/REVIEW_G4F_INDEPENDENT.md:39`；v1 Packet `manifest.live_gate=BLOCKED` 与 `state_constants` | **VERIFIED**（文档级） |
| `E5_PRELIVE_FULL` | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | `docs/REVIEW_G4F_INDEPENDENT.md:40`、`:377`；`docs/M0_G4F_REVIEW_ERRATA.md:97`、`:252`、`:269`；`docs/M0_G4_HUMAN_HANDOFF.md:4`、`:124`；矩阵 `E5-FULL` 行（`…Closeout_Test_Evidence_Matrix_v1.0.csv:47`，status `BLOCKED`）；v1/v2 Packet `manifest.contract.state_constants` | **VERIFIED**（文档/工件级）；**任何变更 = HUMAN_REQUIRED** |

补充说明：

- 只有 `LiveGate` 具有**可执行代码强制**；`G4-H`/`G5`/`G6`/`M0`/`E5_PRELIVE_FULL` 是治理/验收状态，代码中没有可绕过或可开启的入口，也没有 `authorize()`/`approve()` API（见 `REVIEW_G4F_INDEPENDENT.md` §3 R1）。
- 本轮**没有**修改任何常量、没有新增 `--live` 路径、没有接触 approval/Key 注入面。

---

## 6. 无 Key / 无网络 / 无 Live 基线证据（本阶段）

| 检查 | 实测 | 命令/证据 | 分类 |
|---|---|---|---|
| Key 名环境变量（值不读取） | 0 命中（`DEEPSEEK`/`OPENAI`/`ANTHROPIC`/`API_KEY`/`TOKEN`/`SECRET`/`PRIVATE_KEY` 名称级） | `ENV_TOOLS_LIVEGATE_20261119T174800Z.log` | **VERIFIED**（本阶段） |
| 已知 Key 变量 | `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`OPENCODE_API_KEY`/`AT_M0_LIVE_APPROVED`/`AT_M0_ALLOW_LIVE` 全部 `<UNSET>` | 同上（只输出 SET/UNSET，不打印值） | **VERIFIED**（本阶段） |
| `.env` | 仅存在仓库内 `.env.example`（425 B，示例，tracked）；无 `.env`/`.env.*` | 同上 | **VERIFIED** |
| 委托宿主代理变量（非凭据） | `http(s)_proxy`/`all_proxy`/`no_proxy` 已设置（`no_proxy` 值含 `api.deepseek.com,opencode.ai` 等路由名） | 同上；**本阶段未发起任何外部 HTTP/TCP** | **VERIFIED（观察）** |
| 容器 | `podman ps -a` 输出仅表头（无容器） | 同上 | **VERIFIED** |
| Live 负例 | `sh scripts/run_live.sh` → `BLOCKED …`、`exit 3`（本地脚本，无网络） | 同上 | **VERIFIED** |
| 真实 Provider / 模型 / 计费调用 | 本阶段执行 0 次；仅执行本地 git/sha256sum/python/podman 只读命令与 `run_live.sh` 负例 | 本文件与全部证据日志 | **VERIFIED**（本阶段） |
| 完整 A-07 负例矩阵（CLI `--live`、Adapter 4 入口、strace、全历史 scanner） | 未在本阶段重跑；引用 G4-F 独立复核只读结论 | `REVIEW_G4F_INDEPENDENT.md` §8（`:219-243`） | **PARTIAL** |

> 说明：宿主 `no_proxy` 值里出现 provider 域名只是代理路由配置，**不是凭据**；本阶段没有任何出网行为。

---

## 7. 外部并发观察（只观察、未触碰）

`git worktree list` 实测 11 条（采集时点）：

| 路径 | HEAD | 分支/状态 | 观察备注 |
|---|---|---|---|
| `/root/Autonomous Teacher` | `3e7afee` | `main` | 主工作树；本轮只读，`git status` 0 行 |
| `/root/Autonomous Teacher/worktrees/m0-g4h0` | `3e7afee` | `work/m0-g4h0` | A 线兄弟 worktree（非本线写入面） |
| `…/m0-g4h0-base` | `3e7afee` | detached | 同上 |
| `…/m0-g4h0-core` | `3e7afee` | `work/m0-g4h0-core` | **本线 worktree** |
| `…/m0-g4h0-docs` | `3e7afee` | `work/m0-g4h0-docs` | 其它 agent 写入面 |
| `…/m0-g4h0-fix` | `3e7afee` | `work/m0-g4h0-fix` | fix agent 写入面（P2-03..06 修复） |
| `…/m0-g4h0-research` | `3e7afee` | `work/m0-g4h0-research` | 其它 agent 写入面 |
| `/root/at-f4-clean` | `7000f72` | detached | 历史 F4 清理 worktree（只观察） |
| `/root/at-g4f-impl` | `e7d9296` | detached | G4-F impl/Reviewer 历史 worktree（只观察） |
| `/root/at-m1-offline` | `3e7afee` | `work/m1-offline-design` | **B 线 worktree**；只观察，未触碰、未共享 artifact/凭据 |
| `/root/g4b-baseline` | `2f1e41f` | detached | 历史 G4-B 基线 worktree（只观察） |

- 本轮对其它 worktree 只执行了 `git worktree list` 与 `git -C <dir> rev-parse HEAD` / `git -C <dir> status` 级别只读命令；未写入、未 `checkout`、未 `merge`、未 `push`、未共享任何 artifact/凭据/运行时状态。
- `/root/at-m1-offline` 属 B 线（M1 离线设计），与 A 线本轮无执行依赖；本线未读取其工作内容、未共享产物。

---

## 8. A0 完成度与分类汇总

| 项（对应执行方案 §8） | 本阶段结果 | 分类 |
|---|---|---|
| A-01 SHA / 代码 / Stage / 依赖冻结身份 | Git 身份、src sha256 清单、受保护文件、docs 冻结哈希已核对；Stage manifest 哈希 `82e10c6f…` 实测一致（`sha256sum stage/manifest.json`）；rootfs/deps 仅引用 stage-summary 记录值，未全量复算 | **VERIFIED（Git/src/docs/Stage manifest）**；`rootfs/deps/stage tree` 全量复算 = **PARTIAL** |
| A-02 P2 与历史残余逐项 disposition | `docs/g4h0/RISK_DISPOSITION.md` 已交付（建议态，含维护者决策空栏）；维护者签收 | **PARTIAL**（文档已交，未签收）/ **HUMAN_REQUIRED** |
| A-03 并发 consume 恰一次/失败码稳定 | 本任务不做代码修复（由 fix agent 负责）；本线未验证修复 | **UNVERIFIED / NOT_RUN（本线）** |
| A-04 旧 Packet 不改写；新包完整性可复核 | v1 173/173 OK、177 files/0 symlink、两次复核一致；v2 本地重建 175 files / 173 hashed / payload tree 匹配 / 0 sidecar；v1 未改写 | **VERIFIED（本地）**；独立复核/签收 **HUMAN_REQUIRED** |
| A-05 正式 Provider 契约 | 不在本任务范围（另行负责） | **NOT_RUN** |
| A-06 Runbook / 签名 / Key / Egress / Watchdog | 不在本任务范围（另行负责） | **NOT_RUN** |
| A-07 LiveGate 仍 BLOCKED、0 真 Key/真 HTTP | 本阶段 Key 扫描 0、`run_live.sh` exit 3、`podman ps -a` 空、0 Provider 调用；完整 CLI/Adapter/strace 矩阵未重跑 | **PARTIAL** |
| A-08 独立 H0 Review | 未发生；需独立 Reviewer | **HUMAN_REQUIRED** |
| 工具版本 | 实际存在项已记录；host `dsh` CLI 版本与冻结 runtime 不同（已披露） | **VERIFIED / PARTIAL（dsh）** |
| `src` 回归测试 | 本阶段无 `src/` 变更，未运行 | **NOT_RUN（按设计）** |

> 本文件不产生 A-01..A-08 的 PASS 裁定；唯一可接受裁定仍为 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE` 或 `PARTIAL/BLOCKED`，由独立 Reviewer 从冻结 SHA 复现给出。

---

## 9. 证据索引

`docs/g4h0/evidence/`（采集时间均为 UTC；sha256 见下表）：

| 文件 | 内容 | sha256 |
|---|---|---|
| `BASELINE_COMMANDS_20261119T174015Z.log` | Git 身份 / src 清单 / docs 哈希 / 常量 grep / 工具 / 外部 worktree / v1 Packet 检查等原始命令输出 | `ae81a8292a71d1bee573a415624543406fd7802e92be58be066d853b028ef826` |
| `BASELINE_HASHES_20261119T174453Z.txt` | 基线哈希表：src 50 文件、docs 11 文件、控制文件、stage 身份、git tree 对象 | `f356d61d9f9e6aeec536f6b0eacf2b774787695ec1bb45e9f2cf43964565f9fc` |
| `ENV_TOOLS_LIVEGATE_20261119T174800Z.log` | 脱敏 env 扫描（值不打印）、工具版本、`podman ps -a`、`run_live.sh` 负例、主工作树状态 | `e58a17bffe8c0f5df3e3b785f04b07bfcbaa53a443c604bebf2f259565a49e34` |
| `P2-01_packet_v1_verify_20261119T174453Z.log` | v1 Packet 只读校验：177/0、173/173 OK、tree 漂移复算、sidecar 元数据 | `925a76dea4d1f09e017a6964be218649289ea6325a53e97b84cb87b74b0e12ab` |
| `P2-01_packet_v2_build_20261119T174016Z.log` | v2 builder 输出（`ok:true`、172 payload、tree） | `01740584401627628ddd83a555b0c16b32fa0444326aee60c35d7467a7620d32` |
| `P2-01_packet_v2_verify_20261119T174135Z.log` | v2 验证：175/0/0、173/173、175/175、manifest 字段、integrity report | `a1dec24b649abccf6784a066b3443bb090b3249bcae8cdee70a7e37786f015a4` |
| `P2-01_v2.sha256` | v2 Packet 全部 175 文件 sha256 清单（`cd packet-v2 && sha256sum -c …` 可复核） | `fbabce1b0c5cfa01584a71bf9b5e7d9df4e2c9fa7147940f2441c6bb98560145` |

关键命令复核方式：

```text
cd "/root/Autonomous Teacher/worktrees/m0-g4h0-core"
sha256sum -c docs/g4h0/evidence/BASELINE_HASHES_20261119T174453Z.txt   # 注意：该文件含 # 注释，非全量 sha256sum 校验格式
cd artifacts/g4h0/packet-v2 && sha256sum -c ../../docs/g4h0/evidence/P2-01_v2.sha256   # 期望 175/175 OK
```

---

## 10. 范围与不得外推

1. 本文是**无 Key、离线、本地**的基线核对与证据工程记录；**不构成** G4-H0/G4-H1/G4-H2/G5/G6/Live 的授权或部署证明。
2. 本文的 VERIFIED 仅指“实际命令/哈希在采集时点可复核”，不等于独立 Reviewer 的通过结论，也不等于 E5-PreLive Full。
3. v2 Packet 是本地完整性重建，**未经独立复核、未提交、未签收**；P2-02/P2-07 内容问题在 v2 中仍存在。
4. 任何 `src/`、`docs/` 冻结 Packet、Stage、rootfs/deps、HEAD 变化都会使本文失效，必须重新采集。
5. 真实 Provider/Key/TLS/账单/额度、人类信任根、Key Broker、受信 Egress、Watchdog 部署均**未验证**，属 HUMAN_REQUIRED。

---

## 附录 A — `src/` 50 个文件 sha256（工作树字节 = HEAD 字节）

```text
1b0c188538b2f9b51c64068008a9a5c39726156a5da4f6cc875f760ab5cd2a2c  src/autoteacher_m0/__init__.py
d87b9268ccca533917485d9c08cc21a180ff7a04cc013fd6657638c12f0d58f0  src/autoteacher_m0/accounting/__init__.py
0016304a1181677beae76072e639ddfc7988042c46a6400f1ca3dfe4b8157fa6  src/autoteacher_m0/accounting/broker.py
74ccb0f69dbfa6887eaa8dff8cd04c23340e514076abcb9b7f511b454927e6a7  src/autoteacher_m0/accounting/broker_usage.py
50e2ae7106ecf9584e9f4081a1fafa594b4b220bad9ef195c61142cac1c90e7e  src/autoteacher_m0/accounting/budget.py
03d45a2fe13350466e04fae1a0210a8b6ae247fb3a1b4e38ddd12f7b1d6f8e3e  src/autoteacher_m0/accounting/call_identity.py
15b3cf9d42eebf2c5758d180c8303dacaac1d4e9d3bbf0776f9219642e9ead97  src/autoteacher_m0/accounting/ledger.py
90a355618d1e85f03b0dd7bc7ff23c84cc66dd93995157c824eee6cc400b7187  src/autoteacher_m0/accounting/observation.py
19f8a89300601294a829a2edb2d445699d0b0f1e1b76e03a05c462abeac22b2d  src/autoteacher_m0/accounting/pricing.py
923ebca97309c41ddcc2175d94887d844f565057a70a9d417b32fb15773957c2  src/autoteacher_m0/accounting/usage.py
f3cf01ecc3970cffd8a411fd387090c5ac7b3ea5aff17b51261cb8b86a08dbdb  src/autoteacher_m0/bridge/__init__.py
ad979ac3aa2d5e3db2a102b0c4b49b05be165d1a0ed5e486463aa5df889436d2  src/autoteacher_m0/bridge/admission.py
ccd008bd55bda8d344152856912dbde9dfe1e29d5accb53973a938e1e4b59795  src/autoteacher_m0/bridge/attempts.py
1fb8f8ca85b04244a4b013000513db33fdb643f089315c5224c8602064977c15  src/autoteacher_m0/bridge/broker_client.py
0152fcde6bba7c7989740b1bfde8f72744e6c709da22ebbe4940cb443eb35ca3  src/autoteacher_m0/bridge/controller.py
8be106339cd529864019971c415571f5c8232281b39fdbd998bbd915045717c2  src/autoteacher_m0/bridge/dispatch_audit.py
29645bce7cd46d65451feca0498764b279baf947ecf1010d58a4aeb9aafbfb35  src/autoteacher_m0/bridge/fake_backend.py
ff7b4016582ee3f436a9464721a38085fb6d803c207f524dddbbe48b02014774  src/autoteacher_m0/bridge/ipc_server.py
49cc1e832ffc500cc821c9652f52923cc457c7952550eab621743f9a7d740a6a  src/autoteacher_m0/bridge/protocol.py
31555386ec3cbeb6ed4584a861b1da3313fa1e00b026cd8f43cd05227ba2c940  src/autoteacher_m0/cli.py
8b101d2f6c921e0c244156a6439bd7341ee2d6781d3fd4c34a62ca900e9adb4c  src/autoteacher_m0/contracts.py
f1b1336a964cbff0560813ea8de6fa30beae1126beda8b4bb38e6aa1eaaa7763  src/autoteacher_m0/evaluation/__init__.py
5c69255cec6df35e36bb931a18597362cf229528d9396a42a0fb983cffd5806f  src/autoteacher_m0/evaluation/contracts.py
1b2f5333db932406feebf18bf72b74bc5144c5a6015512a759cc8f4bcbd1a41c  src/autoteacher_m0/evaluation/graders.py
e4d47727c34e74d56197fd6bd4020b7f872fb9648a801e60a55af4d08887c2ec  src/autoteacher_m0/evaluation/leakage_checks.py
c7d74d52db99550ff1d0b75db5075164e94e049ba1886680c7e08b263e3ed656  src/autoteacher_m0/experiments/__init__.py
ab45c1cdd69b1cde440cb85b0d829cb12fb8bb1cc02fb09807856660b24054ee  src/autoteacher_m0/experiments/cli.py
85a360e48a3b4fa5a8a66d89689c2f88862414076e3136ba885571eb047c9126  src/autoteacher_m0/experiments/fixtures.py
afd0358a68cd8229ea404645611eec2fbdeeb5d0102782620aa2e4cae1fad666  src/autoteacher_m0/experiments/mock.py
2926c328c66f261edeea11729e643b23f2de56cb2d8f4ad37aaa494500908669  src/autoteacher_m0/experiments/paired.py
144a01ba1129ddda59caba9b9faa0365cee821fb76b9778f5fe9c473b749a6b3  src/autoteacher_m0/experiments/report.py
b2a9ed45689c7bb9ab72fe3d2258439d28c3bf32009c539be96e72151eddd762  src/autoteacher_m0/experiments/runner.py
85286fb2231e1b4d0c4dc1fe16ed8bf34b56c63e6051176c9ca7710d4e1d6c0a  src/autoteacher_m0/runtime/__init__.py
29d63b6041668b8f8fb783ebc3bc18cac38b14969cd82cdbfbb5b0a734e24381  src/autoteacher_m0/runtime/base.py
888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a  src/autoteacher_m0/runtime/dsh_adapter.py
8f3198cc12fe7598717ab480c57c10062576893b1d0ad1936e9a997ef695547a  src/autoteacher_m0/runtime/mock_adapter.py
79b30c9d8683e4b6e38bed9c52ec1649d8bd80202deae0df19baa347ed268182  src/autoteacher_m0/runtime/structured_output.py
3795c512371534549b6db909ddc18952aa7d0a1f74b9703ef8c1d58aee302423  src/autoteacher_m0/security/__init__.py
5696b2c812c21194b82e56a17344c81c631e56becec660b47abcc851a8a7b5b2  src/autoteacher_m0/security/authorization.py
f7424e7e19777702c1a109223b4d10d66c7bf2d31330c786be9b2c61d91c3abb  src/autoteacher_m0/security/credential_boundary.py
8b4c3d86be5b855f653025254a3379b3dfae24142945780d1e4b6daa18d030d1  src/autoteacher_m0/security/docker_runner.py
64f412a861db5128955fe739d1649b5faa06f6aae7c6350b564ecf9fa011bc19  src/autoteacher_m0/security/ed25519.py
cb4961db034c9d5ad62192841c1beb8d965a8392fa3f3226181135ec7073602e  src/autoteacher_m0/security/egress.py
3ed0863440d26105f30f84579f07105c298ed586cbd8e4616c15fad495afb23a  src/autoteacher_m0/security/gates.py
d50a55a18b45044f0cc65b266491a42469d8b452f63bbe348a47e1df8e0bdba0  src/autoteacher_m0/security/live_controller.py
42e1d061ed1e54264d120e4ae7dbffc0b7534abdcac4d9280a636bef58edb965  src/autoteacher_m0/security/watchdog.py
eb9d6b202ccb4c99bfade12b38b5fd03e583ddaee67aca58becf4b56aeb758e8  src/autoteacher_m0/settings.py
f970c89eaf7b1a9d16861411cee837a00ad20a85676ac6e9d3a36c86eb8b0298  src/autoteacher_m0/storage/__init__.py
70ce4a7a48a7e47e88911a208a27aca50b74aefbdcde08fa3d6e79c251ed3dab  src/autoteacher_m0/storage/artifacts.py
12e49506b993861333617b674136626e6febc5d8c9759079f7fba305f4f54ebd  src/autoteacher_m0/storage/schema.py
```
