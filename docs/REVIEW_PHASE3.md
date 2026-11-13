# 第三阶段独立审计 — task18

## 1. 结论与基线

2026-11-13 UTC，reviewer在task17完成后get/claim task18；只修改本审计、最终报告必要增量与新raw evidence，未修改实现/测试/上游/生产Gate/Adapter，未在宿主运行项目controller或probe、未传engine socket给容器、未读取/注入真实Key、未调用模型/Session/prompt。

**新增、限定范围的实证通过：同一锁定SDK executable配合精确只读native cache可真实initialize-ready/观察registered schemas=[]/graceful exit0；严格本地OCI manifest pin的实际OS负向命令和Dockerfile candidate元数据target可用。整体仍DECISION PENDING / Live BLOCKED。** 不扩大为完整H1/E1/E2/E3/E5，不把镜像命令冒充ContainerRunner.run()生命周期，不把save/hash冒充离线load/跨机迁移。

| 证据轮次 | 实现 / 已独立观察的范围 |
|---|---|
| 首轮 | `d5db491bf3299c14b6af98f5cbe952ce56a1a991`：146 Python+8插件；E1-02当时NOT RUN |
| 第二阶段 | `c155789557e525925435e7f8a8bf573856d80311`：235 Python（含89专门子集）+8插件；离线E1-02 PASS；默认无cache SDK initialize BLOCKED/cleanup PASS |
| 第三阶段 | **`5df4f3bdbecdf0683533ef7f0a176513713436cd`**：独立241 Python（含89子集）+8插件；新ROcache startup子集、exactimage OS/candidate build及安装回归PASS |

[第三阶段owner manifest](<../artifacts/phase3-integration/manifest.json>) SHA `f4021242729f03ffe8ed86bb783d88192515e03f80ea7185b08d4c910d03df60`；本轮独立[manifest](<../artifacts/reviewer-phase3/manifest.json>)、[证据摘要](<../artifacts/reviewer-phase3/evidence.sha256>)与完整argv/UTC/exit/stdout/stderr另存。首轮和phase2的[REVIEW](<REVIEW.md>)/[REVIEW_PHASE2](<REVIEW_PHASE2.md>)、manifest与raw产物不倒填、不覆盖。不同轮次和89/241重叠范围不能累计成新测试总数。

## 2. 独立核验的源、环境与身份

- 84项公开输入在工作树、Git归档final-stage、冻结Git对象逐文件匹配；31个owner产物/日志摘要匹配。[source-image-check](<../artifacts/reviewer-phase3/source-image-check.log>) 保留结果。
- Git diff确认相对phase2，`src`、plugin实现/锁、Python锁与项目依赖定义均未改变；生产Runner/Gate/Adapter不变。本轮可执行增量为6个local-pin参数化测试；Dockerfile变化为状态注释，candidate指令未改。文档更新不是实现安全准入。
- [environment-check](<../artifacts/reviewer-phase3/environment-check.log>) 独立重算：共享Node/Python rootfs `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`；Python deps `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`；Node deps `026a7a156830f102cea936bd6836d8f675d36f650ad5935cceb332f7ade292d2`。
- 独立Python-only clone当前归一化树为 `e680bbe32f75253b87bd5123c0327272d1c46d80d166125f5fdee04e54579d7f`；**它不是**共享25491树，也不是原始导入tar/不可变image layer。native stage整树无排除归一化摘要 `c063c129475eb14267de957e3cc9eec30f425fe1b44d004a1a977d1b5e665ef3`。
- `stage.sha256`是归一化tar stdin流摘要，`-`不是普通文件名；本轮按正确算法重算，不执行错误的逐文件`sha256sum -c`。task17的误用失败与修正保留在其manifest，不改写成从未失败。[native-delivery-check](<../artifacts/reviewer-phase3/native-delivery-check.log>) 独立核对delivery/per-file证据以及stage流摘要。

所有新生成执行均使用禁网、无代理/环境继承、uid/gid65534、cap-drop ALL、no-new-privileges、只读root/输入、无socket/private mounts、受限CPU/PID/内存/墙钟的容器。`/tmp`和`/work`始终noexec/nosuid/nodev。Python/SDK512MiB、Node构建1GiB/heap768MiB；真正候选OS命令256MiB。没有为成功放宽root/privileged/noexec或增加可写可执行mount。

