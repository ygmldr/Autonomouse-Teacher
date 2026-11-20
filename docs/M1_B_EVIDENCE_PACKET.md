# M1-B 证据包格式与收集器（Evidence Packet）

| 字段 | 值 |
|---|---|
| 文档状态 | **IMPLEMENTATION REFERENCE（design + 工具说明，不含运行结果）** |
| 版本 | `m1b.evidence-packet.v0`（2026-11-21） |
| 关联协议 | `docs/M1_B_EVALUATION_PROTOCOL.md` §11（`audit-index.json` 字段契约；该文档位于同级 PR 分支 `b-next/pr5-eval-protocol`，本文件内自带字段表以免依赖顺序） |
| 工具 | `scripts/m1b/collect_evidence.py`（纯 stdlib、离线、只读 + 写指定 `--out` 目录） |
| 工作区/基线 | `/root/m1b/p5ev`，分支 `b-next/pr5-evidence`，基线 `3103a06` |
| 本文件边界 | 只描述证据包与收集器用法；不声称任何 E2E/集成/真实效果已通过；不包含真实 Key/PII/hidden 内容 |

---

## 1. 目的与非目标

**目的**：让任何一条 B 线验证（旧两套历史套件、新 B 集成套件、demo/CLI、安全/崩溃负例、X-01/X-02 检查）都能产出**可追溯、可哈希、append-only** 的证据记录，供 Lead 与独立 Reviewer 复核；机器可读的 `audit-index.jsonl` 是唯一权威索引。

**非目标**：

- 收集器不是产品判定器：`EXECUTED_PASS` 只是**命令执行成功**，不是产品 PASS、不是证据类 PASS、不是"真实效果"。
- 收集器不是沙箱：它只按白名单执行**受信任的 Reviewer 命令**；恶意 PoC 必须按协议 §5 在隔离 Worker 内执行，禁止用本工具在主机直跑。
- 收集器不自动分类证据（不把 pytest 成功自动升级为 `DETERMINISTIC`/`PASS`）；`--evidence-class` 由调用者/Reviewer 显式标注，默认 `NOT_VERIFIED`。
- 收集器不联网、不读 fixture 内容作命令来源、不修改被执行的测试/实现。

---

## 2. 证据包结构

一次运行（一个 `run_id`）产生如下目录结构；`--out DIR` 可重复使用以形成 append-only 包：

```text
<out>/
├── README.md                     # 首次运行自动生成的边界声明（永不覆盖已有文件）
├── audit-index.jsonl             # 权威 append-only 索引：每次运行追加 1 行 JSON
├── audit-index.json              # 物化视图：{schema_version, entry_count, entries[]}，原子重写
└── raw/
    └── <run_id>/
        ├── evidence.json         # 本次运行的原始证据（被索引 sha256 引用的对象）
        ├── stdout.log            # 捕获的 stdout（上限 2 MiB）
        └── stderr.log            # 捕获的 stderr（上限 2 MiB）
```

- **append-only 保证**：`audit-index.jsonl` 只以 `"a"` 模式追加，永不截断/重写；已有 malformed 行会**拒绝**写入并退出 2（不自动修复）。重复 `run_id` 同样拒绝。
- **物化视图**：`audit-index.json` 从 jsonl 派生并原子替换（临时文件 + `os.replace`），保证内容 = 全部 entries；若运行在 append 与物化之间崩溃，**以 jsonl 为准**（重建方法见 §7）。
- **artifact manifest**：每个 artifact 的 `sha256`/`bytes`/`exists`/`repo_relative` 记录在 `evidence.json` 与索引条目的 `artifacts[]` 字段中（嵌入 manifest；不另写散落文件）。
- **README 边界声明**：首次运行自动写 `<out>/README.md`（固定文本，无时间戳），说明 `EXECUTED_PASS` 不是产品 PASS、离线合成边界、无 Key/网络。已存在时不覆盖（append-only 包不应被改写）。

---

## 3. `audit-index.jsonl` 字段（与协议 §11 对齐）

