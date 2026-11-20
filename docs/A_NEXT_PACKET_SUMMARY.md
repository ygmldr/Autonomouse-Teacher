# A-NEXT Review Packet v3 — 构建/校验工具与身份摘要（阶段 1）

- **文档 ID**：`A-NEXT-PACKET-SUMMARY-v3-draft`
- **状态**：`PHASE1_TOOLING_READY`（**不是最终 Packet**；最终 Packet 等 Lead 集成冻结 SHA 后由 F-C 用本工具构建）
- **新身份路径**：`artifacts/review-packet-a-next-v3-<impl_sha>/`（gitignored；**不复用/覆盖** v1/v2 路径）
- **基线**：`work/work/g4r = fd1d3a6`；冻结 impl `d33e0aa`；main `3e7afee`
- **硬约束**：0 真实 Key/Provider/网络/Live；不修改 v1（LOST）/v2 Packet 字节；不修改其它分支/工作树

## 1. 已交付工具

| 文件 | 作用 |
|---|---|
| `scripts/a_next/packet_v3_common.py` | 共享常量、canonical hashing、strict inventory（拒绝 symlink/hardlink/special/sidecar/不安全路径）、canonical JSON/hashes 解析、INCIDENT_20261121 常量 |
| `scripts/a_next/build_packet_v3.py` | v3 builder：身份校验（impl SHA 40hex + git 可选验证；payload content SHA 独立）、staging 严格扫描、frozen rootfs T0/T1、三层写入（payload → manifest → hashes）、自校验后原子重命名发布 |
| `scripts/a_next/verify_packet_v3.py` | v3 verifier：三层 + 全树严格核对、mutation 拒绝、frozen/incident 强制披露校验、expected identity 覆盖、JSON 输出与分类退出码 |
| `tests/a_next_packet/` | 37 tests：正向 build/verify、builder 拒绝、8 类 mutation 必须 FAIL |
| `docs/A_NEXT_EVIDENCE_RECONCILIATION.md` | 证据矩阵 v2 append-only 对账 scaffold（65 旧行 + 19 A-NEXT 行 + Host/OCI 例外 + 事件披露；不预填 PASS） |

## 2. 三层结构与身份分离

```text
review-packet-a-next-v3-<impl_sha>/
├── manifest.json        # schema/identity/frozen/incident/inventory/layers（不含自身 hash）
├── hashes.sha256        # payload/** + README.md + manifest.json（自身除外；固定例外集）
├── README.md            # 用法 + frozen 声明 + INCIDENT_20261121 强制披露
└── payload/**           # 证据 payload（仅普通文件，mode 0444）
```

- `identity.impl_sha`：冻结 git commit（40 hex，权威）；可选 `--repo` 做 `git cat-file -e` 验证并记录 `git_commit_verified`。
- `identity.content_sha256`：**payload-only 内容摘要**（64 hex），由 payload inventory（path/sha256/bytes/mode）计算，与 impl commit 独立；二者被 verifier 强制要求不同（禁止混淆）。
- `layers`：payload（文件数 / tree sha / content sha）→ hashes（条目数 / 覆盖集）→ manifest（schema）。
- `frozen_identity`：`rootfs_sha256_expected`、`rootfs_canonical_t0`、`rootfs_canonical_t1`、`t0_t1_equal`、deps/runtime/stage manifest。提供 `--frozen-rootfs` 时执行 T0/T1 对比；T0 != T1 或 T0 != expected → builder 拒绝（STOP）。
- 最终 Packet 必须带 frozen 快照（`rootfs_snapshot=PROVIDED`）；仅阶段 1 工具自测允许 `NOT_PROVIDED` 的 `phase-1-tooling` 包，verifier 需 `--allow-phase1` 才放行（否则 exit 44）。

## 3. 严格 inventory 与 mutation 拒绝

builder 发布前 + verifier 均拒绝：

| 情况 | 拒绝码 | exit |
|---|---|---|
| 未列文件/目录、缺失 payload、空目录 | `EXTRA_ENTRY` / `MISSING_ENTRY` / `EMPTY_DIRECTORY` | 45 |
| sidecar/junk（`.DS_Store`、`*.swp`、`*~`、`*.tmp` 等） | `SIDECAR_REFUSED` | 46 |
| symlink / hardlink / FIFO/socket/device | `SYMLINK_REFUSED` / `HARDLINK_REFUSED` / `SPECIAL_REFUSED` | 47 |
| mode 变化（非 0444；目录 0555） | `MODE_MISMATCH` | 48 |
| payload/README/manifest 哈希不符、hashes 覆盖/格式/条目数不符 | `HASH_MISMATCH` / `HASHES_*` | 41 |
| payload tree/content sha 不符 | `PAYLOAD_TREE_MISMATCH` / `CONTENT_SHA_MISMATCH` | 42 |
| schema/identity/重复 JSON key/层声明不符 | `SCHEMA_MISMATCH` / `IDENTITY_*` / `DUPLICATE_JSON_KEY` | 43 |
| frozen 声明无效、T0/T1 漂移、T0 != expected | `FROZEN_*` / `ROOTFS_T0_T1_DRIFT` / `ROOTFS_T0_EXPECTED_MISMATCH` | 44 |
| INCIDENT 缺失/被篡改、禁止性声明（global NO_DRIFT / 完整性 / v1 recovered） | `INCIDENT_*` / `CLAIM_*` / `V1_CLAIM_INVALID` | 44 |