## 3. 独立执行的完整回归

| 检查 | 独立实际结果 | 原始证据 |
|---|---|---|
| exact62d OCI中全unit+integration | **241 passed in1.67s，0 skipped，exit0**；包含实际OSprobe与6个local-pin用例 | [tests](<../artifacts/reviewer-phase3/tests.stdout.log>) |
| E1-02专门子集 | **89 passed in0.26s，exit0**，包含于241 | [dedicated](<../artifacts/reviewer-phase3/dedicated_e1_02.stdout.log>) |
| Ruff / standalone E1 JSON脚本 | All checks passed / 结构校验、错误与有界Mock retry断言PASS | [lint](<../artifacts/reviewer-phase3/lint.stdout.log>) / [probe](<../artifacts/reviewer-phase3/probe.stdout.log>) |
| 共享Node rootfs插件 | strict tsc/copy exit0，**8/8 PASS**；genuine Cordis registry，不是模型工具能力 | [plugin](<../artifacts/reviewer-phase3/plugin.stdout.log>) |
| exact OCI中独立重建wheel | tmpfs中构建exit0，SHA仍 **`89768d4769795a09dbcc9405def464796aec40ee5fc0faac68a756790c2ac8f7`** | [build](<../artifacts/reviewer-phase3/build.stdout.log>) |
| exact OCI中真实uv安装 | cwd/work，无源码mount/源码PYTHONPATH；inspect/smoke/paired/report(id+latest)及E1包API/脚本全通过 | [installed](<../artifacts/reviewer-phase3/installed.stdout.log>) / [安装E1证据](<../artifacts/reviewer-phase3/public/e1-02-installed.json>) |
| 同原binary SEA四成员比对 | 4项bytes/size/hash/equality PASS，summary PASS；仅version命令 | [native proof](<../artifacts/reviewer-phase3/native_proof.stderr.log>) |
| 新ROcache原样SDK probe，无preload | initialize-ready、registered schemas[] marker、graceful0、无效握手与缺binary清理PASS | [SDK raw](<../artifacts/reviewer-phase3/sdk_native.stdout.log>) / [语义摘要](<../artifacts/reviewer-phase3/sdk_native-semantic.json>) |
| 旧无cache配置新control | **仍initialize BLOCKED、cleanup PASS**；outer0仅为诊断完成 | [unseeded control](<../artifacts/reviewer-phase3/sdk_unseeded_control.stdout.log>) |
| literal audited image OS命令 | exit0，OS_NEGATIVE_ASSERTIONS_PASSED；独立精确名称ps exit0/空 | [image OS](<../artifacts/reviewer-phase3/image_os_negative.stdout.log>) / [absence](<../artifacts/reviewer-phase3/image_os_negative.absence.log>) |
| Dockerfile candidate元数据target | 本地base64c、pull never/network none、3个FROM参数固定digest、timestamp0；5条candidate指令exit0，重建同62d/config56db | [candidate build](<../artifacts/reviewer-phase3/candidate_metadata_build.stdout.log>) |

10个owner集成case独立重放，另加SEA只读身份proof和旧无cache差分control；这些operation数不是新增pytest数。所有原始argv与各case result记录分别归档，owner测试时长没有复制成独立时长。

安装stdout的5个固定白名单公开payload只用可信jq/base64解码，核长度/SHA，不执行数据。新的[JSON](<../artifacts/reviewer-phase3/public/experiment.json>)/[SQLite](<../artifacts/reviewer-phase3/public/experiment.sqlite3>)/[comparison](<../artifacts/reviewer-phase3/public/comparison.md>) 对应实验 `mock-53e08131-f028-43b4-901b-1fa5eb03234d`，与owner不同；仍20×2公开Mock、synthetic $0.030316、API调用0，不是真模型费用或隐藏评估。

## 4. 原始SDK executable与native精确证明

