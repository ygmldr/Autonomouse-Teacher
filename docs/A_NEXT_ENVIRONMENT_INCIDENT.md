# A-NEXT — 环境事故记录：主仓库 `artifacts/` 误删与恢复（append-only）

- **文档 ID**：`A-NEXT-ENVIRONMENT-INCIDENT-v1`
- **事故 ID**：`INCIDENT_20261121`
- **记录者**：A-PR0 Implementer-Docs（子 Agent；非 Lead、非 Independent Reviewer）
- **记录时间（UTC）**：`2026-11-20T19:57Z`–`20:05Z`（本地 `Asia/Shanghai` = 2026-11-21 03:57–04:05）
- **事故时间**：**约 `2026-11-20T19:53Z`**（本地 2026-11-21 03:53，+08:00）
- **性质**：**append-only 事故记录/损失清单/影响声明**。只新增本文件；**不改**任何已提交文档字节。
  本记录不淡化、不隐藏、不伪造恢复；不是授权、不是 PASS、不是部署证据。
- **严重度**：`HIGH`（证据完整性事故，非实时人身/生产事故）。0 真实 Key/Provider/HTTP；0 付费调用；未改动
  Git 跟踪的源码/文档/矩阵/Review 字节。
- **当前状态**：`PARTIAL_RECOVERY`；`v1 Packet = LOST_IN_INCIDENT_20261121`；部分 G4/G4-F/G4-R 原始证据不可恢复。

---

## 0. 事实分级（防误读；本文件严格区分三类陈述）

| 标记 | 含义 | 本文件中的使用 |
|---|---|---|
| `LEAD_REPORTED` | 由 Lead 在事故处置中报告；**本 Agent 无法独立复现删除命令/时序** | 事件发生的直接命令、误删过程、检测触发方式、恢复来源选择、`rmdir EBUSY` 结果 |
| `MEASURED_20261121` | 本文件记录者在事故后（19:57Z–20:05Z）**亲自实测** | 当前目录/挂载状态、恢复后文件计数/大小、rootfs/deps canonical 哈希、Packet v2 独立 verifier、v1 缺失搜索、备份 tar SHA/大小/时间、哈希与 symlink 异常 |
| `DOC_RECORDED` | 仅由仓库 Git 跟踪文档记载的历史断言（如 v1 Packet 的哈希） | v1 Packet 的 `manifest 4aed2a92…`/`hashes 421b07ae…`/177 files 等；**原始字节已丢失，无法复核** |

> **禁止**把 `LEAD_REPORTED` 当成本文件独立验证的事实；也**禁止**把 `DOC_RECORDED` 当作当前可复核证据。

---

## 1. 事件摘要（一句话）

`2026-11-20T19:53Z` 左右，Lead 在清理 `/tmp` 下陈旧 bind mount 时对 `/tmp/at-f4-clean` 执行递归删除；
其子挂载 `/tmp/at-f4-clean/artifacts` 是主仓库 `/root/Autonomous Teacher/artifacts` 的 **bind mount**，
`rm -rf` 因此递归删除了主仓库 **gitignored `artifacts/` 全部内容**；随后从 `/tmp` 与各 worktree 的
`artifacts` 副本以 no-clobber 方式合并恢复。关键 `rootfs`/`deps` 经 canonical 哈希验证恢复成功、Packet v2 经
独立 verifier PASS；**v1 Packet 原始字节与部分 G4-F/G4-R 原始证据不可恢复**（详见 §5/§6）。

---

## 2. 时间线（`UTC`；本地 = UTC+08:00）

