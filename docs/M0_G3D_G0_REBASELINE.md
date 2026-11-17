# M0 G3-D — D-G0 重基线（最终 approved D1 输入 `4bd4803`）

> **状态**：`D-G0_REBASELINE_PASS_AT_4BD4803`（D-G0-01 在最终 approved 输入上 PASS；D-G0-02..05 沿用原 PASS 并做现场身份复核；**不是** D1 实施，**不是** G3-D PASS，**不是** Live/GO）。
> **基线**：HEAD `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`；产品起点 `b2f6af054555705192c4e1ae3019a68078764736`；原 D-G0 文档 `docs/M0_G3D_G0_BASELINE.md`（sha256 `1411e3587b7820a580b8cc6bda7b1a8de0e99733bb7d7368123c41b7e7b02562`，提交 `645190e`）**字节未改**。
> **范围**：只读 Git / Stage / Runtime / 环境核验与新增 docs；不改产品代码、测试、scripts、旧 evidence、Packet 或原 baseline；不实现 D1；全程 0 Key / 模型 / 外网 / Live；不 `podman pull`。
> **结论先行**：并行 D1-A/D-P0 工作已作为 `51abc66`、`4bd4803` 进入线性历史，HEAD 为 `4bd4803` 且工作树 **clean（0 行 / 0 字节）**；相对 `b2f6af0` 的 `src/tests/spikes/plugins` 差异只有 2 个 D1-A 源码文件 + 3 个测试文件，D-P0 无 `src` 改动，rootfs/deps/stage canonical、DSH/Node/0-Key/LiveGate/清理均与冻结值一致。因此 **D-G0-01 更新为 `PASS_AT_4BD4803`**；原 18:44 时点的 `BLOCKED_WORKSPACE_CONFLICT` 保留为真实历史快照，不追溯改写。D1 的产品源码基线为 `4bd4803`，必须从该 SHA 新建 Stage，**禁止复用旧 G3-C stage（`e6fde1c` 批次）**。
> **不变量**：`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立；LiveGate 仍 BLOCKED；本文件不授予 Live/G4/G5。

---

## 0. 摘要

| 项 | 现场结果（2026-11-17 18:54–19:07Z） |
|---|---|
| 重基线 HEAD | `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`，父 `51abc6619ef87ad7b93aa3162fed52ab14df6e56`，tree `e5b91a2bce19ac83f4cdf05df44dec1d71b1e627` |
| 分支 / 远端 | `main`；`origin git@github.com:ygmldr/Autonomouse-Teacher.git`；`origin/main` = `fff36232687afb779befb49fb6e2a10cedbcb7fd`（本地领先 5，未 fetch） |
| `git status --porcelain -uall` | **空输出，exit 0，0 行 / 0 字节** |
| 首次 clean 快照 | 原 D-G0 记录 18:23:42Z 在 `d74f2ff` clean；18:33:41Z 起被并行 WIP 污染；现于 `4bd4803` 重新 clean |
| `b2f6af0..HEAD` 产品/测试面 | `src/tests/spikes/plugins` 仅 5 文件：`controller.py`、`ipc_server.py`、`test_d1_socket_boundary.py`（新增）、`test_c1_03_admission.py`、`test_c3_02_deadline.py`；`spikes/`、`plugins/` 零差异 |
| 提交分解 | `51abc66` D1-A：3 files，+1054/−16；`4bd4803` D-P0：3 files，+421/−15，**0 src**；`645190e` D-G0 docs：1 file，+456 |
| rootfs canonical | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（5,748 files），与冻结值一致 |
| deps canonical | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（1,061 files），与冻结值一致 |
| stage canonical | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0`（6,628 files），与冻结值一致；49/49 个 `.py` = `e6fde1c`，**旧 stage 不可复用** |
| Podman / OCI | 4.9.3 rootful、crun 1.14.1、cgroup v2/systemd；`podman ps -a` **空** |
| DSH / Node / Adapter | runtime `1cc41d5a…` / `0.2.2-rc.2`；Node `v22.23.2`；adapter `lib/index.js` `2cb42461…`，build-meta `dshLlmVersion=0.2.2-rc.2` |
| 0-Key / Live | key-like env 名 **0/45**；无 `.env`；`bash scripts/run_live.sh` **exit 3**；`LiveGate.inspect(live_requested=True)` = **BLOCKED**（4 个条件不变） |
| 清理 | `podman ps -a` 0；`at-g3d-*` 容器 0；`at-g3d` 进程 0；仓库内 UNIX socket 0；无 pull；无新 image |
| D-G0-01 | **PASS_AT_4BD4803**（原 `PARTIAL/BLOCKED` 是 18:44 时点的真实快照，已由提交合并解决） |
| D-G0-02..05 | 沿用原 **PASS**；本次复算身份/环境并记录未重跑项 |

---

## 1. 为什么需要重基线：冲突窗口与解决

### 1.1 原始时间线（来自原 baseline 的只读记录）