已完整读 [SDK_NATIVE_DIAGNOSTIC](<SDK_NATIVE_DIAGNOSTIC.md>)、原样probe-final/matcher/patch/observer以及loader的cache/integrity关键实现。独立实际使用原binary SHA **`1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`**，未换成系统DSH或npm distribution。

1. 在该SEA executable进程中以`NODE_OPTIONS=--require=/probe/match-embedded.cjs`仅执行`--version`；matcher只读public `__pkg_manifest__`/`__pkg_archive__`，按compression=2作Brotli解压，并逐byte比较四成员。不是用非SEA rootfs Node冒充embedded资产。
2. 4项独立exact结果：loader25080 bytes / SHA`6d83f4e5426895d40820acf507146226a893c5aefba00a08bf0884446160049e`；loader metadata840 / `a8ae0ae29211fc65fb482502081f70bae242404f042ddf1091b439471cffae3e`；native metadata733 / `3c00dc0affa1e17a5ce682a818c56bb60aa792f5a6ae6fb731a7338102832225`；native295392 / **`40c34d27d8339e246a8f7415a06152935496cdc06555ea8fce0e052011acc70f`**。另以官方0.1.9原始tar成员SHA与stage候选逐项匹配，见[official-native-candidates](<../artifacts/reviewer-phase3/official-native-candidates.log>)。
3. SEA manifest SHA`7ac45c7a47d27cc84d2ccc609039c43db9ffdecc0b2ac399c31c2174c881dcc6`、archive SHA`d9ce86f8342cc61b3c411f3cef2eb91ea213473d074e0a96e99d85a93e050978`独立一致。它们证明指定成员精确匹配，不杜撰完整二进制Git build commit。
4. loader原[cache实现](<../artifacts/sdk-native/stage/candidates/loader/lib/index.js#L31-L92>)支持NARB_NATIVE_CACHE_DIR，已有cache只有与embedded source SHA一致才复用，原native binding validation未改。新位置是只读/probe内mode0444的匹配文件，不是可写可执行目录、模块解析hook或dlopen补丁。
5. **最终成功启动在另一新容器、没有NODE_OPTIONS/preload**。probe显式清空parent env，仅加入官方NARB cache配置；实际mountinfo证明/probe、/deps、/ ro，/tmp和/work noexec。真实SDK initialized=true、子进程活着、真实observer发出`SDK_PROBE_TOOL_REGISTRY []`且显式断言；正常close后原runtime exit0、proc清、线程停、waitpid无children。实际maxTokens0产生JsonRpcError并清理，missing executable产生FileNotFoundError并清理。

旧无cache新control也仍失败，故不能把旧BLOCKED历史改成“当时其实通过”。task15 formatting-only诊断（owner执行、本审计核读）展开了具体临时cache路径的`failed to map segment from shared object`与独立MODULE_NOT_FOUND fallback；本轮精确ROcache控制证明兼容加载方案，而不泛称任意ABI/权限失败都已解决。

**覆盖仅限第三方SDK无Key启动/registered-definition inspection/关闭和初始化负例子集。** 没有Session，不存在per-agent/per-step resolved ToolSet证据；没有模型、工具调用、真实usage、Session持久化/恢复或生产Adapter调用。原sdk-minimal底层policy仍标danger-full-access；本次OS隔离+禁工具不使其自动成为有凭据可信profile。完整H1/E1/E2/E3与授权仍未满足。

## 5. 本地OCI身份、实际OS命令与不可外推项

已完整读 [LOCAL_OCI_VALIDATION](<LOCAL_OCI_VALIDATION.md>)、命令DATA、53行probe及5个假/公开host paths，逐项核exactargv。候选输入目录真实路径固定，只有两个普通0644公开文件、目录0755，无symlink；未挂controller源、grader、真实private标签或engine socket。外部launcher仅人为假Key，容器env断言证明没有KEY/TOKEN/SECRET名称继承。

| 对象 | 独立核验身份 |
|---|---|
| imported base manifest / config | `64c125c83fa76c2f92c9f004aceea2ff4d7aac07f80297668ab7fe0c550110b0` / `c83e44ab5b5dffc3b048ad33ccbb567c3955e6a634b2fbc3956057233969e896` |
| **执行candidate manifest** / config | **`62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b`** / `56db1e2ad5ab29d3f39304d4fc9d0584d90e6bb90ffb657f31f3c5b77f9a7715` |
| raw tar / uncompressed layer | `aed8d7ef3f3c7fbabb601ed99d5e705e39dc1f779c8486f1865e340dfba94641`，独立cmp完全相同 |

独立official inspect确认manifest/config/RepoDigest、USER65534、Entrypoint、工作目录、仅3项非secret image Env、Volumes=null及layer。用原严格qualified `name@sha256:62d...`、pull never执行；没有把config ID/浮动tag当manifest。六项新测试只验证本地pin接受与非法tag/config/malformed等拒绝，Runner实现未放宽。

实际OS命令为手工literal可信engine CLI，不eval或host import项目代码。只改独立name与external clean-engine HOME证据路径；所有candidate参数/挂载/限制相同。outer20s/engine10s，mem/swap256MiB/pids32/CPU1、nofile64、IPCnone、日志关闭、禁网/只读/cap0/nnp、两个16MiB noexec tmpfs、一个只读public input。实测假Key/双home日志/假private标签/controller源不可读，socket不可见，根/usr/input写入受阻，scratch可写，网络受阻；实际cgroup为268435456/32/100000 100000。退出后独立精确name `ps --all`查询0且空。

独立candidate target构建使用最小Dockerfile上下文，跳过未用stages；只有五条元数据指令（缓存命中），新reviewer tag解析到**同62d/config56db**。没有执行uv/npm依赖target。本轮还独立`podman save --format oci-dir --uncompressed`保存该exact candidate，核index→manifest→config/layer字节与filename SHA一致，并与原raw tar cmp；见[OCI content check](<../artifacts/reviewer-phase3/oci-content-check.log>)。

必须保留以下NOT RUN边界：

- **ContainerRunner.run()真实controller subprocess/timeout/cleanup生命周期没有端到端执行**，只做mock回归和手工engine OS命令。不能为补齐在宿主运行未审controller或给候选engine socket。
- **offline load/另一engine/跨机原qualified pin往返没有运行**。save/blob hash只证归档字节；接收端RepoDigest关联、media重编码、元数据与行为未证。普通gzip导出base的另一manifest不替代本次执行pin。
- Dockerfile `python-test`/`plugin-test`依赖target仍NOT RUN；node build是在已有共享rootfs内，不是这两个target构建。
- 资源设置与负向读取/写入/网络探针通过，不等于本轮在image上重跑所有OOM/PID耗尽/timeout恢复攻击；此前rootfs资源证据仍限定原配置。

## 6. 剩余工程与最终判断

此次没有发现需要owner改实现的新确定性缺陷；未修改或通过放宽标准解决问题。新增证据明确关闭了特定ROcache启动与local-image命令/candidate-build缺口，不能仍笼统记为全未测，也不能外推完整产品能力。

后续仍可无Key推进：真实SDK/RPC的显式offline-test-only provider、Session/工具/恢复/中断测试；公开pre-stream预算桥的reserve-before-dispatch/deny/retry/compaction/Judge/concurrency/no-usage/crash/transport上界；独立受控测试平面下的Runner生命周期；离线依赖target与独立OCI接收端roundtrip。H7的公开hooks仍只是静态路径，Files内部同stream重POST与extension异常omit的缺口未因native ready而自动消失。

独立人类授权/受保护凭据与可信部署、生产安全registry、真正private评估权限、外部Live watchdog、真实模型/usage/版本/费用与全部强制Live验收仍待实现/验证。**保持DECISION PENDING，不签发GO/CONDITIONAL GO，也不因先前环境阻塞擅判DSH不可修复NO-GO。** 所有reviewer独立命名容器已由官方engine查询确认absence，84项源输入/共享与独立树摘要再次匹配，前两轮raw/manifest校验通过，生产实现与既有审计文件未变，git diff --check通过。见[final integrity](<../artifacts/reviewer-phase3/final-integrity-check.log>)、[历史保护检查](<../artifacts/reviewer-phase3/final-check.log>)与[reviewer manifest](<../artifacts/reviewer-phase3/manifest.json>)；新reviewer image tag刻意保留为证据，不是残留运行容器。