| UTC | 本地（+08） | 事件 | 依据 |
|---|---|---|---|
| `~19:53Z` | 2026-11-21 `03:53` | Lead 清理陈旧 `/tmp/at-f4-clean`；`rm -rf /tmp/at-f4-clean` 递归进入其子挂载 `/tmp/at-f4-clean/artifacts`（bind → `/root/Autonomous Teacher/artifacts`），删除 `artifacts/` 内容；最终 `rmdir` 报 `EBUSY` | `LEAD_REPORTED` |
| `~19:53–19:55Z` | `03:53–03:55` | 检测：`rootfs` hash 复核失败、`artifacts/` 为空；确认误删范围 | `LEAD_REPORTED` |
| `~19:53–19:56Z` | `03:53–03:56` | 恢复：以 no-clobber 合并从 `/tmp/at-g4f-review/artifacts`（2026-11-19 副本）与各 worktree 的 `artifacts` 副本（`g4r-phase2`、`g4r-*`、`m0-g4h0*` 等）复制回主仓库 | `LEAD_REPORTED` |
| `19:56:30Z` | `03:56:30` | 生成恢复后备份 tar：`/root/a-next-artifacts-restored-20261121.tar`（916,480,000 bytes；sha256 见 §3） | `MEASURED_20261121`（mtime/size/sha） |
| `19:57:37Z` | `03:57:37` | 本记录开始独立核查；`/tmp/at-f4-clean` 当前为空目录且**已无 bind mount**（`findmnt -T` 无输出） | `MEASURED_20261121` |
| `19:57–20:05Z` | `03:57–04:05` | 独立核查：rootfs/deps canonical hash、Packet v2 verifier、v1 全盘 scoped 搜索、恢复物清单/计数、备份 tar 校验 | `MEASURED_20261121` |

> 时间线中的 `~` 表示 Lead 报告的时间精度；“恢复/备份 tar”之后的时间点均为本记录实测。

---

## 3. 关键哈希（`MEASURED_20261121`，除非另注）

