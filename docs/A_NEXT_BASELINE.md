# A-NEXT — A0-01/A0-02 基线快照与冻结边界（A-PR0）

- **文档 ID**：`A-NEXT-BASELINE-v1`
- **生成者**：A-PR0 Implementer-Docs（子 Agent；**非** Lead、**非** Independent Reviewer）
- **生成时间（UTC）**：`2026-11-20T19:36Z`–`19:45Z`
- **工作树 / 分支**：`/root/Autonomous Teacher/worktrees/a-next-baseline` / `docs/a-next-baseline`
- **基线起点**：`work/g4r` = `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`（本工作树在 A-PR0 提交前的 HEAD）
- **性质**：**基线快照 + 冻结边界声明**。不是测试执行报告、不是 PASS、不是授权；不改变任何门状态常量。
  本轮**未**重跑 Reviewer/Integration 的测试（无 OCI/无服务重启），所有“环境/计数”均为**引用既有冻结证据**
  （`SOURCE_INSPECTED` / `REVIEWER_REPORTED`），不是 `INDEPENDENTLY_REEXECUTED_THIS_TURN`。
- **硬约束遵守**：只写本工作树 `docs/A_NEXT_*.md` 三个新文件；未改 `src/tests/scripts/`、冻结 docs/Packet/矩阵、
  主工作树、其它 worktree；0 真实 Key/Provider/HTTP/TCP；未 `push`/`merge`；未触碰 LeadB 的 `m1_*`。

## 1. 当前分支/远端快照（本轮 `git fetch --all --prune` 后实测）

| 对象 | SHA | 说明 |
|---|---|---|
| `main` / `origin/main` | `3e7afee077845a071cd364e93ab209cac20b2d5f` | 主分支；本次读取时仍未合并 A/B 任一线 |
| `work/g4r` | `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af` | **canonical 候选**（本分支起点）；= 冻结 impl `d33e0aa` + docs/Review 证据链 |
| 冻结 src impl | `d33e0aabd1714a486325b745c436cb59855d6539` | G4-R 产品实现冻结（Reviewer 最终基线） |
| `work/m0-g4h0` | `15c5a08b6f518dadf43f652d5a25f91d5d80811b` | 另一并行线（H0 准备包，非 G4-R 后续提交） |
| `b-pr1` | `c0c6ee5` | B 线分阶段分支（非 GitHub PR；不得称为已合并 PR） |
| `b-pr2` / `b-pr3` / `b-pr4` | `b3d9c8c` / `38e9d2d` / `933ccde` | 同上 |
| `b-pr5` = `work/m1a-mvp` | `4706250643fd42d48d69ddad7159e011955fa9fd` | B 线 M1-A 交付 |
| `work/m1-offline-design` | `290c5770461bb5af2a38c6e6d24ee76350bcb410` | B 线 M1-Offline 交付 |
| `docs/g4r-independent-review` | `e72255d`（含后续 `4bd42d5` addendum/errata 线性历史见 `work/g4r`） | Reviewer 报告来源分支（已合并入 `work/g4r`） |
| `docs/g4r-review-errata` | `12431a9` | G4-R erratum 分支（已合并入 `work/g4r` 的 `fd1d3a6`） |

> 以上 SHA 为 **2026-11-20T19:36Z 抓取时实测**；不假定交接包内快照永久不变。A-PR0 交付提交在本文件之后
> 依次追加，只会增加 `docs/A_NEXT_*.md` 新文件（见 commit 列表于交付报告），不改变上述分支。

## 2. 工作树身份（实测）

| 项 | 值 |
|---|---|
| branch | `docs/a-next-baseline`（从 `work/g4r` @ `fd1d3a6` 创建） |
| A-PR0 起点 HEAD | `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af` |
| `HEAD^{tree}` | `d19be0ef0e22984b02da21185cd1dedc00017302` |
| `HEAD:src` tree | `e10d7c7ce135b741833529d4734d1d307a13ee28`（= 冻结 impl `d33e0aa` 的 src tree） |
| 工作区 | 起点 `git status --porcelain -uall` = 0 行（clean） |
| 继承分支线 | `main 3e7afee` → PR-R1..R4 合并 → 冻结 `d33e0aa` → docs/Review 合并 → `fd1d3a6` |
| 与 `d33e0aa` 的差异 | 54 files / `+4678/−46`，**全部为 docs + Reviewer 证据/探针**；`git diff d33e0aa..fd1d3a6 -- src tests` **为空**；非 docs 仅新增 `scripts/g4r_review/{r_rev2_race_probe,r_rev5_packet_verifier}.py`（Reviewer 自建只读探针） |
| 与 `main` 的差异 | 83 files（含 28 个 impl A 文件与 3 个 M 文件，见 `A_NEXT_BRANCH_RECONCILIATION.md`） |

