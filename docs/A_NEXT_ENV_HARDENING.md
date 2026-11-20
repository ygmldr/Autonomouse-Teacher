# A-NEXT 环境防污染与静态校验工具（OCI/rootfs/CI）

- **文档 ID**：`A-NEXT-ENV-HARDENING-v1`
- **适用范围**：G4-R / G4-H0 no-key 收尾期间的 OCI/容器运行、冻结 rootfs 保护、Packet/证据批次纪律、CI 分支与受保护文件静态校验。
- **性质**：**工程卫生工具与使用约定**，不是安全边界、不是授权、不替代 Independent Reviewer、不改变 `LiveGate=BLOCKED` / `G4-H=NOT_AUTHORIZED` / `G5=BLOCKED` 等状态常量。
- **硬约束**：仅本地执行、0 真实 Key/Provider/外部 HTTP/Live；工具**只读**冻结 rootfs（只做 tar 规范化哈希、`stat`、`findmnt`），**绝不写冻结路径**；测试只用临时目录与合成 hash。

## 0. 背景（为什么需要这些工具）

2026-11-20 G4-R 阶段，多次 `podman run --rootfs <冻结 rootfs>` 在 291 MB 冻结 rootfs 内创建空挂载点目录，导致 canonical hash 漂移：

```text
16:43:53  25491e45...   （冻结值）
16:52-53  0340fb78...   （漂移窗口 #1）
16:53:34  25491e45...   （清理恢复）
16:55-59  a6737150... → e1a8fcf9...   （漂移窗口 #2：evidence/fixtures/plugin/skill/var/var-tmp + probe/*）
17:01:49  25491e45...   （精确清理恢复；最终 Stage 在此后的 canonical 状态构建）
```

结论：**冻结 rootfs 只能只读引用；所有 OCI/容器运行必须使用可写副本**；运行前后必须对比 frozen rootfs SHA，漂移即 STOP。本工具把该约定变为可执行检查。

## 1. 工具清单

| 脚本 | 作用 | 是否写文件 |
|---|---|---|
| `scripts/a_next/oci_guard.py` | OCI/容器运行守卫：冻结 rootfs 检测、输出目录预检、T0/T1 canonical 对比、单 writer 锁、env 脱敏、证据报告 | 只写 `--evidence-dir`/`--output-dir`（新建、独占）；对 frozen/rootfs 只读 |
| `scripts/a_next/rootfs_guard.py` | 冻结 rootfs 物理防写检查：canonical SHA、组/其他可写位、测试 uid 可写、只读挂载状态、可执行验证命令 | 只读；`--json-out` 仅写指定报告路径 |
| `scripts/a_next/ci_guard.py` | CI 静态校验：分支来源（main vs work/g4r）、受保护文件变动清单、H0 cherry-pick/merge 回归提示、未授权合并 | 只读 git；`--json-out` 仅写指定报告路径 |
| `scripts/a_next/_common.py` | 公共只读工具（canonical hash、frozen 检测、env 脱敏、git 封装） | 无 |

所有脚本均为 **stdlib-only**，可用 `/root/Autonomous Teacher/.venv/bin/python` 或系统 python3.11 直接运行。

## 2. OCI 运行守卫

### 2.1 基本用法

```bash
PY="/root/Autonomous Teacher/.venv/bin/python"
FROZEN="/root/Autonomous Teacher/artifacts/security/rootfs"
FROZEN_SHA="25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0"

# 1) 识别某个 rootfs 是否为冻结树（只读哈希；frozen → exit 10）
"$PY" scripts/a_next/oci_guard.py check-rootfs "$FROZEN" \
  --frozen-rootfs "$FROZEN" --frozen-sha "$FROZEN_SHA"

# 2) 运行前预检（不启动任何东西）
"$PY" scripts/a_next/oci_guard.py preflight \
  --rootfs /tmp/g4r-rootfs-workcopy \
  --evidence-dir /tmp/a-next/evidence-batch-001 \
  --frozen-rootfs "$FROZEN" --frozen-sha "$FROZEN_SHA" \
  --claim-id batch-001

# 3) 受守卫运行（推荐做法）：工作副本 + 独占 evidence 目录 + T0/T1 对比
cp -a "$FROZEN" /tmp/g4r-rootfs-workcopy
"$PY" scripts/a_next/oci_guard.py run \
  --rootfs /tmp/g4r-rootfs-workcopy \
  --evidence-dir /tmp/a-next/evidence-batch-001 \
  --frozen-rootfs "$FROZEN" --frozen-sha "$FROZEN_SHA" \
  --claim-id batch-001 \
  --deps "$PWD/artifacts/foundation/deps" \
  --runtime "$PWD/artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64" \
  --stage-manifest /tmp/final-stage/manifest.json \
  --podman-check \
  -- /usr/bin/podman run --rm --network none --read-only \
       --rootfs /tmp/g4r-rootfs-workcopy ... /opt/python/bin/python3.11 -B -m pytest tests/ -q
```

