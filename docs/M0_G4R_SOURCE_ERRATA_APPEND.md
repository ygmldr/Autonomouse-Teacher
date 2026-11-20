# G4-R — Source errata append（P2-02 / P2-07 证据一致性）

- 文档性质：**append-only** 勘误与来源说明；不重写历史报告、不改旧 46 行矩阵、不改旧 Packet 字节。
- 依据：G4-R 执行计划 §7.2；G4-F 独立复核 `docs/REVIEW_G4F_INDEPENDENT.md` §11 P2-02/P2-07、
  `docs/M0_G4F_REVIEW_ERRATA.md` §4 P2-02/P2-07。
- 产出范围：仅本文件 + 新 v2 Packet 构建器/验证器；旧证据只读。
- 日期（UTC）：2026-11-20。

## 1. P2-02 — F2-07 证据路径纠正

### 1.1 已确认事实（历史，不改写）

- 旧 G4-F 矩阵 `F2-07` 行引用 `artifacts/g4f/f6/integration/f2/tool-window.json`，该路径**不存在**。
- 实际历史文件为 `artifacts/g4f/f2/tool-window.json`（F2 owner run，G4-F 期间生成）。
- 结论本身（F2 工具面/title fallback）可由 F6 summary 与 Reviewer 独立 Tool run 交叉验证；这是
  **证据路径错误**，不是结论被推翻。
- G4-F 归档约束只允许修改 `REV-01..REV-05` 五行，因此 `F2-07` 行在归档中被要求逐字节保持原样。

### 1.2 G4-R 处置

1. **原始 46 行矩阵不修改**（保持冻结字节）；本勘误仅作引用与纠正说明。
2. G4-R 的新矩阵/新报告**不得**跨目录引用旧 `artifacts/g4f/...` 来充当新运行证据；它们必须引用
   本轮新采集的 `artifacts/g4r/...` 证据（新 case ID、新命令、新 UTC、新 exit）。
3. 若需要说明历史 F2-07 结论，只允许在文档中以“历史路径/历史证据”引用，并明确标注
   `HISTORICAL_REFERENCE_NOT_A_G4R_RUN`，不得复制旧文件到 `artifacts/g4r/` 伪装成新运行。
4. 新证据路径的物理存在性由集成/Matrix Owner 在最终矩阵生成前逐项检查；本勘误不伪造路径。

## 2. P2-07 — 同一次 LiveGate.inspect 的 reasons 交叉引用

### 2.1 已确认事实（历史，不改写）

- 旧 G4-F Packet 中 `env/zero-key.json` 只列 1 条 LiveGate reason，而 `manifest.json` 与
  `review/livegate.json` 列 4 条；三者均为 `BLOCKED`，属**证据一致性瑕疵**。
- 该问题不构成 LiveGate 放行或状态改变；历史 Packet 保持冻结、不原地修改。

### 2.2 G4-R v2 设计（不硬编码“永远四条”）

v2 Packet 只允许**一次** `LiveGate.inspect()` 的原始结果作为唯一 reason 来源：

1. Builder 接收单个 `--livegate-snapshot <json>`；该文件 schema 为
   `m0.g4r.livegate-snapshot/v1`，必须包含 `live_gate="BLOCKED"` 与非空 `reasons` 字符串列表。
2. Builder 将该原始 JSON 原样写入 Packet 的 `identity/livegate.json`，并在 `manifest.json` 的
   `live_gate` 块记录：
   `status="BLOCKED"`、`snapshot_path="identity/livegate.json"`、`reason_count=<实际长度>`、
   `reasons_sha256=sha256(canonical(reasons))`（canonical JSON：sort_keys、紧凑分隔符）。
3. `env/zero-key.json` 与 `review/livegate.json` **不复制 reason 数组**，只记录
   `snapshot_ref="identity/livegate.json"` 指向同一原始 JSON。
4. Verifier 读取该唯一 snapshot，重算 `reason_count` 与 `reasons_sha256` 并与 manifest 比较
   （逐元素相等的摘要判定）；同时检查所有 payload JSON 中的 `snapshot_ref` 必须指向同一路径。
   任何一处不一致 → `LIVEGATE_CROSSREF_MISMATCH` FAIL。
5. 数量不硬编码：builder/verifier 都从 snapshot 实际列表推导；测试使用 3 条原因（非 4 条）的
   synthetic snapshot 证明没有硬编码，篡改 snapshot 或 crossref 文件都会 FAIL。

### 2.3 残余

- snapshot 本身仍由 Owner 在采集时生成；本轮只保证“同一 snapshot 在 manifest/env/review 之间
  元素级一致”。真实 LiveGate 入口仍恒 `BLOCKED`（`gates.py` 未修改），不构成本轮 Live 授权。
- 最终 v2 Packet 的 crossref 结果需在 Lead 冻结 impl SHA 后由阶段二构建并记录；届时本文件
  不追加伪造数字。

## 3. 不可变性声明

- 旧 `artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99/` 未被修改：
  本轮测试仅读取其 `hashes.sha256` 计算前后 SHA-256 一致性，未写入、未重打包。
- 旧 `docs/REVIEW_G4F_INDEPENDENT.md`、旧 `docs/M0_G4F_REVIEW_ERRATA.md`、旧 46 行矩阵
  `docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv` 均未修改。
- 状态常量不变：`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