| UTC | 事件 | 结果 |
|---|---|---|
| 18:15:20Z | `d74f2ff`（G3-D0 sign-off + D1 plan） | 原 D-G0 核验起点 |
| 18:23:42Z | 原 D-G0 首次 `git status --porcelain=v1` | **clean（0 行）** |
| 18:33:41Z | 再次检查 | **4 modified + 1 untracked**（并行 D1-A/D-P0 WIP） |
| 18:37:49Z | 原 D-G0 最终环境检查 | 环境 canonical 一致，但工作树仍 dirty |
| 18:43:04Z | `645190e` 提交原 D-G0 文档（约 18:44 交付） | 结论 `D-G0_PARTIAL_BLOCKED_WORKSPACE_CONFLICT`；D-G0-01 PARTIAL/BLOCKED |
| 18:46:09Z | `51abc66` D1-A additive socket/peercred/ready | 并行 WIP 的源码与测试正式提交 |
| 18:51:10Z | `4bd4803` D-P0 digest errata + OCI test portability | 并行 WIP 的测试/文档正式提交 |
| 18:54:36Z | 本重基线开始 | `HEAD=4bd4803` |
| 18:54–19:07Z | 只读复核 | clean、diff、canonical、runtime、live/cleanup 全部复算 |
| 19:00Z 后 | 本文档提交 | append-only 新文件；不改原 baseline |

18:33:41Z 的冲突现场（原文档逐字记录）：

```text
HEAD=d74f2ff7a7477094b0a3ac68ea7d51fa2c30f22d
 M src/autoteacher_m0/bridge/controller.py
 M src/autoteacher_m0/bridge/ipc_server.py
 M tests/integration/g3c/test_c1_03_admission.py
 M tests/integration/g3c/test_c3_02_deadline.py
?? tests/integration/g3d/test_d1_socket_boundary.py
```

### 1.2 解决方式（不是“宣布干净”，而是提交后重新判定）

- 原来的 4 个 modified 文件与 1 个 untracked 文件已分别进入 `51abc66`（D1-A）和 `4bd4803`（D-P0）；二者都在 `4bd4803` 的线性祖先链上，工作树不再持有未提交 WIP。
- 本文件不把 18:44 的 `BLOCKED` 改写成“当时其实通过”。它承认 **在 `d74f2ff` + dirty worktree 上 clean freeze 不成立**，然后把 D-G0-01 的 gate 在 **最终 approved D1 输入 `4bd4803`** 上重新执行。
- 原 baseline 文档未改一个字节（`1411e358…`，见 §3.4）；本文件是追加记录（append-only），不覆盖、不改写旧结论。

---

## 2. Git 现场（clean）

### 2.1 固定输出

```bash
$ git status --porcelain -uall
# 无输出；exit 0；0 行 / 0 字节

$ git rev-parse HEAD
4bd48037d98e081c8fb96a246f3fbf3cf60eb38b

$ git rev-parse HEAD^{tree}
e5b91a2bce19ac83f4cdf05df44dec1d71b1e627

$ git rev-parse origin/main
fff36232687afb779befb49fb6e2a10cedbcb7fd

$ git rev-list --count origin/main..HEAD
5

$ git rev-list --count b2f6af0..HEAD
13
```

`git remote -v`：

```text
origin  git@github.com:ygmldr/Autonomouse-Teacher.git (fetch)
origin  git@github.com:ygmldr/Autonomouse-Teacher.git (push)
```

`git log -5`：

```text
4bd4803 2026-11-17T18:51:10Z fix: D-P0 digest errata and OCI test portability (no-key)
51abc66 2026-11-17T18:46:09Z feat: D1-A additive socket mode, peercred and ready boundary (no-key)
645190e 2026-11-17T18:43:04Z docs: add D-G0 baseline and environment freeze (no-key)
d74f2ff 2026-11-17T18:15:20Z docs: add G3-D0 sign-off and D1 implementation plan (no-key)
1274280 2026-11-17T18:15:15Z docs: archive G3-D dual-principal plan and matrix (verbatim)
```

父链：`4bd4803 → 51abc66 → 645190e → d74f2ff → 1274280`；`b2f6af0` 仍是 `HEAD` 的祖先（`git merge-base --is-ancestor` exit 0）。

### 2.2 无进行中的 Git/并行操作

以下均不存在（检查时无输出）：

- `.git/MERGE_HEAD`、`.git/CHERRY_PICK_HEAD`、`.git/REVERT_HEAD`
- `.git/rebase-merge`、`.git/rebase-apply`
- `.git/index.lock`
- 额外 `git worktree`：`git worktree list` 只有 `/root/Autonomous Teacher 4bd4803 [main]`

### 2.3 ignored 残留（可忽略，但记录）

`git status --porcelain --ignored=matching -uall` 共 **24** 条，全部是 gitignored 的缓存/产物，不是未跟踪源码：

```text
.pytest_cache/  .ruff_cache/  artifacts/
plugins/offline-fixture/node_modules/
plugins/runtime-budget-guard/lib/
plugins/runtime-budget-guard/node_modules/
plugins/skill-lookup/.sandbox-stage/
plugins/skill-lookup/node_modules/
scripts/__pycache__/  scripts/security/__pycache__/
spikes/g3b-trusted-bridge/fake/__pycache__/
spikes/g3b-trusted-bridge/node_modules/
spikes/g3b-trusted-bridge/run/__pycache__/
spikes/g3b-trusted-bridge/test/__pycache__/
src/autoteacher_m0/__pycache__/
src/autoteacher_m0/accounting/__pycache__/
src/autoteacher_m0/bridge/__pycache__/
src/autoteacher_m0/security/__pycache__/
tests/integration/budget_bridge/__pycache__/
tests/integration/g2_closure/__pycache__/
tests/integration/g3_bridge/__pycache__/
tests/integration/sandbox/__pycache__/
tests/unit/accounting/__pycache__/
tests/unit/security/__pycache__/
```

`artifacts/` 是历次证据/产物目录（gitignored）；`node_modules/`、`lib/`、`.sandbox-stage/` 是插件构建产物；`__pycache__/` 是 Python 缓存。它们不进入 Git 基线，也不改变产品源码身份。

---

## 3. 变更审计：`b2f6af0 → 4bd4803`

