# M0 G1-SEC 报告 — 安全/授权/Watchdog 确定性修复（无 Key）

- 任务：`task-60`（v0.6 G1-SEC）；基线 HEAD `92c9f71`；实现 SHA 仍 `87f44e1`；本任务不 commit/stage
- 结论：**A1/A2/A3/A4/A8 五项确定性缺口已修复，fail-first 定向回归与全量 security/sandbox 回归通过；LiveGate 仍恒 BLOCKED，无真实 Key/模型/HTTP，G1/G2 其余项与 Live 仍按 G0 裁定 BLOCKED。**

## 1. 范围与隔离

- 仅改 `src/autoteacher_m0/security/{ed25519,authorization,live_controller,watchdog}.py`、
  `tests/unit/security/{test_authorization,test_watchdog}.py`、
  `tests/integration/sandbox/test_live_controller_no_key.py`（适配 AUTH-08 完整策略）；
  未改 accounting/egress/guard/adapter/gates/LiveGate，未读凭据。
- 所有项目代码/测试只在固定 digest 无 Key 禁网隔离 OCI 内执行（image
  `localhost/autoteacher-local-oci@sha256:62d3569e…64667b`，id `56db1e2a…`；`--network none`、
  read-only、uid 65534、cap-drop ALL/no-new-privileges、pids/mem/cpu 受限；宿主未运行
  pytest/项目 Python/TS）。
- 工作树中 `src/autoteacher_m0/accounting/**`、`tests/**accounting**` 的修改属并行 G1-ACC，
  本任务未触碰、未 stage。

## 2. 逐项 finding / 旧行为 / 修复 / 回归

| ID | Finding | 旧行为（fail-first 证据） | 修复 | 回归 |
|---|---|---|---|---|
| A1/AUTH-02 | 可信公钥准入 | `verify()` 接受 identity/非规范 identity 公钥（构造 `S*B=R+k*A` 签名即可通过）；trusted key 加载只校验 hex | `ed25519.py`：`_decode_point` 强制 canonical（`y<q`、`x<q`、重编码一致）；`is_valid_public_key()` 拒绝 identity/小阶（[8]P=O）且要求 [L]P=O 的素数阶子群；`verify()` 对 A/R 均做 canonical+小阶+子群检查；`authorization._load_trusted_keys` 调用严格准入；保留 RFC8032 正向向量 | `test_auth02_*`（identity/非规范 identity/低阶/ RFC 向量），fail-first 3 failed → pass |
| A2/AUTH-05 | 整数强类型 | `int(...)` 接受 `"10"`、`10.5`、`True` 等（budget max_calls、total_seconds、max_steps、max_dispatch_attempts） | `authorization._require_int()` 用 `type(x) is int`，拒绝 bool/float/str/Decimal/NaN；替换四处强制转换 | `test_auth05_*` 10 参数，fail-first 10 failed → pass |
| A3/AUTH-06 | approver/时间异常未初始化 | 非法 `approver` 进入 except 后 `approver` 未赋值，构造对象时 `UnboundLocalError`（P0 升格） | approver 与时间解析拆开 try；失败分别记 `APPROVER_INVALID`/`AUTHORIZATION_TIME_INVALID` 并置安全默认（`approver=""`、时间=moment），返回 approved=False，不崩溃 | `test_auth06_*` 5 参数，fail-first 2 failed（非法 approver 崩溃）→ pass |
| A4/AUTH-08 | Controller 仅比 host_ports | `live_controller._candidate_violations()` 仅比较 `host_ports`；改 path/method/model/budget/flags 而 host 不变时无违规 | Controller 使用完整 `security.egress.EgressPolicy`；逐字段比较 host_ports/methods/path_prefix/approved_routes/max_tokens/max_attempts/require_reservation/allow_files/allow_images/allow_store，任一不符 append `EGRESS_POLICY_FIELD_MISMATCH:<field>`；仍 inspect-only/恒 BLOCKED | `test_auth08_*` 8 参数，fail-first 8 failed → pass |
| A8/WD-03/04 | 异常/清理路径 | `supervise()` 只在正常结尾调用 cleanup；异常路径 kill 后直接重抛（cleanup 不执行）；cleanup 异常按原异常传播，可能被当作成功/未 BLOCKED | `supervise()` 统一异常/超时/step/dispatch/清理路径：kill 进程树→确认 absence→执行 cleanup；cleanup 异常/超时/返回非 Mapping→`WatchdogViolation`(SECURITY_BLOCKED)；finally 兜底 kill；未知结果不进入下一次计费 | `test_wd03_*`/`test_wd04_*`，fail-first 3 failed → pass |

## 3. 回归与计数

| 运行 | 内容 | 结果 |
|---|---|---|
| fail-first（改前） | `test_authorization.py -k auth02/auth05/auth06` + `test_watchdog.py -k wd03/wd04` + sandbox `-k auth08` | exit 1；**26 failed, 4 passed, 40 deselected**（旧代码失败证据） |
| targeted（改后） | 同选择集 | exit 0；**30 passed, 40 deselected** |
| full security+sandbox（改后） | `tests/unit/security tests/integration/sandbox` | exit 0；**157 passed, 1 skipped**（skip 为既有 `/input` 外部探针契约） |
| Ruff scoped | `src/autoteacher_m0/security tests/unit/security tests/integration/sandbox` | exit 0，`All checks passed!` |
| Ruff repo-wide | `ruff check --no-cache .`（同上固定 OCI） | exit 0，`All checks passed!` |

实现 diff：7 文件，+307/−42（4 security + 3 tests）；既有测试未删除；旧 watchdog 测试
`test_supervise_kills_on_controller_exception` 的旧 RuntimeError 断言按 v0.6 WD-03/04 更新为
`WatchdogViolation` 语义（已迁移为 `test_wd03_cleanup_failure_after_exception_is_security_blocked`）。

## 4. 边界与未做项（不宣称完成）

1. 本 PR 只做离线、无 Key 的确定性修复；**LiveGate/P03/真实 egress/Key/模型/HTTP 仍 BLOCKED**，不签发 GO。
2. AUTH-02 的严格子群检查是纯 Python RFC8032 参考实现；非常数时间、未独立审计；未做侧信道/性能认证。
3. AUTH-08 仍是 inspect-only 策略校验；真实禁止 egress/Key 需要 PR4b/外部代理部署，不在本任务。
4. WD-03/04 只验证 mock/hung 子进程与 fake cleanup；真实容器 cleanup/OS 权限/外部 supervisor 未验证。
5. 未做 G1 其余项（A4/A5/A13 的完整语义）与 G2（A9–A11、broker claim、ADR-002）；未接会计/egress 变更（并行 G1-ACC 负责）。
6. 未改历史证据/manifest；证据见 `artifacts/m0-g1-security/`（manifest/evidence hash）。

## 5. 证据

- `artifacts/m0-g1-security/manifest.json`、`evidence.sha256`、`logs/`（fail-first/targeted/full/ruff 的
  argv/UTC/exit/stdout/stderr）、`image-inspect.json`、`container-absence-after.txt`。
- 验证：`cd artifacts/m0-g1-security && sha256sum -c evidence.sha256`。
- 具体文件 hash 见 manifest 的 `deliverables`；fail-first 日志保留旧代码真实失败，不做覆盖。
