# M0 G3-D1-B — Stage / Launcher / 双 Principal 真实 DSH Echo 报告

**状态**：`D1_B_PASS_DUAL_PRINCIPAL_REAL_DSH_ECHO`（仅 D1-B 正向 Echo；**不是** D1 Gate 全通过、**不是** D2/D3、**不是** G3-D PASS、**不是** Live）
**日期**：2026-11-17 ｜ **执行 Agent**：D1-B Stage/Launcher Agent ｜ **工作树**：`/root/Autonomous Teacher`
**产品基线**：`4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`（D-P0）｜ **运行 HEAD**：`328a458b98871279a7a1926cdd1f28721672de00`（D-G0 rebaseline，仅 docs；`git diff 4bd4803 -- src spikes plugins scripts/g3c tests/integration/g3c tests/integration/g3_bridge` 为空）
**证据根**：`artifacts/g3d/d1b/`（`artifacts/` 被 gitignore，不进入产品 commit）｜ **规范命令**：

```bash
/root/.local/bin/python3.11 -B scripts/g3d/build_stage.py
/root/.local/bin/python3.11 -B scripts/g3d/launch.py \
  --case d1-echo --scenario echo --session g3d-d1-s1 \
  --evidence-dir artifacts/g3d/d1b
```

**唯一裁定**：本报告只支持“D1-B 的双 OS Principal 正向 Echo 已真实跑通且账本一致”。Tool 两轮 / Resume（D1-02/03）、D1 Gate、D2 攻击、D3 恢复均 **未执行**；完整 Gate 结论由 D1-C 出具。

---

## 1. 交付物

| 路径 | 作用 |
|---|---|
| `scripts/g3d/build_stage.py` | 从 `git archive 4bd4803` 构建独立 `trusted/`；candidate 以显式白名单组装；固定 rootfs 内 `--network none` 重建 adapter；生成并复核 `manifest.json` |
| `scripts/g3d/lib_g3d.py` | 纯函数契约：`$RUN` 权限、socket/ready 判定、容器 argv、manifest 校验、symlink-safe cleanup、TERM→有界 KILL |
| `scripts/g3d/launch.py` | Host root Launcher：preflight、`$RUN`/配置生成、Trusted→Ready→Candidate 顺序、证据采集、清理/canonical 复核 |
| `scripts/g3d/stage/trusted_entry.py` | Trusted 容器入口：目录/Config 断言、`inspect.getfile`+模块字节 SHA、`on_ready` 写受保护 ready、DEBUG peercred 日志 |
| `scripts/g3d/stage/candidate_entry.py` | Candidate 容器入口：principal/挂载/socket/网络/模块不可导入断言，真实 DSH `0.2.2-rc.2` Echo |
| `config/g3d/trusted/*.json` | 只读模板（controller 432/`socket_gid=null`/`expected_peer_uid=65534`；synthetic admission/broker） |
| `config/g3d/candidate/bridge.patch.yml` | Candidate overlay：仅 `/project/runtime/...`，无 `/probe`、无 trusted 路径 |
| `tests/integration/g3d/test_d1_launcher_contract.py` | 53 个 host 纯函数契约测试（权限/ready 顺序/argv/白名单/manifest/清理/超时/配置） |
| `docs/M0_G3D_D1B_REPORT.md` | 本报告 |

未修改 `src/`、`scripts/g3c/`、既有 G3-C 冻结证据/Packet、历史 docs、`tests/integration/g3{c,_bridge}`。

---

## 2. Stage 身份