### 3.1 产品/测试面（任务指定路径）

```bash
git diff --stat b2f6af0..HEAD -- src tests spikes plugins
```

```text
 src/autoteacher_m0/bridge/controller.py          |  37 +-
 src/autoteacher_m0/bridge/ipc_server.py          | 230 ++++++-
 tests/integration/g3c/test_c1_03_admission.py    |  71 +-
 tests/integration/g3c/test_c3_02_deadline.py     |  37 +-
 tests/integration/g3d/test_d1_socket_boundary.py | 803 +++++++++++++++++++++++
 5 files changed, 1147 insertions(+), 31 deletions(-)
```

`--name-status`：

```text
M  src/autoteacher_m0/bridge/controller.py
M  src/autoteacher_m0/bridge/ipc_server.py
M  tests/integration/g3c/test_c1_03_admission.py
M  tests/integration/g3c/test_c3_02_deadline.py
A  tests/integration/g3d/test_d1_socket_boundary.py
```

逐文件 numstat：

| 文件 | +/− | 归属 |
|---|---|---|
| `src/autoteacher_m0/bridge/controller.py` | +32 / −5 | D1-A `51abc66` |
| `src/autoteacher_m0/bridge/ipc_server.py` | +219 / −11 | D1-A `51abc66` |
| `tests/integration/g3d/test_d1_socket_boundary.py` | +803 / −0 | D1-A `51abc66`（新增） |
| `tests/integration/g3c/test_c1_03_admission.py` | +68 / −3 | D-P0 `4bd4803` |
| `tests/integration/g3c/test_c3_02_deadline.py` | +25 / −12 | D-P0 `4bd4803` |

`spikes/`、`plugins/` **零差异**；没有删除、没有现有文件 mode 变化、没有 binary diff、没有 submodule 变化。`git diff --summary` 只显示新增文件（含 2 个 100755 的 `scripts/g3c` 脚本，见 §3.2）。

### 3.2 提交分解（把“已批准输入”与“D-G0 之前的历史”分开）

**A. `b2f6af0..645190e`（16 files，+4539/−171；D-G0 基线时已包含）**

- 13 个 `docs/`：G3-C 复审/errata/矩阵、G3-D0 sign-off、D1 plan、Dual-Principal plan/START_HERE/矩阵、原 D-G0 baseline。
- 3 个 `scripts/g3c/`：`build_packet.py`、`coldstart_overlay_probe.py`、`reproduce-coldstart-with-src-overlay.sh`；来自 16:23–17:27Z 的 G3-C packet 修正提交（`18c8290`、`7b979d9`、`fff3623`），在 `645190e` 时已冻结，不是 D1-A/D-P0 的新改动。

**B. `645190e..HEAD`（6 files，+1475/−31；原 baseline 之后真正的新增）**

```text
A  docs/M0_G3D_D_P0_ERRATA.md
M  src/autoteacher_m0/bridge/controller.py
M  src/autoteacher_m0/bridge/ipc_server.py
M  tests/integration/g3c/test_c1_03_admission.py
M  tests/integration/g3c/test_c3_02_deadline.py
A  tests/integration/g3d/test_d1_socket_boundary.py
```

**C. 两个输入提交的精确统计**

| 提交 | 内容 | 文件 | 统计 | `src/` 改动 |
|---|---|---|---|---|
| `51abc66` D1-A | additive socket mode / peercred / ready | 3（2 src + 1 新测试） | +1054 / −16 | 2 files |
| `4bd4803` D-P0 | digest errata + OCI test portability | 3（1 docs + 2 tests） | +421 / −15 | **0** |

结论：`b2f6af0..HEAD` 全路径共 22 files，+6014/−202，按顶层目录为 **14 docs + 3 scripts + 2 src + 3 tests**；除上述已解释的 D1-A/D-P0/ G3-C 归档/ D-G0 文档外，**无其他产品改动**。

### 3.3 关键 blob / 内容 SHA（HEAD = `4bd4803`）

| 文件 | blob sha（HEAD） | SHA-256（工作树） | 相对 `b2f6af0` |
|---|---|---|---|
| `src/autoteacher_m0/bridge/controller.py` | `1a2592e509cf4d7e02a826c518bb59698ca13a7c` | `2ea1a962a498ff815e0c78c62e550104336623d5d2fe5c8ba33fdd3c303368b8` | 改变（D1-A） |
| `src/autoteacher_m0/bridge/ipc_server.py` | `08888e4f987a65ba972cb802ddb19149fb781a69` | `a257627b53f481d56fc83057e323a5d7ad2e6fe6d324a58050494a5c2588f851` | 改变（D1-A） |
| `src/autoteacher_m0/bridge/attempts.py` | `d54ce4a9b93836934b8a9a788f41b46993f1c6cb` | `ccd008bd55bda8d344152856912dbde9dfe1e29d5accb53973a938e1e4b59795` | 未变 |
| `src/autoteacher_m0/bridge/admission.py` | `273c2676cdcdf3683bacaca807a21911ac89d7a9` | `174358c8b27737037f4b98f9087ee62156506276f319d534959acd162d58b984` | 未变 |
| `src/autoteacher_m0/accounting/broker.py` | `6b3813c0c3edac5f43be5fe09ae5bed3e09190ea` | `0016304a1181677beae76072e639ddfc7988042c46a6400f1ca3dfe4b8157fa6` | 未变 |
| `src/autoteacher_m0/accounting/ledger.py` | `aa5e7c11688597d64179b46bd2ad6cf64ac927dc` | `15b3cf9d42eebf2c5758d180c8303dacaac1d4e9d3bbf0776f9219642e9ead97` | 未变 |
| `spikes/g3b-trusted-bridge/fake/fake_provider.py` | `11f1541292bf79b0f5409322b0bfea183c1c384c` | `1a775539bf82994438271d656281377aee4ea40e477c69b1d066bf93f09ac159` | 未变 |
| `spikes/g3b-trusted-bridge/src/index.ts` | `e82a497ef33f28c4b8756a7d55fb2a381c62ca4f` | `b0f0e8a7ec6dd3a2f5fe417d7131f43fdc594e540b65dd0a01d164eb5b3e0dbf` | 未变 |

