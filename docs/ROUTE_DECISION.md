# Route Decision — PENDING independent human review

本文件是审计记录，不是授权凭据，Agent 修改它不能解锁 Live 或注入密钥。

| 字段 | 基线 |
|---|---|
| requested_model | DeepSeek V4.1 Flash |
| route_id / provider | deepseek-official |
| request model ID | deepseek-flash |
| selection reason | v0.4 默认主渠道；不开展模型选型 |
| model version evidence | 任务书指定服务别名；实际响应型号/请求ID/版本映射 **UNVERIFIED LIVE** |
| human approver / approval date | **NONE / NONE — NOT APPROVED** |
| authentication permissibility | 官方 API 认证流程须维护者确认；未读取或使用任何真实凭据 |
| acceptance scope | 未来获批配置上的 E1、E2/E3/E4 Live；当前全部 BLOCKED |
| fallback | 禁止自动切换渠道/模型 |

## 分渠道状态

| 渠道 | 角色 | 状态与边界 |
|---|---|---|
| DeepSeek 官方 / deepseek-flash | 设计默认 primary，未人工批准执行 | BLOCKED：安全授权/可信控制器/真实模型映射及 Live 验证未完成 |
| OpenRouter / deepseek/deepseek-v4.1-flash | optional，未启用 | NOT TESTED，不影响官方渠道判断；未证明同模型实际版本 |
| OpenCode Go | 仅可选开发订阅调查 | UNVERIFIED 第三方 API 可接入性；不能当作零成本 Runtime API |

当前没有路由切换，没有批准者、批准日期或真实调用证据。替代渠道的成功也不得替代官方渠道结果。若人类维护者今后事先批准切换，必须提供型号与认证允许性证据，并在新主渠道完整重跑 E1 及受影响 E2/E3/E4；不得沿用别的渠道 PASS。

安全批准与路由批准都必须由独立人类操作确认。即便未来文档记录批准，当前代码仍硬拒绝 Live；还需专门工程任务实现并审查受限控制器，而不是编辑此文件开启运行。
