# Xero Integration Review

## C1 Connection & Permission Validation

1. 调用 Xero OAuth2 `/connect/token` 接口获取有效访问令牌，确认身份鉴权通过
2. 调用`GET /Xero/Organisation`拉取租户列表，确认目标租户已绑定当前应用
3. 单条试查 A 模块生成的测试发票，确认 Invoice Read 权限正常打通

## C2 Error Diagnosis Tree

- 优先排查 401：检查 Access Token 是否过期、刷新令牌是否有效
- 再排查 403：核对 OAuth scope 是否包含 invoice 相关权限、租户 ID 是否匹配
- 最后排查 404：确认请求环境是沙箱 / 生产、租户 ID 输入无拼写错误

## C3 Incremental Sync Strategy

使用 Xero API 的`updatedAfter`时间游标做分页拉取，本地持久化最后同步水印，每次从水印时间开始拉增量发票，避免全量拉取浪费配额，失败断点自动续传

## C4 Rate Limit Handling

遇到 429 限流时读取响应头`Retry-After`数值，等待对应时长后加随机抖动重试，同时按 Xero 官方并发上限控制请求数，幂等请求冲突、超时这类非限流错误不重试

## C5 Idempotent Create

创建发票时用 B 模块输出的订单 ID 作为 Xero 幂等键，超时后先调用查询接口核对该订单是否已生成发票，存在则直接复用，不存在再补推，避免重复开票

## C6 Observability & Security

全链路植入 traceId 埋点，日志里绝不打印敏感 token 和客户数据，OAuth 密钥存入加密 Vault 并定期轮换，异常时通过 traceId 快速定位链路节点
