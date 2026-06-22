# Agent 边界（主链路 Workflow / 开放层 Agent）+ Provider 后端可换；保留 nanobot

重新评估基底（nanobot vs nanoclaw）并澄清 agent 在 BirdBot 的边界。

**背景**：

- 审视已交付的 MVP 主链路（S1–S11），领域代码极少依赖 nanobot——主链路骨架是 birdbot 自建的 Workflow(#5)/ingress/db；nanobot 在主链路只当 provider 层 + cron 触发器 + `Schema`/`Tool` 复用。
- 评估 [nanoclaw](https://github.com/nanocoai/nanoclaw)：TypeScript app + container-per-agent 隔离——与 BirdBot（Python 嵌入式 / 多租户 pool SaaS）三重不匹配。
- 关键澄清：BirdBot 功能分两类——**确定性主链路** vs **开放交互层**（Nature Chat 等）。一刀切"用/不用 agent"是错的。

**决定**：

- **保留 nanobot 为基底**（受控 vendor fork，[ADR-0001](0001-vendored-nanobot-fork.md) 不变）。
- **Agent 边界**：
  - **主链路 = Workflow**（确定性、代码固定每步）：快速识别 / 深度 Story / 日报 / 路由 / 配额。需 LLM 处是**单次结构化调用**，不启用 agent 自主性；骨架由 birdbot 自建 Workflow(#5) 承载。
  - **开放交互层 = Agent**（Nature Chat、跨事件推理、探索追问）：用 nanobot agent loop（`process_direct` 多轮 + 工具集 + 会话记忆 + subagent）。spike（`birdbot/chat/`）验证机制可行——agent loop 自主驱动多轮 BirdBot 工具编排（`device_history` → `bird_context` → 综合答复）。
  - 两者**共用 nanobot 一个基底、两种用法**（主链路单回合 / 开放层多回合）。
- **Provider 后端可换**：业务只认 Model Router([ADR-0007](0007-eu-data-routing.md)/#6) 的逻辑模型名；其下 provider 后端（nanobot provider / LiteLLM / 直连 SDK）是可替换实现，**不锁定供应商**（OpenAI SDK `base_url` / LiteLLM 连 DeepSeek/Qwen/Gemini/本地/OpenRouter 等）。EU 区域硬约束使多 provider 成为**合规刚需**。真要灵活多模型时 Model Router 下接 **LiteLLM** 比 nanobot provider 层更省心——局部可逆决定。

**否决**：

- nanoclaw（TS / 完整 app / container-per-agent，与 Python 嵌入式 / pool SaaS 不匹配）。
- 「BirdBot 不需要 agent / 全面去 agent 框架化」——只对主链路成立；开放层真需要 agent。

**后果**：保留 nanobot 有**积极理由**（开放层 agent loop），非仅沉没成本；主链路对 nanobot 是**浅依赖**（provider 层），经 Model Router 隔离、可换 LiteLLM。**待验证**：开放层接**真 LLM** 后 agent 的自主决策质量（spike 仅用 fake provider 验证了机制）。
