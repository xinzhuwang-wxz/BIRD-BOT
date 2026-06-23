# 统一 LLM 调用门面（LLMGateway）：每次 LLM 往返的唯一受治理出口

> Status: **Accepted**（设计经 grill 定稿；实现见 issue）。
> 兑现 [ADR-0006](0006-observability-first-class.md)（观测一等公民）/ [ADR-0004](0004-tenant-isolation-pool-bridge.md)（配额）在生产路径上「定义但未接线」的缺口；统一 [ADR-0013](0013-self-hosted-runtime-litellm.md) 后分叉的多条 provider 调用路径。

**背景**：

去 nanobot 后的架构审查 + `/verify` 实测确认：可观测/配额/成本是「**已定义、零生产接线**」——`CallRecord(` 零构造、`.record(`/`.emit(` 零调用、`QuotaLimiter.try_acquire` 零调用、`litellm.completion_cost` 零调用、`classify_failure` 孤儿（均在 `birdbot/src/` 实测为零生产调用方）。根因：有**三条各自发明的 LLM 调用路径**（`runtime/agent.py:AgentRuntime` 的注入 completion、`deep/llm.py:LiteLLMStoryLLM`、`deep/llm.py:OpenAICompatStoryLLM`），没有一处把 quota/route/telemetry/cost/alert 和一次 LLM 调用绑定。ADR-0006/0004 因此在生产路径未生效。

**决定**：引入 `LLMGateway` 深模块——**completion-level** 的唯一受治理出口。

- **粒度**：completion-level（治理**每一次 LLM 往返**，非整个 agent 任务）。AgentRuntime 一次 run = N 次受治理 completion；深度阶段 = 1 次。理由：telemetry/cost/quota 的自然语义就是 per-completion；call-level 会把 N 次糊成一条、丢粒度。
- **接口**：`complete(*, envelope, logical_model, messages, skill, required_caps=(), region="US", **provider_kw) -> GatewayResult`。后处理（tool_calls 解析 / JSON parse）留调用方。
- **内部编排**：`quota.try_acquire(QuotaKey(tenant, skill, 逻辑模型))`（routing 前拦）→ `router.resolve`（区域/能力/拒 unimpl）→ 计时 → `completion(model=entry.model, ...)` → `completion_cost`/usage → `telemetry.record(CallRecord)` → `release`。
- **失败 = 抛异常，绝不静默**：配额满 → `alert(QUOTA_EXHAUSTED)` + 抛 `QuotaExhausted`；provider 抛 → `classify_failure` + `alert(DEGRADED)` + `telemetry.record(degraded=True)` + 抛 `ProviderCallError(failure_class)`；配置错（routing/unimpl）→ fail-fast。
- **不内置 fallback**：沿 router 链按 `failure_class` 重试（候选 ⑤）是门面的**外层装饰**，不进 ①（保单一职责）。
- **completion 协议 = seam 即逃生通道**：门面持注入的 `Completion`（`async (model, messages, **kw) -> OpenAI-compatible response`）。默认适配器 `litellm.acompletion`；录制适配器 = OpenAI SDK + S14 `RecordReplayTransport`（CI 不打真网，**且经门面 → record/replay 路径也受治理**）。`OpenAICompatStoryLLM` **退役** → 其 OpenAI-SDK 调用降为「录制/逃生 completion 适配器」，JSON parse 留 StoryLLM。litellm 出问题时换 completion 适配器即逃生，仍受治理——保留未受治理旁路是反模式。M3 的双 StoryLLM 适配器分叉就此消解。
- **仅治 LLM**：context 数据源（eBird/iNat）的受治出口仍是 Bird Context Service（`CallRecord.source_mode` 对 LLM 调用填 None）。

**② AgentRuntime 错误处理契约**（开放层 Nature Chat 专用；主链路走 Workflow+StoryLLM 不用 agent loop）：

- 三类工具错误（坏 JSON 参数 / 模型幻觉的工具名 / `execute` 抛异常）→ **转成「错误观察」喂回模型**让其自我纠正 + `alert(DEGRADED)`，而非 crash（现状 `agent.py:61-62` 裸调用会崩）。
- completion timeout 放**门面**（`asyncio.wait_for`），AgentRuntime 不重复。
- 门面抛 `ProviderCallError`/`QuotaExhausted` → AgentRuntime **catch → 返回降级人话 str**（开放层要人话不要异常栈；alert 已由门面 emit）。
- `max_iterations` 耗尽 → `alert(DEGRADED)` + 返回降级人话（**不再静默返回空串**）。
- 降级出口 = **人话 str + alert，不抛、不引入结果对象**（MVP）；调用方靠 alert 感知降级。`alert_sink` 注入 AgentRuntime（与门面**共享同一实例**）。
- 接线：AgentRuntime 构造注入 `gateway` + `logical_model` + `skill="chat"`；`run()` 传 per-request 的 `envelope` + `region`。

**否决的选项**：call-level 粒度（丢 per-completion 粒度/无法单次配额）；失败返回 degraded result（易被当正常 → 静默）；① 内置 fallback（膨胀、违单一职责）；保留 `OpenAICompatStoryLLM` 作未受治理生产逃生通道（违 ADR-0006 一等公民——逃生由 completion 协议提供）；AgentRuntime 降级抛异常（破开放层 UX）。

**后果**：ADR-0006/0004 从「文档承诺」变「**构造上不可绕过**」（任何 LLM 调用不经门面就没有 completion）；M3 双适配器分叉消解；候选 ②（错误处理）、⑤（fallback 装饰）都挂在这个 seam 上；候选 ③（生产组装根）是门面 + sinks + limiter 的唯一注入点。AgentRuntime / StoryLLM 改为持 `gateway`。CONTEXT.md 新增术语「受治理调用 / LLMGateway」。