| 对象 | 值 | 说明 |
|---|---|---|
| 恢复后备份 tar | `/root/a-next-artifacts-restored-20261121.tar`；**sha256 `11172f0268cdf2dc2bde08e90d9d93c0a444b134f8eaab9a712057c9d5159d42`**；916,480,000 bytes；mtime `2026-11-20 19:56:30Z` | 与任务/Lead 报告一致；**为恢复后状态备份，不是事故前快照** |
| rootfs（恢复后） | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` | canonical 方法：`tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . \| sha256sum`；**与冻结值一致** |
| deps（恢复后） | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | 同法对 `artifacts/foundation/deps`；**与冻结值一致** |
| rootfs/deps 恢复来源副本 | `/tmp/at-g4f-review/artifacts/security/rootfs`、`.../foundation/deps`（2026-11-19 副本） | 用同法复算，二者分别等于上述冻结值 → **来源副本与恢复结果一致**（provenance 可核对；副本本身非“原始不可变介质”） |
| Packet v2（恢复后） | tree `4300a7c67a031136cd52f46b44d325db7a5dd14df82f409d25d6a2247737c1f6`；manifest sha256 `fe45d7602bd7a115cfdc3dd3a85e889c0f7b4fa642c03a54717c06f0bcf403a9`；hashes sha256 `e7a67c77b8e213fac32cb4aabeae56075dcf4982c0281479fae25cca1c4bdddb` | 独立 verifier（Reviewer 自建 `scripts/g4r_review/r_rev5_packet_verifier.py`，**非 Owner 实现**）在恢复后路径运行：**exit 0 / status=PASS / issues=[] / mutation_undetected=[]**；43 files / 0 symlink / payload 40 / hashes 41；`impl_git_commit=d33e0aa…`、`rootfs_sha256=25491e45…` |
| 备份 tar 内容 | 28,133 entries；含 v2 Packet 116 entries、`security/rootfs`+`foundation/deps` 8,408 entries；**`review-packet-g4f` 相关 0 entries** | 备份为恢复后状态；不能用于恢复 v1 |

---

## 4. 根因与直接命令（`LEAD_REPORTED`；本 Agent 未独立复现）

**直接命令（按 Lead 报告）**：

```bash
# 事故动作（危险，禁止模仿）
rm -rf /tmp/at-f4-clean
# 其下存在 bind mount（子挂载）：
#   /tmp/at-f4-clean/artifacts  ==  bind  /root/Autonomous Teacher/artifacts
# rm -rf 递归跨越挂载点删除目标树内容；最终 rmdir 因挂载仍忙 EBUSY
```

**根因链**：

1. **bind mount 被放在待删除目录之下**：`/tmp/at-f4-clean/artifacts` 是对主仓库 `artifacts/` 的 bind mount；
   删除父目录时 `rm -rf` 会**进入子挂载**继续删除，而不是只删除挂载点目录项。
2. **删除前未检查挂载点**：未使用 `findmnt -T`/`mountpoint`/`findmnt -R` 预检子挂载；无“挂载点禁止 `rm -rf`”
   的硬规则或包装脚本。
3. **`artifacts/` 为 gitignored**：不在 Git 历史中，误删后**不能**用 `git checkout/restore` 恢复；
   关键证据（Packet、L2 运行、账本副本）只存在于该目录。
4. **备份缺位/滞后**：事故前没有独立于 `artifacts/` 的离线/只读备份；事故后才有恢复态 backup tar。
5. **`/tmp` 承载持久证据**：把 bind mount/临时清理目录与长期证据路径混放，放大了清理操作风险。

---

## 5. 影响面与恢复结果（按组件；`MEASURED_20261121`）

恢复后 `artifacts/`：**23,345 files / 918 MB**（`du -sh`）。组分：

| 组件 | 恢复后文件数 | 来源（`LEAD_REPORTED`）与 provenance | 状态 |
|---|---|---|---|
| `security/rootfs` | 5,748 | `/tmp/at-g4f-review/artifacts`（2026-11-19 副本）+ worktree 副本；canonical hash 已核对 | **RECOVERED_VERIFIED**（内容 = 冻结值；provenance = 副本） |
| `foundation/deps` | 1,061（`foundation` 共 1,086） | 同上；canonical hash 已核对 | **RECOVERED_VERIFIED** |
| `review-packet-g4r-v2-…` | 43 files / 0 symlink | worktree `g4r-packet-final` 副本；manifest/hashes/tree 与 Reviewer 登记一致；独立 verifier PASS | **RECOVERED_VERIFIED**（独立 verifier PASS；timestamp 为恢复后） |
| `g4h0` | 175 | worktree `m0-g4h0/artifacts/g4h0` 副本；两处 `find -exec sha256sum \| sort \| sha256sum` 摘要相等（`f1e028cb…`） | **RECOVERED_VERIFIED**（副本摘要相等） |
| `security/`（22 个顶层文件 + 5,748 rootfs + probe-input 等） | 5,813（含 rootfs） | `/tmp` 副本；`frozen-*.sha256`/`environment.txt`/logs 为副本，**provenance 非原始** | **PARTIAL**（内容与副本一致；不能证明与事故前原始字节一致） |
| `g4/c` | 13,246 | 多个 worktree 副本合并（`g4r-phase2` 等） | **PARTIAL**（完整性不可证明；`g4` 下仅 `c/` 有内容） |
| `g4r` | 2,982（`final-prep` 100 / `integration` 2,712 / `integration-regressions` 8 / `logs` 35 / `r0` 5 / `r1` 21 / `r2` 27 / `r4` 11 / `registry` 63） | worktree 副本部分合并 | **PARTIAL**（完整性不可证明；事故前集合更大/不同，无权威清单） |
| `g4f` | **0**（空目录） | — | **LOST**（G4-F 原始运行证据未见可恢复副本） |
| `g4` 其他子目录（如 `d/`、`e5/`） | **不存在** | — | **LOST/UNKNOWN**（原 G4-D/E5 运行证据未见恢复） |
| `review-packet-g4f-e7d92967…`（**v1 Packet**） | **不存在** | 全盘 scoped 搜索无副本；backup tar 0 entries；`/tmp/at-g4f-review` 无 packet 目录 | **`LOST_IN_INCIDENT_20261121`** |
| 顶层 symlink | `g3a-provider-bridge`、`g3c`、`g3d` 三个 symlink **自指并悬空**（target = 自身路径；`test -e` = false） | 恢复合并产生或未正确重建 | **RESTORE_ANOMALY**（待人工确认；非安全证据） |

**v1 缺失的搜索证据（本记录实测，scoped）**：

```bash
ls -d /root/Autonomous\ Teacher/artifacts/review-packet-g4f-*      # 无匹配（exit 2）
find /root /tmp /var/tmp /opt /srv -name "review-packet-g4f-*" 2>/dev/null   # 0 行
tar -tf /root/a-next-artifacts-restored-20261121.tar | grep -c review-packet-g4f  # 0
```

> 说明：不做全盘逐 inode 恢复（无可用副本时无意义）；上述 scoped 搜索与 backup 检查已覆盖本机已知副本与备份。

---

## 6. 不可恢复/损失清单（正式登记）

| ID | 损失 | 级别 | 说明 |
|---|---|---|---|
| L-01 | **v1 Packet 原始字节**（`artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99/`，原 177 files / 0 symlink） | **LOST_IN_INCIDENT_20261121** | 全盘 scoped 无副本；backup tar 无该目录；**禁止**生成新包冒充 v1；仓库文档中记录的 `manifest 4aed2a92…`、`hashes 421b07ae…`、`177 files/173/173` 仅为 `DOC_RECORDED`，**不再可作为本地可复核证据** |
| L-02 | `artifacts/g4f/**` G4-F 原始运行证据（f2/f3/f4/f5/f6 等） | **LOST**（恢复后 0 files） | 旧 G4-F 证据包与部分 L2/账本原始数据不再本机可用；文档/Reviewer 报告文字仍保留 |
| L-03 | `artifacts/g4/{d,e5,...}` G4-D watchdog/E5 运行证据 | **LOST/UNKNOWN** | 仅 `g4/c` 部分恢复；G4-D/G4-E 原始 L2/absence/探针证据未见副本 |
| L-04 | `artifacts/g4r/**` 原始运行证据（事前一等公民） | **PARTIAL** | 恢复 2,982 files（来自 worktree 副本合并）；**完整性不可证明**，不得把恢复集合当“原始完整证据” |
| L-05 | `artifacts/security/**` 部分原始 provenance | **PARTIAL** | `frozen-*.sha256`/`environment.txt`/logs 恢复自 `/tmp` 副本；内容等于副本，但“原始性”不可证明 |
| L-06 | 其他 `artifacts/` 历史组件（若存在而未被任何副本覆盖） | **LOST/UNKNOWN** | 无完整事故前清单（gitignored），无法逐项确认 |
| L-07 | 三个顶层 symlink 悬空 | **RESTORE_ANOMALY** | 不构成安全证据；不影响 rootfs/deps/packet 已验证项 |

**关键限制**：backup tar 是 **19:56:30Z 恢复后**快照（含恢复后的 v2 Packet/rootfs），**不是事故前备份**；
不得把它描述为“事故前完整备份”，也不能从中恢复 v1。事故前无独立只读备份 → v1 无恢复路径。

---

## 7. 影响与失效声明（对既有文档结论；不改旧字节，仅在本文件声明）

### 7.1 v1 Packet 相关结论一律失效

自本事故起，任何“**v1 Packet 未改写 / 可核验 / 全量一致**”的表述**不再成立**，统一记为
**`LOST_IN_INCIDENT_20261121`**（原字节丢失，无法复核；仅有 `DOC_RECORDED` 哈希）。受影响的既有文档段落
（**旧字节不在本任务修改范围**，此处仅登记失效）：

| 文档/行 | 原表述（事故前有效） | 事故后状态 |
|---|---|---|
| `docs/A_NEXT_BASELINE.md:105-106` | v1 Packet manifest/hashes 实测哈希（`4aed2a92…`/`421b07ae…`） | 该“实测”为事故前读取；现 **`LOST_IN_INCIDENT_20261121`**，不可再复核 |
| `docs/A_NEXT_BASELINE.md:137`（A0-04） | “v1/v2 Packet、G4-F 旧件、G4-R Review 字节与登记值一致” | v1 部分失效 → 由 `A_NEXT_BASELINE_ADDENDUM_V2.md` 更正为 `PARTIAL/LOST`（不修改本行） |
| `docs/A_NEXT_REVIEW_STATUS_RECONCILIATION.md:197` | v1（G4-F，未改写）manifest/hashes | 改为 `LOST_IN_INCIDENT_20261121`（见 `…_V2_ADDENDUM.md`） |
| `docs/REVIEW_G4R_INDEPENDENT.md:48,98-99,250,276,319` | Reviewer 在**审查时点**确认 v1 Packet 未改写 | 历史结论审查时点有效；**当前不可复核**；不得再引用为“现状可验证” |
| 其它 G4-R/Review 文本中“v1 未改写/旧 Packet 保持”类表述 | — | 同上：chronological 有效、当前不可验证；统一加 `LOST_IN_INCIDENT_20261121` 注释 |

### 7.2 A4/L2/环境身份

- **rootfs/deps**：恢复自**经哈希验证的副本**，canonical 哈希 = 冻结值。可继续作为“内容身份”依据，但必须
  注明 **provenance = 恢复副本**（非原始介质）；不得写“全程 NO_DRIFT”。
- **Stage 身份**：Stage 目录位于 `artifacts/g4/c/stages/…` 等恢复路径，**必须独立重算/复核**后才能用于
  A4/L2；旧 Stage 引用的证据集合已部分丢失。
- **Packet v2**：恢复后独立 verifier PASS（43/0/40/41、tree/manifest/hashes 一致、11/11 mutation 检出，
  issues=[]）。但：**不得声称“自冻结以来字节从未被触碰/未恢复”**——它是从 worktree 副本恢复的；
  只能说“恢复后内容与冻结 manifest/hashes 一致，且独立 verifier PASS；恢复后 timestamps 不具证明力”。
- **G4-R Review 的 65 行矩阵/Reviewer 证据**：`docs/` 内 Git 跟踪文件完整（未受事故影响）；但行内引用的
  `artifacts/g4r/**` 原始证据已 **PARTIAL**，因此“可由原始证据本地复现”的范围缩小；row 级可用性见
  `A_NEXT_REVIEW_STATUS_RECONCILIATION.md`（历史）与新 addendum。
- **A0-04（Packet/Review 冻结）**：因 v1 字节丢失 → `PARTIAL/LOST`（由 v2 addendum 更正）；v2 自身 PASS 保留。

### 7.3 不得淡化

- 这不是“无影响的小清理”：**确实丢失了冻结 v1 Packet 原始字节与部分 G4/G4-F/G4-R 原始证据**，且无事故前
  备份；任何“已全部恢复/无损失”表述均不成立。
- 这不是安全漏洞/Key 泄漏：事故不涉及真实 Key/Provider/HTTP、不涉及 Git 跟踪源码/文档/矩阵字节。

---

## 8. 人类需知项与待决策（Agent 不代签）

| ID | 事项 | 状态 | 需要人类决定 |
|---|---|---|---|
| H-01 | 接受“v1 Packet 永久丢失、不得再作为可核验冻结物”的事实 | `PENDING_HUMAN_ACTION` | 是否将 v1 标记为作废、后续只以 v2/新版本为新身份 |
| H-02 | 是否接受 G4-F/G4-D/G4-E 部分原始证据丢失对 G4-H1/G5 前置的影响 | `PENDING_HUMAN_ACTION` | 重跑取证 / 明示接受残余 / 阻断相关门 |
| H-03 | 是否接受 rootfs/deps “恢复副本” provenance，或要求从更权威介质重建 | `PENDING_HUMAN_ACTION` | 内容哈希已验证，但原始性不可证 |
| H-04 | 备份策略：恢复后 tar 是否作为正式备份、是否另做离线/只读副本 | `PENDING_HUMAN_ACTION` | tar sha `11172f02…` 已记录；需人类确认保管位置与周期 |
| H-05 | A-PR0/A-NEXT 既有结论更正（v1 LOST、A0-04 降级） | 本文件登记 + v2 addendum | 由维护者/Reviewer 确认更正生效 |
| H-06 | 事故是否需升级为更正式事件报告/复盘 | `PENDING_HUMAN_ACTION` | 由维护者决定是否对外/对审计披露 |

---

## 9. 预防措施（强制建议；后续任务落地）

1. **禁止对挂载点执行 `rm -rf`**：任何递归删除前必须 `findmnt -T <path>` 且
   `findmnt -R <path>`（检查**子挂载**）；发现挂载 → 先卸载或改路径，禁止删除。
2. **禁止在 `/tmp` 下创建指向长期证据目录的 bind mount**；需要只读视图用 `cp -a` 副本或只读 bind 并命名
   带 `DO_NOT_DELETE`/记录在停机清单中；清理脚本必须显式排除已知挂载路径。
3. **删除前 dry-run + 摘要确认**：先用 `find … -maxdepth`/`du -sh` 列出目标，人工确认后再删；关键路径使用
   受审包装脚本（内置挂载检查与白名单拒绝）。
4. **关键操作前后 hash 复核**：删除/移动/恢复前后对 `rootfs`/`deps`/关键 Packet 计算 canonical hash，
   不一致即 STOP。
5. **离线/只读备份**：对 gitignored 证据（Packet、L2 账本副本、Review 证据）定期 `tar` + sha256 + 异地/只读
   保管；事故前必须有**事故前**备份（18:00/19:00 等时间点），而不是只在恢复后备份。
6. **证据路径与临时清理分离**：长期证据不放 `/tmp`；`/tmp` 清理任务只处理 `/tmp` 自身普通文件，不跨挂载。
7. **记录清理操作**：所有清理命令进审计日志（UTC/argv/操作者/前后 `findmnt` 输出）。

---

## 10. 复现/复核命令（供审计者）

```bash
cd "/root/Autonomous Teacher"
# 1) 当前挂载与目录状态
findmnt -T /tmp/at-f4-clean; ls -la /tmp/at-f4-clean
# 2) rootfs/deps canonical hash（预期分别为 25491e45… / e07729d7…）
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/foundation/deps . | sha256sum
# 3) Packet v2 独立 verifier（预期 exit 0 / status PASS / issues [] / mutation_undetected []）
PYTHONPATH=src python3 scripts/g4r_review/r_rev5_packet_verifier.py \
  --packet artifacts/review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539 \
  --expected-impl-sha d33e0aabd1714a486325b745c436cb59855d6539 --out /tmp/verify.json
# 4) v1 缺失（预期无输出/0）
ls -d artifacts/review-packet-g4f-* 2>/dev/null
find /root /tmp /var/tmp /opt /srv -name "review-packet-g4f-*" 2>/dev/null
tar -tf /root/a-next-artifacts-restored-20261121.tar | grep -c review-packet-g4f
# 5) backup tar SHA（预期 11172f02…）
sha256sum /root/a-next-artifacts-restored-20261121.tar
# 6) 恢复清单
find artifacts -type f | wc -l; du -sh artifacts
```

---

## 11. append-only 规则与版本记录

- 本文件 v1 为事故后首次记录；后续补充（如更精确时间、第三方复核、人类决定）**只在文件末尾追加**，
  不改写既有字节。冻结 CSV/Packet/旧 Review/既有 A-NEXT 文档字节均不由本文件修改（v2 更正另立新文件）。
- 若发现本记录与事实不符：追加勘误并注明「本文件 §x 的表述被更正」，不得静默改写。

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-20T20:05Z | 初次记录：事故时间线/根因/命令、恢复结果与哈希、v1 LOST 与部分证据损失、影响与失效声明、人类待决、预防措施、复核命令 |

## 12. 不主张 / STOP

- 不主张事故已完全恢复（`PARTIAL_RECOVERY`）；不主张 v1 Packet 可核验（`LOST_IN_INCIDENT_20261121`）；
  不主张 G4-F/G4-D/G4-E 原始证据完整；不主张任何门通过、部署、Live 或 Key/Provider 行为。
- 不主张本文件替代人类事故报告/正式复盘；不代填写任何 ACCEPT/APPROVED。
- **STOP**：等待维护者按 §8 决策；后续 A4/L2/A6 任务必须以本记录与 v2 addendum 为输入。