测试文件（HEAD）：

| 文件 | blob sha | SHA-256 |
|---|---|---|
| `tests/integration/g3d/test_d1_socket_boundary.py` | `9a45d9b0336b144e5413c967e854369ed50d6a83` | `678d564587de3a725c8d344a8a4fd86442aa18b12f10728b684567395c617e25` |
| `tests/integration/g3c/test_c1_03_admission.py` | `395b78d91db33da34d6ae19bce2a2687c069d838` | `98cc6084a7559c3429f7387ae365e09b83e092175aa8bdd45ce56e0f1710d30a` |
| `tests/integration/g3c/test_c3_02_deadline.py` | `b50090505aac4d4478bfedfc955ad5b89cf52933` | `10bce8415cfd73dffa1a0799e8ccff5896ab06ed3fc11693c0a10c5944a8bd9e` |

> `b2f6af0` 的 `controller.py` / `ipc_server.py` blob 分别为 `4baa85f7…` / `790ae930…`；其余 6 个关键 blob 与 HEAD 逐一相同。

### 3.4 受保护/治理文件

| 文件 | blob sha（HEAD） | SHA-256 | 状态 |
|---|---|---|---|
| `AGENTS.md` | `fdab235ce5aa2467051df9d246d95efbe7eb59b1` | `1d97a7e369a3831267516a968070ee5bca0950350c350e2ebbd9eed91cf30133` | `b2f6af0..HEAD` 无差异 |
| `scripts/run_live.sh` | `dd0814e165eea620164e7c6b372abbdc014e972a` | `a8a2753fd6b6b096b66adecfbdde044b42c6c4a26630c24f0fc269b1fe5f957a` | 无差异 |
| `docs/M0_G3D_G0_BASELINE.md` | `50dbd5aeef765758073b1eea12b265a3188a58ca` | `1411e3587b7820a580b8cc6bda7b1a8de0e99733bb7d7368123c41b7e7b02562` | `645190e..HEAD` 无差异（提交后字节未动） |
| `docs/M0_G3D_D0_SIGNOFF.md` | — | `ae87dfa53cc5f8cdb39b2d4dd6d995f1e0eb4eeb115ecebb2527760450a5bbd6` | 冻结输入内，未在本轮修改 |
| `docs/M0_G3D_D1_IMPLEMENTATION_PLAN.md` | — | `f024bc0e88f3ef5b82886943d21b66d2709fdd71cd24c1bea27998119eb5b3ce` | 冻结输入内，未在本轮修改 |
| `docs/M0_G3D_D_P0_ERRATA.md` | — | `2ffda7ff1ee253a897094fdf41ed6fb85a627b8567f4729c94cdc33b3b0fa98f` | 冻结输入内，未在本轮修改 |

更强的一条：`git diff --name-status b2f6af0..HEAD` 的 22 个路径全部可归入 §3.2 的三类（G3-C 归档/ D-G0 docs、D1-A、D-P0），没有无法解释的 tracked 文件变化。

---

## 4. D-G0-01 判定：`PASS_AT_4BD4803`

### 4.1 判定条件逐项

| 条件 | 现场 | 判定 |
|---|---|---|
| 记录实际 HEAD | `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`（父 `51abc66`） | PASS |
| 工作树 clean | `git status --porcelain -uall` 0 行 / 0 字节，exit 0 | PASS |
| 无未跟踪文件 | `-uall` 无 `??`；24 条均为 ignored 缓存/产物（§2.3） | PASS |
| 无进行中并行改动 | 无 merge/rebase/cherry-pick/revert、无 `index.lock`、只有 main 一个 worktree | PASS |
| 产品 drift 可解释 | `src/tests/spikes/plugins` 只有 5 文件：D1-A 2 src + 1 测试，D-P0 2 测试；`spikes/plugins` 0 | PASS |
| 产品源码 = 批准输入 | `git diff 51abc66..HEAD -- src` 为空；D-P0 无 `src` 改动 | PASS |
| 原 baseline 不被改写 | `645190e..HEAD -- docs/M0_G3D_G0_BASELINE.md` 为空；文件 sha256 `1411e358…` | PASS |
| 受保护文件未被未审修改 | AGENTS.md、`scripts/run_live.sh` 相对 `b2f6af0` 无差异（§3.4） | PASS |

### 4.2 状态语义

- **D-G0-01 = `PASS_AT_4BD4803`**：在 2026-11-17 18:54–19:07Z 的最终 approved D1 输入上，Git clean baseline source 与受保护文件条件真实成立。
- 原 `D-G0_PARTIAL_BLOCKED_WORKSPACE_CONFLICT` 仍是 18:33–18:44Z 的 **真实快照**：当时 `HEAD=d74f2ff` 且 worktree 持有 4 modified + 1 untracked，因此 clean freeze 不成立。该历史结论不改写。
- 这不是“把 dirty worktree 判成干净”，而是“并行工作已提交、HEAD 已前进到 `4bd4803` 后，重新在 clean 输入上判定”。