| 项 | 值 |
|---|---|
| Stage 目录 | `artifacts/g3d/stage-20261117T192708Z`（新目录，未复用/覆盖 G3-C stage） |
| Manifest SHA-256 | `098512767548dc346cb4bddc1e8f0a732cd303897468d1aa0f8e5d04d9935a10` |
| 整体 tree SHA-256 | `b14de55a78e5457552fe90b885c227b8c569294f5ed2c472b8638fc02a090b81` |
| Trusted / Candidate tree SHA | `4b1fbe9ee6c2785307b92437a08c80ff54f909eb6454a127f6fea8ef97aab585` / `9178fb484f2b7094d4527de74e861b37a2cbc0ce7b631a2742aadef1de3b16ae` |
| 文件数 | trusted 57 / candidate 6529（含 node_modules/pkg-cache），逐文件 path/sha256/bytes/mode/source |
| Candidate 白名单 | `run/`, `config/bridge.patch.yml`, `runtime/{bridge,skill}`, `node_modules/`（排除 `.bin` symlink）, `native-cache/`, `pkg-cache/`, `fixtures/`, `etc/{passwd,group}`, `REFERENCE.json` |
| Candidate 禁止项实测 | 无 `autoteacher_m0`、`controller.py`、`fake_provider.py`、`admission.json`、`broker.json`、`policy.json`、`*.sqlite3*`、`rcpt-*.json`、`run/trusted_entry.py`、launcher、`.git`、完整 repo；无 symlink/特殊文件 |
| Adapter 重建 | 固定 rootfs 内 `--network none --cap-drop ALL` 由 `spikes/g3b-trusted-bridge/src/index.ts` 重编译；`builtJs.sha256 = 2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba`，与 G3-C 冻结 build-meta 一致（deterministic_match=true） |
| 运行时引用 | rootfs `25491e45…`、deps `e07729d7…`、Node `v22.23.2`、DSH SDK `0.2.2rc2`、runtime bin `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4` |

**Trusted 模块实际加载校验**（D0 §4.2）：`trusted/evidence/trusted-modules.json` 记录 10 个模块的 `inspect.getfile` 与字节 SHA-256；全部从 `/project/src/autoteacher_m0/...` 加载，且与 `git show 4bd4803:<path>` 的字节 SHA 完全一致（Launch check `trusted_modules_from_stage_and_git_blobs` PASS）。旧 G3-C stage 的 `e6fde1c` `src` **未使用**。

---

## 3. 规范 Run

| 项 | 值 |
|---|---|
| Run ID | `20261117T193529Z-d1-echo-f2cdc076` |
| UTC | `19:35:29Z` → `19:35:36Z`（Launcher）；Trusted `19:35:31Z` ready；Candidate `19:35:32Z` 启动（`run/trusted-ready.json`、`run/exits.json`） |
| 退出 | Launcher `0`；Trusted `0`；Candidate `0` |
| 断言 | 29/29 PASS（`run/checks.json`、`summary.json`） |
| 容器名 | `at-g3d-trusted-20261117T193529Z-d1-echo-f2cdc076`、`at-g3d-candidate-…`；运行后 `podman ps -a` 为空 |

### 3.1 双 Principal 与命名空间

| 观测 | Trusted | Candidate |
|---|---|---|
| 容器 argv | `--userns=host --user 0:0`，`--network none`，`--read-only`，`--cap-drop ALL`，`no-new-privileges` | `--uidmap 0:65534:1`、`--gidmap 0:65534:1`、`--gidmap 2000:2000:1`、`--group-add 2000`，`--user 0:0`，同上安全参数 |
| Host `/proc/<pid>/status` | `Uid/Gid 0/0`，`CapEff=000…0`，`NoNewPrivs=1` | `Uid/Gid 65534/65534`，`CapEff=000…0`，`NoNewPrivs=1`，`Seccomp=2` |
| uid_map / gid_map | `0 100000 65536`（Runner 自身嵌套 LXC userns 视角，见 `env/host-identity.json`） | `0 65534 1` / `0 65534 1` + `2000 2000 1` |
| 挂载 | `/project`(trusted stage, ro)、`/deps`(ro)、`/work/state`(rw)、`/work/g3b`(rw)、`/output`(rw)；无 candidate stage/session | `/project`(candidate stage, ro)、`/deps`(ro)、`/work/g3b`(**ro**)、`/work/session`(rw)；**无** `/work/state`、`/output`、`/project/src` |
| cgroup | `pids.max=256`、`memory.max=1073741824`、`cpu.max=100000 100000` | 同左（`memory.current≈11.7MB`、`pids.current=1`） |
| 网络 | `NetworkMode=none` | `NetworkMode=none`；`AF_INET/AF_INET6 socket()`→`EACCES(13)`，DNS→`EAI_AGAIN(-3)`，`if_nameindex` 仅 `lo`，`/proc/net/route` 空 |