每条记录一行 JSON，字段如下（`sort_keys=True` 输出，便于 diff/哈希）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | string | 证据用例 ID（如 `B1-05`、`B4-01`、`X-01`）；`[A-Za-z0-9][A-Za-z0-9._-]{0,63}` |
| `run_id` | string | 本次运行唯一 ID；默认 `<case_id>-<UTC compact>-<hash>`，可由 `--run-id` 显式指定（重复拒绝） |
| `branch` | string | `--branch` 或 git 当前分支；git 不可用为 `UNKNOWN` |
| `git_sha` | string/null | 仓库 `HEAD`（40 hex）或 `null`（无 git 环境；**绝不伪造**；可用 `--git-sha` 显式传入归档冻结 SHA） |
| `git_available` | boolean | 被测量目录是否存在可用的 git 仓库（无 `.git` clean archive 为 `false`） |
| `git_sha_source` | string | `git`（从当前仓库读取）/ `explicit`（调用者 `--git-sha` 显式提供）/ `unavailable`（无 git 且未提供） |
| `tree_sha` | string/null | `git rev-parse HEAD^{tree}`（40 hex）或 `--tree-sha` 显式值；无 git 时为 `null` |
| `command` | string/null | 原始命令字符串（调用者提供；不来自 fixture） |
| `command_argv` | array/null | 经 `shlex` 解析后的 argv（`shell=False` 实际执行体） |
| `cwd` | string | 实际执行目录（必须位于仓库根内） |
| `environment` | object | `python_version`/`python_implementation`/`python_executable`/`platform`/`system`/`machine`/`cwd`/`repo_root` + `TZ`/`PYTHONHASHSEED` |
| `utc` | string | 墙钟 UTC（`YYYY-MM-DDTHH:MM:SSZ`）；**审计元数据，不是 artifact 确定性内容** |
| `expected_exit` | integer | `--expected-exit`（默认 0），仅记录 |
| `exit_code` | integer/null | 实际 exit code；超时/未执行为 `null` |
| `timed_out` | boolean | 是否因 `--timeout` 被终止 |
| `status` | string | `EXECUTED_PASS` / `EXECUTED_FAIL` / `NOT_RUN`（见 §4） |
| `evidence_class` | string | 证据类标签（默认 `NOT_VERIFIED`；见 §5） |
| `artifacts` | array | 每个 artifact 的 `requested/path/repo_relative/exists/sha256/bytes`（缺失时 `error`） |
| `stdout` / `stderr` | object/null | `{bytes, sha256, truncated, tail}`；tail 取末尾 2000 字符 |
| `raw_evidence_path` | string/null | 相对 `<out>` 的路径（`raw/<run_id>/evidence.json`） |
| `sha256` | string/null | `evidence.json` 的 sha256（raw evidence 的完整性锚点） |
| `limitation` | string/null | 限制/失败原因；非 PASS 必填；多条以 `"; "` 连接 |
| `schema_version` | string | `"m1b.audit-index.v0"` |
| `collector` | object | 工具 `name/version/sha256`（自身溯源） |

### 3.1 无 `.git` clean archive 的绑定行为（P1-1）

- 在 `git archive HEAD | tar -x` 生成的 clean archive 中运行时，collector 探测到没有 git 仓库，记录
  `git_sha: null`、`git_available: false`、`git_sha_source: "unavailable"`、`tree_sha: null`，
  `branch: "UNKNOWN"`；**不会编造 40-hex SHA**。
- 需要绑定冻结 SHA 时，调用者必须显式传入 `--git-sha <40-hex-frozen-commit>`（可选 `--tree-sha <40-hex-tree>`），
  collector 记录 `git_sha_source: "explicit"`；该 SHA 是调用者提供的 provenance，不是运行时 git 读取。
- clean-archive 回归命令（Reviewer/CI 可复跑）：

```bash
rm -rf /tmp/m1b-archive && mkdir -p /tmp/m1b-archive
git -C <repo> archive <FROZEN_SHA> | tar -x -C /tmp/m1b-archive   # no .git
cd /tmp/m1b-archive
PY="/root/Autonomous Teacher/.venv/bin/python"
"$PY" scripts/m1b/collect_evidence.py --out /tmp/m1b-archive-evidence --case-id ARCHIVE-01 \
  --git-sha <FROZEN_SHA> --tree-sha <FROZEN_TREE_SHA> \
  --command "$("$PY" -c 'import shlex,sys;print(shlex.join([sys.executable,"-m","pytest","tests/m1_teacher","-q"]))')"
```

- 回归测试：`tests/m1_teacher/test_evidence_collector.py::test_collector_is_portable_in_a_no_git_archive_copy`
  （`git_available=false`/`git_sha=None`/显式 `--git-sha` 两分支）；在 clean archive 中该测试随全量套件一起执行。