### 4.3 矩阵填表交接（本文件不直接改 CSV）

按 G3-D 任务书 §12，历史 CSV 不就地覆写。建议 Lead/Evidence Owner 将 D-G0-01 行填为：

| 字段 | 建议值 |
|---|---|
| `status` | `PASS_AT_4BD4803` |
| `observed` | clean 0；HEAD `4bd4803`；产品 drift = D1-A 2 src + 1 test，D-P0 2 tests/0 src；rootfs/deps/stage canonical 一致 |
| `command_argv` | `git status --porcelain -uall; git diff --stat b2f6af0..HEAD -- src tests spikes plugins; ...`（见 §9） |
| `code_sha` | `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b` |
| `stage_sha` | 不适用（旧 stage `fcdb0de4…` 不是本输入构建物；D1 必须新建） |
| `evidence_paths` | `docs/M0_G3D_G0_BASELINE.md`、`docs/M0_G3D_G0_REBASELINE.md`、`artifacts/g3d/`（原环境证据） |

D-G0-02..05 的原 PASS 不在本次重写；如矩阵需要统一 `code_sha`，应同时标注其环境证据来自 `d74f2ff`/`b2f6af0` 时点，不能伪装成 `4bd4803` 重新执行。

---

## 5. D-G0-02..05：沿用原 PASS + 本次现场复核

| Case | 原判定 | 本次复核（只读） | 维持 |
|---|---|---|---|
| **D-G0-02** Podman rootful / userns readiness | PASS | Podman `4.9.3` rootful=false(rootless)；crun `1.14.1`；cgroup `v2` / `systemd`；seccomp enabled；LXC；`uid_map=0 100000 65536`；`/etc/subuid`、`/etc/subgid` 均 0 字节；`gid 2000` 空闲。原 P2/P3 的 uid 65534 / peercred / 独立 namespace 证据未重跑。 | **PASS** |
| **D-G0-03** canonical rootfs/deps/stage | PASS（身份）/ 旧 stage 警告 | rootfs `25491e45…`、deps `e07729d7…`、stage `fcdb0de4…` 均与冻结值一致；stage 49/49 `.py` = `e6fde1c`；PR1 标记 0；只有 `attempts.py`、`controller.py` 与 `b2f6af0` 不同。旧 stage 仍为 pre-PR1，**D1 禁止复用**。 | **PASS（身份）** |
| **D-G0-04** 0 Key / no network / LiveGate | PASS | key-like env 名 **0/45**；无 `.env`（仅 `.env.example`，sha256 `440251f4…`）；`run_live.sh` exit **3**；`LiveGate` = **BLOCKED**（4 reasons 不变）；`src/` 严格 import/调用检查只有 `AF_UNIX`；未 pull、未 fetch、未外部 HTTP。 | **PASS** |
| **D-G0-05** DSH/Node/Adapter lock | PASS | DSH `1cc41d5a…` / 182,717,632 B / `0.2.2-rc.2`（exit 0）；系统 `/usr/bin/dsh` `80112efe…` / `0.2.1-rc.2`（不得替代）；Node `v22.23.2`（host/rootfs 同为 `3517c2df…`）；adapter `lib/index.js` `2cb42461…` / 20,321 B；build-meta 一致。 | **PASS** |

**总体**：`D-G0_REBASELINE_PASS_AT_4BD4803`。D-G0-01 在最终输入上 PASS；D-G0-02..05 原 PASS 维持，且其关键身份量在本轮复算一致。注意 D-G0-02/04 的容器面（UID map 实测、`--network none` 实测、cgroup 限制实测）本次**未重跑**，见 §6.6。

---

## 6. 环境 / Stage / Runtime 复核

### 6.1 Canonical（只读复算）

命令：

```bash
tar -C <path> --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - . | sha256sum
```

| 对象 | canonical（18:55Z / 18:59Z / 19:07Z 三次一致） | 文件数 | 结论 |
|---|---|---|---|
| `artifacts/security/rootfs` | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` | 5,748 | 与冻结值一致，NO_DRIFT |
| `artifacts/foundation/deps` | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | 1,061 | 与冻结值一致，NO_DRIFT |
| `artifacts/g3c/stage` | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0` | 6,628 | 与冻结值一致，NO_DRIFT |

无 rootfs 空目录漂移、无并发容器改写；三次复算之间未出现 hash 变化。

### 6.2 旧 G3-C stage 身份（存在，但不可复用）

| 项 | 值 |
|---|---|
| stage 路径 | `artifacts/g3c/stage` |
| `stage/src` 文件数 | 86（49 个 `.py`） |
| 49 个 `.py` vs `e6fde1c` | **49/49 相等** |
| 49 个 `.py` vs `b2f6af0` | 47/49 相等；仅 2 个不同 |
| 不同文件 | `bridge/attempts.py`：stage `33017e75…` vs `b2f6af0`/HEAD `ccd008bd…`；`bridge/controller.py`：stage `8d7e2041…` vs `b2f6af0` `cbec21f7…` / HEAD `2ea1a962…` |
| PR1 标记 | `INIT_BUSY_TIMEOUT_MS`、`def _initialize`、`CONTROLLER_SINGLETON_LOCKED` 在 stage 中 **0 命中** |
| 结论 | stage 是 `e6fde1c` pre-PR1 批次；D1 必须从 `4bd4803` 新建 stage，**不得**挂载/复制 `stage/src`、旧 `run_c3`、旧 fake/controller |

本次没有创建任何 D1 stage；`artifacts/g3d/` 下只有环境/证据目录，没有新 stage。

### 6.3 DSH runtime / Node / Adapter