> 冻结 rootfs 的 **唯一合法用法** 是 `--frozen-rootfs`（只读哈希/快照）。把它传给任何 `--rootfs` 会被拒绝（exit 10）。
> G4-R 事故的直接教训：`podman run --rootfs <frozen>` 会在冻结树内创建挂载点目录；**禁止**。

### 2.2 拒绝与退出码

| exit | 含义 |
|---|---|
| 0 | OK |
| 2 | 用法错误（argparse 或缺少 `--frozen-rootfs` 快照且未显式 `--no-frozen-snapshot`） |
| 10 | 拒绝：`--rootfs` 是冻结树（同路径 / frozen 标记 / canonical hash 匹配） |
| 11 | 拒绝：evidence/output 目录已存在、父目录不可写、位于 frozen tree 内、或位于 rootfs 内 |
| 12 | 拒绝：单 writer 锁被其它批次持有 |
| 13 | 拒绝：rootfs 不是可用目录 |
| 20 | 运行期间 frozen rootfs canonical hash 漂移（T0 != T1）→ STOP |
| 21 | 被包裹命令非零退出（T0/T1 无漂移；报告仍落盘） |
| 23 | 运行前 frozen rootfs 已不在期望 SHA（pre-existing drift）→ 不启动 |

### 2.3 批次/evidence 约定（单 writer）

- 一个**批次** = 一个全新 `--evidence-dir` + 唯一 `--claim-id`；目录必须不存在（空目录也拒绝），禁止复用旧 evidence/JUnit 路径。
- 单 writer 锁固定为 `<evidence-parent>/.a_next.writer.lock`（`O_CREAT|O_EXCL`）；锁存在即拒绝（exit 12）。正常结束自动删除；异常/取证可用 `--keep-lock` 保留。
- T0/T1 快照记录：frozen rootfs、工作副本 rootfs、可选 deps/runtime/stage-manifest 的 SHA；`guard-report.json` 写入 evidence 目录，包含 argv、UTC、`env_scrubbed_names`、漂移与 wrapped exit code。
- 默认对包裹命令**移除**名称匹配 `KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL/AUTHORIZATION` 的环境变量（只记录变量名，不读取/打印值）。
- 运行前后建议 `--podman-check` 记录 `podman ps -a`，批次结束应为空。

## 3. 冻结 rootfs 物理防写检查

```bash
"$PY" scripts/a_next/rootfs_guard.py \
  --rootfs "$FROZEN" --expected-sha "$FROZEN_SHA" \
  --require-ro-mount        # 若要求物理只读挂载；未满足 → exit 32
  --emit-commands --json-out /tmp/a-next/rootfs-guard.json
```

| exit | 含义 |
|---|---|
| 0 | OK |
| 30 | 权限违规：存在 group/other 可写位，或测试 uid（默认 65534）对某路径可写 |
| 31 | canonical SHA 与期望不符 |
| 32 | `--require-ro-mount` 但挂载点不是只读 |
| 33 | 路径不存在/非目录 |

检查内容：tar 规范化 SHA（只读）、递归 `stat`（不跟随 symlink）、`findmnt -T` 挂载选项、测试 uid 可写判定；`--emit-commands` 输出可直接执行的独立验证命令（`find -perm /022`、`setpriv ... test -w`、`podman ... -v <frozen>:<frozen>:ro ...` 期望 EROFS）。

**实测（2026-11-20，只读检查）**：冻结 rootfs canonical = `25491e45…` ✅；扫描 7211 entries、`violation_count=0`；当前挂载状态为 `rw`（见 §5 残余风险，需部署侧改为只读 bind 或接受记录）。

## 4. CI 静态校验

```bash
BASE=<canonical-base-sha>          # 例如 work/g4r 上的冻结/审计基线 SHA
"$PY" scripts/a_next/ci_guard.py all --repo . --source work/g4r --base "$BASE"
# 分项：
"$PY" scripts/a_next/ci_guard.py branch    --repo . --source work/g4r --base "$BASE" \
  --expect-branch 'chore/.*|work/.*'
"$PY" scripts/a_next/ci_guard.py protected --repo . --base "$BASE"
"$PY" scripts/a_next/ci_guard.py merges    --repo . --base "$BASE" --allow-merge <reviewed-merge-sha>
"$PY" scripts/a_next/ci_guard.py cherry-pick --repo . --base "$BASE" --h0-ref work/m0-g4h0
```