**索引条目模板（字段示意；不是运行结果，状态与数值均为占位）**：

```json
{
  "schema_version": "m1b.audit-index.v0",
  "case_id": "<CASE_ID>",
  "run_id": "<RUN_ID>",
  "branch": "<BRANCH>",
  "git_sha": "<FROZEN_40_HEX_SHA_OR_NULL>",
  "git_available": true,
  "git_sha_source": "git",
  "tree_sha": "<40_HEX_TREE_OR_NULL>",
  "command": "<QUOTED_COMMAND>",
  "command_argv": ["<ARG0>", "<ARG1>"],
  "cwd": "<REPO_ROOT>",
  "environment": {"TZ": "UTC", "PYTHONHASHSEED": "0", "python_version": "<X.Y.Z>"},
  "utc": "<YYYY-MM-DDTHH:MM:SSZ>",
  "expected_exit": 0,
  "exit_code": null,
  "timed_out": false,
  "status": "NOT_RUN",
  "evidence_class": "NOT_VERIFIED",
  "artifacts": [],
  "stdout": null,
  "stderr": null,
  "raw_evidence_path": "raw/<RUN_ID>/evidence.json",
  "sha256": "<64_HEX_OF_EVIDENCE_JSON>",
  "limitation": "template placeholder; run the collector for a real entry",
  "collector": {"name": "m1b.collect-evidence", "version": "m1b.collect-evidence.v0", "sha256": "<64_HEX>"}
}
```

---

## 4. `status` 语义（窄定义，防止伪造 PASS）

| status | 触发条件 | 含义 |
|---|---|---|
| `EXECUTED_PASS` | 命令实际执行且 `exit_code == 0` | **仅执行成功**；不是产品/证据 PASS |
| `EXECUTED_FAIL` | 命令实际执行但 exit≠0、超时，或请求的 artifact 缺失/不可哈希 | 执行失败/证据不完整 |
| `NOT_RUN` | 未提供 `--command`；命令被 preflight 拒绝（危险/不在白名单/cwd 越界/可执行文件不存在）；索引 malformed/run_id 重复导致拒绝 | **绝不可当作 PASS**；必须附 `limitation` |

规则：

1. 没有 `--command` 的记录永远不是 PASS；没有 `sha256`/`raw_evidence_path` 的记录永远不是证据。
2. `EXECUTED_PASS` 不改变证据类；Reviewer 必须自行复跑并标注 `INDEPENDENTLY_REEXECUTED`，否则只能作 `OWNER_REPORTED` 引用。
3. artifact 缺失即使命令 exit 0 也判 `EXECUTED_FAIL`（不能声称"证据完整"）。
4. `--expected-exit` 仅记录；status 规则固定为"exit 0 才 PASS"，避免用期望值掩盖失败。

---

## 5. `evidence_class` 标注（与协议 §1 词汇一致）

| 证据类 | 证据包中的用法 |
|---|---|
| `MOCK` | 合成 fixtures/mock learner/脚本化结果；不得写成真实收益 |
| `DETERMINISTIC` | 冻结输入/seed/时间戳下可重复的断言/哈希/replay；必须附命令与 raw sha256 |
| `HUMAN_REVIEWED` | Reviewer 人工审查，需在报告注明范围与身份（收集器不自动产生） |
| `NOT_VERIFIED` | 默认值；执行了命令≠验证了能力，未独立复算前保持此值 |
| `UNVERIFIED` | 依赖本线之外/无法在 B 线验证（如 M0、真实 Provider） |
| `BLOCKED` | 需要人类授权/外部依赖；不得降级成 `NOT_RUN` 后放行 |
| `NOT_RUN` | 未执行（含收集器拒绝/未提供命令） |
| `INDEPENDENTLY_REEXECUTED` | **仅 Reviewer 本轮真实复跑**时可标；必须附 Reviewer 身份、命令、环境、哈希；不得由 Owner 或历史报告转写 |

**禁止**：`MOCK` 与"真实学习收益"同句；`NOT_RUN/BLOCKED/UNVERIFIED` 改写成 PASS；`OWNER_REPORTED` 标成 `INDEPENDENTLY_REEXECUTED`；历史 536/365 相加成统一数字。

---

## 6. 命令行与复跑模板