### 3.2 UDS / Ready / Peercred

- Host `ipc/` = `2750 root:2000`（setgid，evidence `env/run-layout.json`）；socket 在 Launcher 检查时 `S_ISSOCK 0660 root:2000`（`socket-stat/before-candidate.json`）。
- Trusted `on_ready` 仅在 `bind` + `chmod/chown` 校验 + `listen()` 之后写 `/work/state/ready`（0600 root，`O_NOFOLLOW|O_EXCL`，fsync 文件与目录）。
- Host Launcher 独立复核：socket stat + `/proc/<trusted_pid>/net/unix` 中 `flags=0x10000`（LISTEN）+ inode 与 ready 文件一致 + 容器 running；四项全满足后才写 `$RUN/state/launcher-ready.json` 并启动 Candidate（`run/launcher-ready.json`、`socket-stat/listening.json`）。Candidate 从不参与 Ready。
- Trusted 侧 `SO_PEERCRED`（`peercred/trusted-log-extract.txt`）：

```text
bridge socket ready mode=0660 gid=2000 uid=0 peer_uid=65534
bridge peer accepted uid=65534 gid=65534 pid=0
```

`pid=0` 是跨 PID namespace 的已知正常值，**未**用于鉴权；无 `PEER_UID_DENIED`/`PEERCRED_UNAVAILABLE`。

### 3.3 Candidate 边界自检（`traces/principal.json`，全部 PASS）

未导入 `autoteacher_m0`/`controller`/`broker`/`fake_backend`（`find_spec=None`）；`PYTHONPATH=/deps`；`/work/state`、`/project/src` 不存在；socket unlink/rename/IPC create 分别得到 `EROFS`/`EROFS`/`EROFS`；无 Key-like env；无 trusted 组件进程。

### 3.4 真实 DSH → Controller → Broker → Fake → Receipt

- Candidate 真实 `DeepSeekHarness`（`sdk-minimal`、patches=`/project/config/bridge.patch.yml`）执行 Echo；只通过 `/work/g3b/bridge.sock`。
- DSH：`final_response="ok"`，`finish_reason="completed"`，13 events；usage：

```text
inputTokens=11  cacheReadTokens=2  cacheWriteTokens=0
outputTokens=5  reasoningTokens=0  totalTokens=18
```

- Fake receipt `rcpt-a597ee427a7047a3802714d683340f98`：usage **与 DSH 完全相等**，`synthetic=true`、`real_model_calls=0`、`http_calls=0`、`network_used=false`；`received-count={"count":1}`。
- Broker/Attempt：

| 对象 | 值 |
|---|---|
| Reservation | `94241d59-4316-4211-9227-2c0d112876d6`，`status=OK`，`input_used=13`、`output_used=5`、`cost=0.001022` |
| Claim | `call-823835fb…`，`status=COMPLETED` |
| Attempt | `att-47e24b2d15a44c4984750f5b7bb026be`，`state=SETTLED` |
| Admission | `82966b33fbb37f923b97625232f52ff6`，`run_id=20261117T193529Z-…` |
| 两个 Digest | `claim.request_digest == attempt.prepared_digest == c873157f…`；`attempt.payload_digest == receipt.raw_sha256 == d20033ef…`（不要求两者互等） |

- DB 拷贝（Trusted 停止后只读查询）：`db/broker.sqlite3`、`db/attempts.sqlite3`、`db/snapshot.json`；`PRAGMA integrity_check=ok`。原始路径记录于 `db/paths.json`（`$RUN/state/*.sqlite3`）。

### 3.5 清理 / 完整性