| exit | 含义 |
|---|---|
| 0 | OK |
| 31 | 分支来源/血缘不符：base 不是 HEAD 祖先、merge-base 与声明的 source 不符、`main` 来源分支夹带 `work/g4r` 血缘、分支名不匹配 |
| 32 | 存在未 allow-list 的 merge commit |
| 33 | 受保护路径相对 base 发生变化且未在 `--allow` 中显式列出 |
| 34 | H0 风险：`work/m0-g4h0` 已是 HEAD 祖先（合并），或 HEAD 提交与 H0 提交 **patch-id 相同**（cherry-pick），或 `--strict-hints` 下出现 H0 主题提示 |

受保护路径（`ci_guard.py::PROTECTED_PREFIXES`）：`src/autoteacher_m0/security/**`、`src/autoteacher_m0/bridge/controller.py`、`recovery_diagnostics.py`、`request_lifecycle.py`、`src/autoteacher_m0/runtime/dsh_adapter.py`、`src/autoteacher_m0/cli.py`、`scripts/run_live.sh`、`config/g4/**`。

规则：
- **不得盲 merge/cherry-pick H0 实现**；H0 只允许选择性吸收已审阅、无 Key 的文档/Runbook/风险清单。`cherry-pick` 子命令用 ancestor + patch-id + subject 三重检查提供回归提示，不能代替 Reviewer 的决定。
- 受保护文件变动必须逐个显式 `--allow`（评审记录在 PR/审计文件），不得靠“没有回归”一句话通过。
- merge 默认全部拒绝，只有显式 `--allow-merge <sha>`（已审阅合并）才能通过。
- 该工具只做**静态提示**，不检查代码语义；最终安全裁定仍由 Independent Reviewer 完成。

## 5. 局限与残余风险（必须如实记录）

1. **不是防写边界**：`rootfs_guard` 是检查器，不是 OS 强制；root 用户仍可写。真正的物理防写依赖部署侧：`chmod -R go-w` + 挂载 `:ro`/只读 bind + 运行用户非 root/非 owner，并由 OS/容器运行时强制。
2. **哈希检测是事后证据**：canonical hash 计算约 291 MB 树（≈1–2 s），能检测漂移但不能阻止；T0/T1 只能覆盖工具运行窗口。
3. **单 writer 锁是协作约定**：`O_CREAT|O_EXCL` 锁 + 独占 evidence 目录防“同批次并发写”，但无法防有权用户手动删除锁。
4. **env 脱敏是名称匹配**：只移除名称含 key-like 子串的变量；不能保证第三方子进程不读取其它来源（文件、socket）。
5. **frozen 检测口径**：同路径 / marker 文件 / canonical hash 三种；已知 SHA 的“内容副本”也会被识别为 frozen（会阻止把它当工作副本使用——这是预期行为）。
6. **CI 检查是启发式**：patch-id 扫描有 `--max-h0-commits` 上限（默认 120，超出会标 `h0_scan_truncated`）；subject 提示默认只告警，`--strict-hints` 才失败。
7. **当前冻结 rootfs 挂载为 rw**：工具如实报告 `read_only:false`；若要求物理只读，须部署侧配置只读 bind 后以 `--require-ro-mount` 验收。
8. 本轮不包含真实 Key/Provider/HTTP/Live；本工具不改变任何门状态。

## 6. 测试与验收

```bash
py="/root/Autonomous Teacher/.venv/bin/python"
"$py" -B -m pytest tests/a_next_hygiene -q          # 38 passed
"$py" -m ruff check --no-cache scripts/a_next tests/a_next_hygiene
```

覆盖：冻结树按路径/哈希/marker 拒绝；输出目录已存在/在 frozen 内/在 rootfs 内拒绝；锁冲突；T0/T1 漂移；pre-existing drift；wrapped 命令失败；key-like env 脱敏；根目录权限违规、SHA 不符、只读挂载要求、只读不修改；CI 分支来源/夹带 G4R 血缘/受保护文件 allow-list/未授权 merge/H0 patch-id 与合并血缘/H0 ref 缺失。

脚本失败时均非零退出，可安全用于 CI 阻塞门。

## 7. 复现本次只读演示（不含任何写入冻结路径）

```bash
"$py" scripts/a_next/oci_guard.py check-rootfs \
  "/root/Autonomous Teacher/artifacts/security/rootfs" \
  --frozen-rootfs "/root/Autonomous Teacher/artifacts/security/rootfs" \
  --frozen-sha 25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0
# => {"is_frozen": true, "verdict": "rootfs_is_the_frozen_tree"}，exit 10

"$py" scripts/a_next/rootfs_guard.py \
  --rootfs "/root/Autonomous Teacher/artifacts/security/rootfs" \
  --expected-sha 25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0 \
  --emit-commands
# => verdict OK；sha_matches_expected=true；violation_count=0；mount.read_only=false（如实报告）
```

> 本工具与本文档不写冻结 rootfs、旧 Packet、Reviewer 报告或其它 PR 分支文件；任何新证据提交使用新路径/新身份。