### 6.1 基本用法（Reviewer，在仓库根执行）

```bash
PY="/root/Autonomous Teacher/.venv/bin/python"
CMD=$("$PY" -c 'import shlex,sys; print(shlex.join([sys.executable,"-m","pytest","tests/m1_teacher","-q"]))')

"$PY" scripts/m1b/collect_evidence.py \
  --out /tmp/m1b_evidence/B5-01 \
  --case-id B5-01 \
  --command "$CMD" \
  --expected-exit 0 \
  --limitation "offline synthetic only; not a product PASS"
```

说明：命令经过 `shlex.split`；含空格的路径（如 `/root/Autonomous Teacher/.venv/bin/python`）**必须**由 `shlex.join` 或显式引号传入，否则会被拆成多个 token 并被 preflight 拒绝（这是有意的安全行为）。

### 6.2 带 artifact 的复跑（证据哈希）

```bash
"$PY" scripts/m1b/collect_evidence.py \
  --out /tmp/m1b_evidence/B5-01-artifacts \
  --case-id B5-01-artifacts \
  --command "$CMD" \
  --artifact docs/m1a_evidence/e2e_student_a.jsonl \
  --artifact docs/m1a_evidence/e2e_summary.json \
  --limitation "historical artifacts only; review context required"
```

`--artifact` 相对 `--cwd`（默认仓库根）解析；每个 artifact 记录 `sha256/bytes/exists`。不同公开面文件集合会改变某些 artifact 哈希（参考 M1-Offline demo 两种上下文），必须记录上下文（冻结 SHA/文件集合），不得静默改期望值。

### 6.3 旧两套历史套件（仅作 Reviewer 复跑输入；历史数字不相加）

```bash
# M1-A（冻结实现 C6=3010426…；clean archive 见协议 §3.3）
"$PY" scripts/m1b/collect_evidence.py --out /tmp/m1b_evidence/B5-01-m1a \
  --case-id B5-01-m1a \
  --command "$("$PY" -c 'import shlex,sys;print(shlex.join([sys.executable,"-m","pytest","tests/m1_teacher","-q"]))')"

# M1-Offline（冻结 C2=052d980d…；合入/复制到独立 clean 副本后执行）
"$PY" scripts/m1b/collect_evidence.py --out /tmp/m1b_evidence/B5-01-m1off \
  --case-id B5-01-m1off \
  --command "$("$PY" -c 'import shlex,sys;print(shlex.join([sys.executable,"-m","pytest","tests/m1_offline","-q"]))')"
```

> 历史报告声称 536/365 tests 各自通过（`REVIEWER_REPORTED` / `OWNER_REPORTED`，只作历史冻结参考）；本轮必须由 Reviewer 重新执行并记录**新的**运行结果，禁止把两个历史数字相加或直接填为 B-PR5 通过数。

### 6.4 demo / 确定性 artifact 双跑

```bash
# 每次运行作为一个独立 run；两次运行后比较 sha256（diff 为空才可声称“两次一致”）
"$PY" scripts/m1b/collect_evidence.py --out /tmp/m1b_evidence/B5-01-demo1 \
  --case-id B5-01-demo1 \
  --command "$("$PY" -c 'import shlex,sys;print(shlex.join([sys.executable,"-m","m1_teacher.demo"]))')"
"$PY" scripts/m1b/collect_evidence.py --out /tmp/m1b_evidence/B5-01-demo2 \
  --case-id B5-01-demo2 \
  --command "$("$PY" -c 'import shlex,sys;print(shlex.join([sys.executable,"-m","m1_teacher.demo"]))')"
sha256sum /tmp/m1b_evidence/B5-01-demo1/raw/*/stdout.log /tmp/m1b_evidence/B5-01-demo2/raw/*/stdout.log
```

### 6.5 预检与安全限制