- 顺序：先 Candidate 再 Trusted；TERM 后 0.19s 正常退出（未触发 KILL）；`podman rm -f`；只删除本 Run 的 `bridge.sock`/`bridge.sock.lock`；`ipc/` 仅空目录时 rmdir；随后删除本次 `$RUN`（不跟随 candidate symlink，`cleanup/cleanup.json`）。
- 结束快照：`podman ps -a` 空、`at-g3d-*` 空、无残留进程、socket 不存在、run-dir 不存在（`cleanup/`）。
- Rootfs / deps / stage 前后 SHA 相等：`25491e45…` / `e07729d7…` / `b14de55a…`（`env/canonical-pre.json`、`env/canonical-post.json`）。
- 0 Key：host env key-like 名 0；两容器 env 名仅固定白名单（含 `HOSTNAME`，无 proxy/Key）；`bash scripts/run_live.sh`=`exit 3`；`LiveGate().inspect(live_requested=True)`=`BLOCKED`（`env/livegate.json`）。全部容器 `--network none --http-proxy=false --unsetenv-all`。

---

## 4. 测试

| 套件 | 结果 |
|---|---|
| 新增 `tests/integration/g3d/test_d1_launcher_contract.py` | **53 passed**（0.16s）；覆盖 `$RUN` 权限、ready 顺序（socket/listen/inode/容器状态缺一不可）、Trusted/Candidate argv 正向与 8 类削弱拒绝、candidate 白名单/禁止文件、manifest 未知/篡改/symlink、TERM→KILL、清理幂等/越界拒绝、模板配置、env 名不泄漏值 |
| `tests/integration/g3d` + `tests/integration/g3_bridge` | **137 passed** |
| `tests/integration/g3c`（冻结 G3-C） | **110 passed** |
| `ruff check scripts/g3d tests/integration/g3d/test_d1_launcher_contract.py` | clean |

容器真实证据由 `launch.py` 产生；pytest 不冒充内核/容器证据。

---

## 5. 失败、偏差与残余

- 开发早期尝试（均在本 Run 前，证据归档 `artifacts/g3d/d1b-attempt-*` / `d1b-run-d20b80ab`）暴露并修正了：preflight 属性遮蔽、key 标记过宽（`DSH_SESSION_ID` 误报）、`find_spec` 对缺失父包抛错、`/proc/self/mountinfo` 解析、admission `tool_schemas` 未与 DSH `skill_lookup` 对齐、settlement 校验字段层级。**没有**通过放宽 Socket 权限、同 UID、挂载 state、mock 或关闭 peercred 来“修复”。
- 结论范围：仅 **Echo 1 次**。D1-02 Tool 两轮、D1-03 Resume、D1 Gate、D2-01..12、D3 均未运行，不得写成 PASS。
- 残余风险：Candidate Session 当前无磁盘硬配额（D0 已知 P2）；Rootful Podman/LXC/Trusted root 属受信基础；本机 `CAN_ISOLATE` 不可外推；DSH 固定为 `0.2.2-rc.2`；`--userns=host` 的 Trusted uid_map 需结合 Runner 自身嵌套映射阅读。
- 未推送、未 amend、未修改 G3-C 冻结证据/Packet/历史 docs。

---

## 6. 证据索引（`artifacts/g3d/d1b/`）

```text
env/{git.json,git.txt,preflight.json,podman-info.json,host-identity.json,
     livegate.json,userns-probe.json,userns-probe.stdout.txt,setgid-probe.json,
     canonical-pre.json,canonical-post.json,run-layout.json,
     stage-manifest.json,stage-summary.json,stage-validation.json}
run/{argv-trusted.json,argv-candidate.json,inspect-*.json,trusted.log,candidate.log,
     ready,launcher-ready.json,exits.json,state-assets.json,checks.json,
     config-*.json,run-summary.txt,trusted-preflight.json}
traces/{principal.json,dsh-result.json}
db/{broker.sqlite3,attempts.sqlite3,snapshot.json,paths.json}
receipt/{rcpt-*.json,received-count.json,timing-*.json,summary.json}
uid-map/*、mountinfo/{trusted,candidate}.txt、socket-stat/*、peercred/*、
network-probe/{candidate-network.json,container-network.json,env-names.json}、
cleanup/{cleanup.json,ps-after.txt,residual-processes.json}、cleanup.json、
commands.jsonl、summary.json
```