## 3. 基线来源与证据等级（防止把“引用”当“本轮复跑”）

| 等级 | 本文件中的使用 |
|---|---|
| `SOURCE_INSPECTED` | Git SHA、merge-base、diff 统计、文件哈希：本轮由 `git` 命令实测（§5/§6） |
| `REVIEWER_REPORTED` | Reviewer 独立复算的 rootfs/Stage/Packet/加载身份、R-REV 裁定：引自 `docs/REVIEW_G4R_INDEPENDENT.md`（sha256 见 §5） |
| `OWNER_REPORTED` | 联合回归/OCI/Node/ruf 计数：引自 `docs/M0_G4R_PACKET_SUMMARY.md`、`docs/M0_G4R_IMPLEMENTATION_REPORT.md` |
| `INDEPENDENTLY_REEXECUTED_THIS_TURN` | **无**（本轮只做只读 Git/哈希核对；未启动 OCI、未跑 pytest） |

> 因此：任何“测试已通过”的表述在本文件只作为**引用**，不得当作本轮新证据；A0-03（rootfs 防写）等未实测项
> 一律 `NOT_RUN`（§7）。

## 4. 冻结实现与环境身份（引用 Packet v2 / Reviewer 报告）

来源：`artifacts/g4r/packet-v2`（gitignored，仓库外）+ `docs/REVIEW_G4R_INDEPENDENT.md:1-38`。以下值本轮
**只读核对**（manifest/hashes 的 sha256 实测，见 §5），环境本身未重测：

| 项 | 值 | 状态 |
|---|---|---|
| frozen impl（code） | `d33e0aabd1714a486325b745c436cb59855d6539`；`impl_content_sha256=5551078a…` | `REVIEWER_REPORTED` |
| docs commit（Packet） | `bc08bdd3f6cceb73462c33acd98bda276d0b1fbf` | `REVIEWER_REPORTED` |
| Final Stage | `stage-20261120T165407Z`：manifest `cc7ccb61…`、tree `933f2c07…`、trusted `f10053d4…`、candidate `131ab68e…`、base/head=`d33e0aa`；loaded src 52/52 == git blobs | `REVIEWER_REPORTED` |
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（清理后；**非全程 NO_DRIFT**，见 P1） | `REVIEWER_REPORTED` |
| deps / runtime / adapter JS | `e07729d7…` / `1cc41d5a…`（DSH 0.2.2-rc.2） / `2cb42461…` | `REVIEWER_REPORTED` |
| 工具版本 | Python 3.11.15、pytest 9.2.0、ruff 0.17.5、Node v22.23.2、Podman 4.9.3 | `REVIEWER_REPORTED` |
| 独占窗口 | `2026-11-20T17:05:50Z–17:08:20Z`；T0/T1 rootfs=`25491e45…`、`T0_T1_equal=true`、`frozen_rootfs_unchanged=true` | `REVIEWER_REPORTED` |
| 历史 Stage | `82e10c6f…`（G4-F 旧 Stage）仅 HISTORICAL，不作为本轮身份 | `REVIEWER_REPORTED` |

**P1 环境限制（必须保留）**：冻结 rootfs 在审查窗口内曾被 OCI `--rootfs` 直接写入（漂移
`0340fb78…`/`a6737150…`/`e1a8fcf9…`，两次窗口 16:52–16:53Z、16:55–16:59Z），已于 17:01:49Z 清理恢复；
Reviewer 17:26:37Z 独立复算一致，并裁定 **P1 = RESOLVED_WITH_LIMITATIONS**。因此：**不得写“审阅全程
immutable / no drift”**；后续 OCI 必须使用 rootfs 可写副本并串行独占（A0-03/A5 负责落地，本轮 `NOT_RUN`）。

## 5. 受保护文件清单（实测 `git blob SHA-1 @HEAD` + `sha256` 内容摘要）

说明：以下文件在本分支 **相对 `main 3e7afee` 未改动**（`git diff --name-only 3e7afee..HEAD -- <list>` 为空，
见 §8 复核），且 A-PR0 不写入这些路径。`sha256` 为工作树文件内容实测值，供独立复核。