| 项 | 值 |
|---|---|
| DSH runtime 路径 | `artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64` |
| SHA-256 / size | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4` / 182,717,632 B |
| `--version` | `0.2.2-rc.2`（exit 0；仅版本自报，不加载插件/不访问网络） |
| 系统 `/usr/bin/dsh` | `80112efe368efb1a39720c7ada0af00442e5131fb2744edaaff8a3e8bb499e6f` / `0.2.1-rc.2`，**不得替代** |
| Node | host `v22.23.2`，`/usr/bin/node` 与 `rootfs/usr/bin/node` 均 `3517c2df0b2f8cd7f422b4b8450ef81c6889f08eb03e281d6de9079b15e6a327` |
| adapter build-meta | `createdUtc=2026-11-17T13:40:24.374Z`；`node=v22.23.2`；`typescript=5.9.3`；`dshLlmVersion=0.2.2-rc.2`；`synthetic=true` |
| adapter `lib/index.js` | `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba` / 20,321 B |
| adapter `lib/index.d.ts` | `d72067d3de7ef102cd92247ed93d2a1c6bb5c1df9735770692d202469caa2d78` / 1,076 B |
| adapter 输入源交叉核对 | `inputSourceSha256=b0f0e8a7…` 与 `spikes/g3b-trusted-bridge/src/index.ts` 的 SHA-256 完全一致 |

### 6.4 0-Key / LiveGate / 网络面

当前 shell：

```text
env 变量名总数 = 45
key-like 名称（KEY/TOKEN/SECRET/CREDENTIAL/PASSWORD/AUTH/API）= 0
```

未打印任何变量值。`.env`：**0 个**；仅 `.env.example`（sha256 `440251f47b22b8e61f128b28efd0d338fd74e4c9b65306be25023258b3cf64dd`）。

`bash scripts/run_live.sh`：

```text
BLOCKED SECURITY_BLOCKED: no independent authorization/controller boundary.
Review docs/M0_RUNBOOK.md; a Markdown approval is not an execution capability.
exit=3
```

`LiveGate().inspect(live_requested=True)`：

```json
{
  "status": "BLOCKED",
  "reasons": [
    "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED",
    "BASELINE_EVIDENCE_MISSING",
    "ACTUAL_TOOL_REGISTRY_NOT_APPROVED",
    "SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED"
  ],
  "external_boundary_deployed": false
}
```

静态网络面：`src/` 中严格匹配 `import (requests|httpx|aiohttp|http.client|urllib)` / `from (requests|httpx|aiohttp|http|urllib)` / `socket.AF_INET|AF_INET6` / `create_connection` 的结果为 **0**；bridge 只使用 `socket.AF_UNIX`。未执行 `curl`/`wget`/`git fetch`/`podman pull`。本地 image 仍为原来的 4 个 `repo:tag`（2 个唯一 ID），无新 image。

### 6.5 清理 / 无残余

| 检查 | 结果 |
|---|---|
| `podman ps -a` | 0 个容器（只有表头，exit 0） |
| `podman ps -a --filter name=at-g3d-` | 0 |
| `at-g3d` 进程 | 0（`ps -eo pid,args` 过滤） |
| 仓库内 UNIX socket（`find . -type s`） | **0** |
| `artifacts/g3d/runs/**/ipc` / `*.sock` | 无 |
| `/tmp/*.sock` | 无；`/run/podman`、`/run/tailscale`、`/run/cups` 是系统 socket，与本项目无关 |
| canonical 前后 | 三次一致（§6.1） |
| 新 image / pull | 无 |

### 6.6 本次未重跑（明确边界）

- 未重跑双容器 UID map / `SO_PEERCRED` / `--network none` / cgroup 资源探针；这些结论来自原 D-G0 的 18:27–18:32Z 证据（`artifacts/g3d/`），本文件只复核了**静态环境身份**。
- 未运行 D1-A/D-P0/G3-C 测试套件；本文件引用 Lead 已审计结果（g3d 53 + g3c 110 + g3_bridge 31 + gates 14 = 208 passed，ruff 通过；D-P0 fixed OCI full 775 passed/0 failed/1 skipped），**不把转述当成本次新执行**。
- 未运行真实 DSH Echo/Tool/Resume、D2 攻击、D3 回归；不属于 D-G0 重基线。

---

## 7. D1 输入基线声明（authoritative）

### 7.1 产品源码 SHA

- **产品源码 SHA = `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`**。
- `src/` 与 D1-A `51abc66` **完全相同**（`git diff --stat 51abc66..HEAD -- src` 为空）。
- D-P0 `4bd4803` **只有 tests/docs**（3 files：`M0_G3D_D_P0_ERRATA.md` + 2 个 G3-C 测试），无 `src` 改动。
- 因此 D1 不得以 `b2f6af0` 为产品源（它缺少已批准的 D1-A additive API），也不得把 `d74f2ff` 的旧 worktree 当输入。

### 7.2 批准输入链

| 输入 | 提交 | 内容 | 作用 |
|---|---|---|---|
| D1-A | `51abc66` | additive socket mode / peercred / ready（3 files，+1054/−16） | D1 产品源码 |
| D-P0 | `4bd4803` | digest errata + OCI test portability（3 files，+421/−15，0 src） | 测试/文档补丁 |
| D-G0 docs | `645190e` | 原 D-G0 baseline（1 file，+456） | 历史快照，本文件不修改 |
| 重基线 | 本文件 | append-only 复核 | D-G0-01 在 `4bd4803` 上 PASS |

### 7.3 D1-A API（已批准，HEAD 实测）

`BridgeServer.__init__(... , *, socket_mode: int = 0o600, socket_gid: int | None = None, expected_peer_uid: int | None = None, on_ready: Callable[[], None] | None = None)`：

| 参数 | 默认 | 允许 / 行为 |
|---|---|---|
| `socket_mode` | `0o600` | 只允许 `{0o600, 0o660}`（`_ALLOWED_SOCKET_MODES`）；拒绝 `0666`、`0770`、`0640`、`0400`、bool/float/str；默认保持旧 0600 |
| `socket_gid` | `None` | 非负 int；仅当 mode 含 group 位（`& 0o060`）时允许；非 None 才 `chown`，D1 隔离模式依赖 host 预创建 `2750 root:2000` setgid 目录继承 gid，不依赖 `CAP_CHOWN` |
| `expected_peer_uid` | `None` | 非负 int；配置时要求 `SO_PEERCRED` 存在，否则构造失败；每个 accept 在读取首帧/发 ack 前校验，不匹配即关闭；PID 只作证据，不作身份 |
| `on_ready` | `None` | 必须 callable；在 `listen()` 与权限校验通过后**恰好一次**；boundary 拒绝/启动失败时不调用 |

`controller.main(argv=None, *, on_ready=None)` 支持可选配置键 `socket_mode`/`socket_gid`/`expected_peer_uid`，未知键/非法值 `CONFIG_INVALID`；默认调用保持 0600/root/无 peer 校验。stale-socket 清理只针对配置路径，`lstat` 校验类型/owner/symlink，遇到 symlink、普通文件或 foreign owner 拒绝而非盲删。

历史文档口径提醒：`docs/M0_G3D_D0_SIGNOFF.md` 与 `docs/M0_G3D_D1_IMPLEMENTATION_PLAN.md` 的部分旧文仍写 `0770`；**最终执行方案（Dual-Principal plan）与 HEAD 实现/测试一致采用 `0660`**。D1 必须以 `0660` 为准，不得传 `0770`（会被构造器拒绝）。见 §8 残余 4。

### 7.4 D1 Stage 规则（硬门）

1. D1 **必须从 `4bd4803` 新建** `{trusted,candidate}` Stage；两容器产品模块来自同一批准 SHA。
2. **禁止**复用 `artifacts/g3c/stage/src`（49/49 是 `e6fde1c` pre-PR1）、旧 `run_c3`、旧 fake/controller 副本；旧 Packet R5 命令不得原样使用。
3. 新 Stage 必须带 Manifest：源 blob、构建产物 hash、Runtime 版本（`0.2.2-rc.2`）、rootfs/deps hash。
4. 必须用 `inspect.getfile` + 实际文件 SHA 对照 `git show 4bd4803:<path>` 证明加载的是批准源码；仅 `git rev-parse`/Packet hash 不算。
5. 目标 Runner 必须重跑 UID map / namespace / peercred / `--network none` / cgroup；本机 `CAN_ISOLATE` 不可外推。
6. 每 run 独立目录/容器名；结束 `podman ps -a` 空、无 `at-g3d-*`、无 socket 残留；共享 rootfs 的 canonical 重算必须串行。

### 7.5 D1 启动前 checklist

- [x] HEAD clean = `4bd4803`，产品源码 = 批准输入（本文件）
- [x] D1-A additive API 已在 HEAD（0600 默认 / 0660 隔离、socket_gid、expected_peer_uid、on_ready）
- [x] D-P0 无 `src` 改动
- [x] rootfs/deps/stage canonical 与冻结值一致，旧 stage 身份可证明
- [x] 0 Key / LiveGate BLOCKED / run_live exit 3
- [ ] D1 新 Stage + Manifest（待 D1 执行）
- [ ] D1 `inspect.getfile` 加载证明（待 D1 执行）
- [ ] D1 目标 Runner 环境重跑（待 D1 执行）
- [ ] D1 清理/无残余复核（待 D1 执行）

---

## 8. 残余与已知限制

1. **旧 G3-C stage 不得复用**：`artifacts/g3c/stage` 是 `e6fde1c` pre-PR1（49/49），`attempts.py` 为旧 `journal_mode=WAL` 批次；D1 必须从 `4bd4803` 新建。
2. **D-P0 host full 仍有 2 个既有环境失败**（不是 D-P0 回归）：
   - `tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text`：宿主 `config/dsh/*` 非只读；OCI stage 中由 0444 满足。
   - `tests/integration/sandbox/test_live_controller_no_key.py::test_all_live_entrypoints_remain_blocked`：测试硬编码 `PYTHONPATH=/project/src:/deps`，宿主无 `/project`。
   - 因此 **host 不称全绿**；D-P0 的有效证据是固定 OCI full **775 passed / 0 failed / 1 skipped**（exit 0），host full 为 773 passed / 2 failed / 1 skipped（exit 1）。
3. **1 个既有 skip**：固定 OCI full 的 skip 是外部 probe mount 既有 skip，不是失败，也不代表全部测试都执行。
4. **`0770` 文档口径残留**：D0 sign-off/D1 plan 旧文写 0770，最终执行方案与 HEAD 实现为 0600/0660。D1 以 0660 为准；建议 docs owner 在 D1 文档冻结时更新旧文，不能靠改代码放宽到 0770。此项不阻塞 D-G0 重基线，但阻塞“照旧 plan 直接传 0770”的做法。
5. **rootfs 是共享可写目录**：历史上面临并行容器瞬时改 hash 的竞争；D1 必须独立 run 目录并串行重算 canonical。
6. **本次未重跑容器探针**：D-G0-02/04 的 UID map/peercred/network/cgroup 证据来自原 18:27–18:32Z；本文件只复核静态环境身份，不能把“未重跑”说成“新执行”。
7. **未建 D1 Stage、未跑真实 DSH**：D1/D2/D3 均未开始；本文件不提供 D1 测试结果。
8. **LiveGate 仍 BLOCKED**：`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 不变；本文件不授予 Live/G4/G5。
9. **本地领先远端 5 个提交**：未 push、未 amend；`origin/main` 仍停在 `fff3623`。这是本地历史状态，不是 D1 阻塞项。
10. **ignored 残留 24 条**：缓存/构建产物/证据目录；Git 视角 clean，但它们仍是宿主磁盘状态，清理策略由 D1 runbook 负责。
11. **D-G0-01 PASS 仅对 `4bd4803` 成立**：后续任何新提交、未提交改动、额外 worktree 或 stage 修改都会使该判定失效，必须重新 preflight。

---

## 9. 证据索引（本次只读命令）

| 组 | 命令（摘要） | 结果 |
|---|---|---|
| Git clean | `git status --porcelain -uall` | exit 0，0 行/0 字节 |
| Git 身份 | `git rev-parse HEAD`、`HEAD^{tree}`、`git log -5`、`git remote -v`、`git branch --show-current` | `4bd4803` / `e5b91a2b…` / 见 §2.1 |
| Git 完整性 | `git merge-base --is-ancestor b2f6af0 HEAD`、`git rev-list --count origin/main..HEAD` | exit 0 / 5 |
| 进行中操作 | `.git/{MERGE_HEAD,CHERRY_PICK_HEAD,REVERT_HEAD,rebase-*,index.lock}`、`git worktree list` | 均不存在 / 仅 main |
| ignored | `git status --porcelain --ignored=matching -uall` | 24 条，均为 ignored |
| 产品 diff | `git diff --stat/--name-status/--numstat b2f6af0..HEAD -- src tests spikes plugins` | 5 files，+1147/−31 |
| 全路径 diff | `git diff --stat b2f6af0..HEAD`；`git diff --summary` | 22 files，+6014/−202；无 mode/binary/submodule |
| 提交分解 | `git diff --stat b2f6af0..645190e`；`git diff --stat 645190e..HEAD`；`git show --stat 51abc66 4bd4803` | 见 §3.2 |
| blob | `git rev-parse <sha>:<path>`、`sha256sum <path>` | 见 §3.3 |
| 原 baseline 未改 | `git diff 645190e..HEAD -- docs/M0_G3D_G0_BASELINE.md`；`sha256sum` | 空 / `1411e358…` |
| canonical | 三次 `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner … \| sha256sum` | §6.1，三次一致 |
| stage | 49 个 `.py` 逐个 `sha256sum` vs `git show e6fde1c:<path>`；PR1 marker grep | 49/49，0 marker |
| Podman | `podman --version`、`crun --version`、`podman info --format json`、`podman ps -a` | 4.9.3 / 1.14.1 / rootful / 0 容器 |
| Runtime | `sha256sum`、`<runtime> --version` | `1cc41d5a…` / `0.2.2-rc.2` |
| Node | `node --version`、host/rootfs `sha256sum` | `v22.23.2` / `3517c2df…` |
| Adapter | `sha256sum lib/index.js`、`cat build-meta.json` | `2cb42461…` / 见 §6.3 |
| Key | `env \| cut -d= -f1`（只打印名称）、`find . -name .env` | 45 名称 / 0 key-like / 0 `.env` |
| Live | `bash scripts/run_live.sh`；`LiveGate().inspect(live_requested=True)` | exit 3；BLOCKED |
| 网络静态 | `grep -RInE "import (requests|httpx|aiohttp|http\.client|urllib)|from (requests|httpx|aiohttp|http|urllib)|socket\.AF_INET|AF_INET6|create_connection" src` | 0 |
| 清理 | `podman ps -a`、`podman ps -a --filter name=at-g3d-`、`ps`、`find . -type s` | 0 / 0 / 0 / 0 |
| 镜像 | `podman images --format …` | 4 个 repo:tag / 2 个唯一 ID，无新 pull |

说明：本次只读复核没有另建 `artifacts/commands.jsonl`；关键命令与输出已内联在本文件，便于逐项重放。原 D-G0 的 `artifacts/g3d/commands.jsonl`（56 条）与 D-P0 的 `artifacts/g3d/d-p0/` 保持原样。

---

## 10. 声明与非主张

1. 本文档是 **D-G0 重基线（append-only）**，不是 D1 实施、不是 D2/D3、不是 G3-D PASS，也不是 Live/GO。
2. 原 `docs/M0_G3D_G0_BASELINE.md` 的 `PARTIAL/BLOCKED` 仍是 18:33–18:44Z 的真实历史结论，本文档没有修改其字节，也没有把历史 dirty 状态“追溯洗白”。
3. `D-G0-01 = PASS_AT_4BD4803` 仅表示：在 `4bd4803` clean worktree 上，产品 drift 已全部解释、受保护文件未被未审修改、原 baseline 未被改写。它不表示 `d74f2ff` 在 18:33Z 是 clean。
4. D-G0-02..05 沿用原 PASS；本次只读复核了静态身份/环境，未重跑容器面探针，未重跑测试套件。
5. 真实 Key、真实模型、Provider HTTP、`podman pull`、LiveGate 解锁、G4/G5 均未发生，也不由本文档授权。
6. D1 必须重新核验 HEAD/产品 SHA/Stage/环境，并在 clean/隔离的 worktree 中进行；`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立。