- 默认允许的可执行名：`python`/`python3`/`python3.11`/`python3.12`/`pytest`/`ruff`/`echo`/`git`（按 basename 判断；venv python 可用）。
- `git` 只允许只读子命令：`diff/log/show/rev-parse/status/ls-files/cat-file/grep`；`git push/clean/reset` 等拒绝。
- 硬拒绝（即使 `--allow-any-command` 也拒绝）：`rm/rmdir/shred/dd/mkfs*/sudo/su/curl/wget/ssh/scp/sftp/nc/ncat/telnet/kill/pkill/killall/chmod/chown/systemctl/mount/umount/apt/pip/uv/npm/podman/docker` 与 shell（`bash/sh/...`）。
- `--allow-any-command` 仅用于受信任 Reviewer 命令；仍受硬拒绝列表与 git 子命令限制。
- `--cwd` 必须 resolve 到仓库根内部；否则 `NOT_RUN`（防止在任意主机路径执行）。
- 子进程环境会剥离明显凭据变量（匹配 `api_key/token/secret/password/credential/provider`）；证据只记录白名单环境字段。
- `--timeout` 默认 1800 秒；超时判 `EXECUTED_FAIL` 且 `timed_out=true`。
- 收集器自身纯 stdlib、无网络 import；但**子命令本身**是否联网由 Reviewer 环境负责（协议要求 socket 阻断/隔离环境）。

---

## 7. 证据包校验（Reviewer/Lead 可执行）

```bash
# 1) 每个 raw evidence 的 sha256 与索引一致
"$PY" - <<'PY'
import hashlib, json
from pathlib import Path
out = Path("/tmp/m1b_evidence/B5-01")
for line in (out / "audit-index.jsonl").read_text().splitlines():
    entry = json.loads(line)
    raw = out / entry["raw_evidence_path"]
    assert raw.is_file(), raw
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == entry["sha256"], entry["case_id"]
    for artifact in entry["artifacts"]:
        if artifact.get("exists"):
            assert hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
print("audit index OK:", out)
PY

# 2) append-only：旧行字节不变（对比两次运行前后的 jsonl 前缀）
# 3) 物化视图与 jsonl 条目数/内容一致
"$PY" - <<'PY'
import json
from pathlib import Path
out = Path("/tmp/m1b_evidence/B5-01")
entries = [json.loads(line) for line in (out / "audit-index.jsonl").read_text().splitlines()]
mirror = json.loads((out / "audit-index.json").read_text())
assert mirror["entries"] == entries and mirror["entry_count"] == len(entries)
print("mirror OK:", len(entries))
PY

# 4) 无无命令 PASS / 无 hashless PASS（应输出 0）
"$PY" - <<'PY'
import json
from pathlib import Path
entries = [json.loads(line) for line in (Path("/tmp/m1b_evidence/B5-01") / "audit-index.jsonl").read_text().splitlines()]
bad = [e for e in entries if e["status"] == "EXECUTED_PASS" and (not e.get("command") or not e.get("sha256") or not e.get("raw_evidence_path"))]
print("bad PASS entries:", len(bad))
PY
```

**物化视图重建**（jsonl 权威；若 `audit-index.json` 缺失/过期）：

```bash
"$PY" - <<'PY'
import json
from pathlib import Path
out = Path("/tmp/m1b_evidence/B5-01")
entries = [json.loads(line) for line in (out / "audit-index.jsonl").read_text().splitlines()]
(out / "audit-index.json").write_text(
    json.dumps({"schema_version": "m1b.audit-index.v0", "entry_count": len(entries), "entries": entries},
               ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print("rebuilt audit-index.json from jsonl:", len(entries))
PY
```

---

## 8. 已知限制（必须保留在报告中）

1. 收集器只记录**执行事实**；不判断命令是否真的验证了目标能力，也不自动判定 `PASS`。
2. `utc`、`run_id` 含墙钟/随机成分，属于审计元数据；不得作为确定性 artifact 的一部分承诺。
3. `evidence_class` 默认 `NOT_VERIFIED`，必须由 Reviewer 显式标注；忘记标注不会自动变成证据。
4. 白名单/硬拒绝是**纵深防御**而非沙箱；受信任的 `python -c` 仍可执行任意代码（调用者责任）。恶意不可信代码只能按协议 §5 在隔离 Worker 中处理。
5. 收集器不阻断子命令网络；网络隔离由 Reviewer 环境（socket 阻断/`--network none`）保证。
6. 子进程 stdout/stderr 上限 2 MiB、tail 2000 字符；超限截断会在 `limitation` 与 `truncated` 中标注。
7. `audit-index.json` 是派生视图；append-only 字节保证只对 `audit-index.jsonl` 有效。
8. 跨 learner/session 泄漏、反例证据、crash 证据仍需专门探针与独立 Worker；本工具只提供统一封装与哈希，不替代协议 §5/§6 的专项验证。