| 文件 | git blob SHA-1 @HEAD | sha256（实测） |
|---|---|---|
| `src/autoteacher_m0/security/gates.py` | `edf7f45fdbd058f89177a8e8f8d918274516b9d4` | `3ed0863440d26105f30f84579f07105c298ed586cbd8e4616c15fad495afb23a` |
| `src/autoteacher_m0/runtime/dsh_adapter.py` | `86ae5d6e6f8bf50f68972e28744530af4f109dcf` | `888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a` |
| `src/autoteacher_m0/cli.py` | `b68822fdd376ab816e0179e0482dd1a4266de8d1` | `31555386ec3cbeb6ed4584a861b1da3313fa1e00b026cd8f43cd05227ba2c940` |
| `scripts/run_live.sh` | `dd0814e165eea620164e7c6b372abbdc014e972a` | `a8a2753fd6b6b096b66adecfbdde044b42c6c4a26630c24f0fc269b1fe5f957a` |
| `config/dsh/sdk-minimal.patch.yml` | （见 HEAD） | `ed93b96cdcf2c6052ee128908188f50e5e432241b825447bb2c0494811bc4317` |
| `config/dsh/target-runtime.patch.yml` | `cd17534a39484004d63eff87fce66ec01d47b1de` | `367ec27c6130993d3968658fb278ed1837cf83f99c891a72a2c7ecb441fc7d5a` |
| `config/dsh/target-runtime-opencode-go.patch.yml` | （见 HEAD） | `9c5fe713e5af25f47e24f4db9c4f30172c31bcfe3030301b7eeb5831c47fc652` |
| `docs/REVIEW_G4F_INDEPENDENT.md`（旧 G4-F Review） | `83f08de257d607c616918870d07eb0a19c816b1f` | `b17977d1ff8506de440996f7bd411149ae968cef6564391b74b28980468ddc4b` |
| `docs/M0_G4F_REVIEW_ERRATA.md`（旧 errata） | `00bd61f111672ac9b0f810ad28bbfe22c14f0a8d` | `7b8209db9c15897e6b4d271361703e4425a9a3a361cb3818d53e5fd92eb9b42b` |
| 旧 46 行矩阵 `docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv` | `4490907ae8cf132f750a5f11b9b940b825f50c61` | `0f4e25ae76632ff60e0c644d34a19bf6c602cf49e347112a1fb3be87a091dba3` |
| `docs/REVIEW_G4R_INDEPENDENT.md`（G4-R Review，只读归档） | `73366681b84f54f7a99cbd9950d7d8fe48e74699` | `0599856aec247d0834a88a8967db81bd68965578a35eed37dbdf45322068446c` |
| `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`（冻结 65 行矩阵） | `6fe675536a9277ae1fe07bf4e99b3c3f48052230` | `741d7d5598cb9357c9ec9126ebcc277d504af93c0bc591af0d0c395b303d1382` |

Packet（gitignored，仓库外；本轮只读 sha256 核对，**未写入**）：

| 对象 | 路径 | 实测 sha256 |
|---|---|---|
| v1 Packet manifest | `/root/Autonomous Teacher/artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99/manifest.json` | `4aed2a923ea3fae52ed3eac9d0c5838077242ed32045804d687dcef703a1d7f2` |
| v1 Packet hashes | 同上 `/hashes.sha256` | `421b07ae3ad0eac2d36c032cd384d252dfda4ac521e193577aed56fc60ca9d3d` |
| v2 Packet manifest | `/root/Autonomous Teacher/worktrees/g4r-packet-final/artifacts/review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539/manifest.json` | `fe45d7602bd7a115cfdc3dd3a85e889c0f7b4fa642c03a54717c06f0bcf403a9` |
| v2 Packet hashes | 同上 `/hashes.sha256` | `e7a67c77b8e213fac32cb4aabeae56075dcf4982c0281479fae25cca1c4bdddb` |

（Reviewer 侧 43 份证据的目录级清单摘要：`8326e4ca4c6f79c0ebf9e73edbf2db87dc982901207bd97935c97dd72fc3a02a`，
计算方式见 `A_NEXT_REVIEW_STATUS_RECONCILIATION.md` §5。）

## 6. 分支方向与“0 未授权合并”声明

- **共同祖先**：`git merge-base main work/g4r` = `git merge-base main work/m0-g4h0`
  = `git merge-base work/g4r work/m0-g4h0` = **`3e7afee`**。即两条线是**同源平行分支**，不是上下游关系。
