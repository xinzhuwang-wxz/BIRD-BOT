# 事件入口：HTTP 同步（快速阶段）+ 持久化队列（深度阶段）

IoT 平台经 BirdBot **自建 HTTP server** 提交 BirdEvent（内核已无任何网络 ingress）。

**决定**：
- **快速阶段**走 HTTP 同步——收事件 → 落库拿幂等键 → 调薄门面 `process_direct` → 秒级返回 `202 + status_url`；`session_key` 编码 `tenant/user/device`。
- **深度阶段 / 高频上报**走持久化队列——进队列，后台 worker 消费，配 [ADR-0002](0002-workflow-on-postgres.md) 的 Postgres 状态机 + 幂等键，结果经 outbox 回调回灌。

**否决**：直接用内核无界内存总线对外承接 IoT 事件（崩溃即丢、无背压、OOM 风险）。

**待定**：队列中间件具体选型（Redis / SQS / Kafka）留到 IoT 平台对接约束（webhook 推 / 轮询 / 指定中间件）明确后定。