## 4. INCIDENT_20261121 — 强制披露（内嵌 manifest/README）

- 2026-11-20T19:53Z 前后 `artifacts/` 被误删，随后从哈希验证副本恢复：
  - 备份 tar：`/root/a-next-artifacts-restored-20261121.tar`，sha256 `11172f0268cdf2dc2bde08e90d9d93c0a444b134f8eaab9a712057c9d5159d42`
  - 恢复后 rootfs canonical = `25491e45…`、deps canonical = `e07729d7…`（与冻结声明一致）
- **v1 Packet 原始字节 LOST**（原路径 `artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99`），不可再独立核验；只保留 SHA-only 历史引用。
- v2 Packet 为 `HISTORICAL_REFERENCE_ONLY`，v3 构建不修改其字节。
- verifier 强制：`claims_allowed.global_no_drift == false`、`claims_allowed.evidence_completeness == false`、`lost.v1_packet.status == LOST_ORIGINAL_BYTES_UNVERIFIABLE`、disclosure 含 "MUST NOT"；任何“v1 已恢复/已核验”“全程 NO_DRIFT”“证据完整”声明 → FAIL。

## 5. 使用方式

```bash
PY="/root/Autonomous Teacher/.venv/bin/python"
# 构建（最终阶段；staging 为待封装 payload 树；impl SHA/rootfs/deps/stage 由 Lead 冻结值提供）
"$PY" scripts/a_next/build_packet_v3.py \
  --staging-dir /tmp/a-next-staging \
  --impl-sha <frozen-40hex> --repo . \
  --out-dir artifacts/review-packet-a-next-v3-<frozen-40hex> \
  --frozen-rootfs "/root/Autonomous Teacher/artifacts/security/rootfs" \
  --expected-rootfs-sha 25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0 \
  --deps-sha e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98 \
  --stage-manifest-sha <final-stage-manifest-sha> \
  --incident-source-tar /root/a-next-artifacts-restored-20261121.tar

# 校验
"$PY" scripts/a_next/verify_packet_v3.py \
  --packet-root artifacts/review-packet-a-next-v3-<frozen-40hex> \
  --expected-impl-sha <frozen-40hex> --json-out /tmp/v3-verify.json
```

## 6. 测试与证据（阶段 1）

- `pytest tests/a_next_packet -q` → **37 passed**；`ruff check scripts/a_next/packet_v3_common.py scripts/a_next/build_packet_v3.py scripts/a_next/verify_packet_v3.py tests/a_next_packet` → **All checks passed**。
- mutation 自测各 ≥1：未列 extra 文件、root sidecar、symlink、hardlink、mode 改动、payload hash 改动、删除 payload、hashes 行篡改、README 篡改、manifest content-sha 篡改、schema 篡改、重复 JSON key、incident 删除、global NO_DRIFT 假声明、v1 recovered 假声明、expected identity 不符 —— 全部被 verifier 拒绝（分类退出码）。
- builder 拒绝：symlink/hardlink/FIFO 暂存、sidecar、非法 impl SHA、content SHA attestation 不符、rootfs T0 不符、输出目录已存在、非新身份目录、未验证 commit。
- 正向：final 包 build→verify PASS；`--allow-phase1` 规则；impl SHA 改变不影响 content SHA（身份分离）；payload 改变 content SHA 改变；git 验证；`--json-out`。

## 7. 阶段 2（等 Lead 通知）必须完成

1. Lead 给出**集成冻结 SHA**（A-PR0..A-PR3/A6 集成后）与 staging payload 清单（证据目录/报告/矩阵/例外文档）。
2. 用冻结 rootfs/genesis（`25491e45…`、deps `e07729d7…`、final Stage manifest SHA）构建 **final Packet v3**；记录 T0/T1、manifest/hashes/tree/content SHA。
3. 在 `docs/A_NEXT_EVIDENCE_RECONCILIATION.md` §7 填入 Packet v3 身份；将 Host/OCI 例外、INCIDENT 披露与矩阵对账一并纳入。
4. 生成 `packet-integrity-report`（如需要）与 Reviewer 请求；Reviewer 独立 verify（`verify_packet_v3.py` + 全树 mutation）。
5. 全流程 0 Key/网络/Live；v1/v2 字节不动；不 push/merge（等 Lead 冻结）。

> 本文件不是最终 Packet、不是 PASS、不改变任何门状态；v1 LOST / v2 historical / INCIDENT_20261121 披露必须在最终 Packet 中保留。