- 提交数：`main..work/g4r` = 28；`main..work/m0-g4h0` = 20。
- `work/g4r` 的 9 个 merge 提交均为**历史 PR-R1..R4/Review 集成合并**（`4842985`、`6f92c9f`、`418cd05`、
  `eb67329`、`5bf9b8b`、`d33e0aa`、`64522d9`、`9768933`、`fd1d3a6`），随基线继承，**不是本轮新增**。
- **本任务声明**：分支 `docs/a-next-baseline` **只追加 docs 提交**（`docs/A_NEXT_*.md`）；
  `git rev-list --merges fd1d3a6..HEAD` = **0**；未执行任何 `merge`/`cherry-pick`/`rebase`/`push`；
  未修改其它工作树；未触碰 `m1_*`（`git diff --name-only 3e7afee..HEAD | grep -E 'm1_|m1_teacher|m1_offline'`
  = 0，见 §8）。**0 个未授权合并**。
- 说明：`work/g4r` 继承的历史合并本身已由 G4-R Reviewer 报告覆盖（`M0-G4R-INDEPENDENT-REVIEW-v1`）；
  本声明只表示 A-PR0 未引入新的合并/代码变更。

## 7. 门状态与 A-PR0 验收映射

**状态常量（冻结，未变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

| A-PR0 项 | 本组文档覆盖 | 状态（本轮） | 说明 |
|---|---|---|---|
| A0-01 Branch arbitration | `A_NEXT_BRANCH_RECONCILIATION.md` | **PARTIAL（docs 完成，待 Reviewer）** | merge-base/文件级 diff/逐函数行为矩阵/F-02 覆盖结论已交付；Reviewer 独立复跑未做 |
| A0-02 Reviewer matrix reconciliation | `A_NEXT_REVIEW_STATUS_RECONCILIATION.md` | **PARTIAL（docs 完成，待 Reviewer）** | 65/65 行对账 + 证据 SHA；append-only；未改冻结字节 |
| A0-03 Immutable rootfs | 本文 §4/§5 + 分支报告 §7 | **NOT_RUN** | 尚无代码级 `--rootfs` 防写/写副本强制；仅文档与流程要求（A5 落地） |
| A0-04 Packet/Review 冻结 | 本文 §5 | **PASS（只读哈希核对）** | v1/v2 Packet、G4-F 旧件、G4-R Review 字节与登记值一致；本任务零写入 |
| A0-05 0 未授权合并 | 本文 §6 | **PASS（本任务）** | 本分支仅 docs 提交，0 merge/cherry-pick/push；历史合并为继承 |
| CI 检测 main/canonical 来源 | — | **NOT_RUN** | 交接要求“CI 能检测”，本仓库尚无该 CI；需 A-PR0 后续或维护者决定 |

## 8. 复核命令（可复现）

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-baseline"
git fetch --all --prune
git rev-parse main work/g4r work/m0-g4h0
git merge-base main work/g4r; git merge-base main work/m0-g4h0; git merge-base work/g4r work/m0-g4h0
git rev-parse HEAD 'HEAD^{tree}' HEAD:src
git diff --stat 3e7afee..d33e0aa; git diff --stat d33e0aa..fd1d3a6; git diff --stat work/m0-g4h0..work/g4r
git diff --name-only 3e7afee..HEAD -- <§5 受保护文件清单>   # 预期：空
git rev-list --merges fd1d3a6..HEAD                          # 预期：0
git diff --name-only 3e7afee..HEAD | grep -E 'm1_|m1_teacher|m1_offline'  # 预期：无输出
sha256sum <§5 文件>                                          # 与表中值比对
```

> 说明：`git diff 3e7afee..HEAD -- <受保护清单>` 在 A-PR0 三个 docs 提交后仍应为空；如有输出即 **STOP**。

## 9. 不主张 / STOP

- 不主张 A-PR0 通过、G4-R/ G4-H0 升级、E5/B03/G4-H/G5/G6/M0 任何门通过、部署或 Live。
- 不主张本轮独立复跑测试；不主张环境“全程 NO_DRIFT”；不主张 B03/E5-P04 关闭。
- 不主张任何 `b-pr*` 已构成 GitHub PR 或已合并；它们只是分支。
- **STOP**：等待独立 Reviewer 对 A-PR0 文档与基线做复核；A-PR1+ 需新的任务/审批。维护者决定不由此文件代替。
