# 基底迁移：移除 vendored nanobot，转自建 AgentRuntime + LiteLLM（spike-gated）

> Status: **Accepted（方向）**；实施 **gated on spike** —— 自写薄 agent loop 跑通 Nature Chat 多轮对话即全面迁移，否则回退保留 nanobot。
> 若实施完成，本 ADR **supersedes [ADR-0001](0001-vendored-nanobot-fork.md)**（vendored nanobot fork），并取代 [ADR-0012](0012-model-router-backend-litellm.md) 的 Proposed 状态（LiteLLM 已选定）。

**背景**：

MVP（S1–S13）+ 生产化（S14–S20）交付后盘点 birdbot 对 nanobot 的实际依赖，收窄得很厉害——主链路骨架（ingress/db/workflow/识别/context/router/隐私/观测/日报聚合）全是自建；nanobot 真正被用的只剩：

- **AgentLoop**（薄门面 #2 + 开放层 Nature Chat 的多轮工具循环）— 唯一不易替代的部分；
- Tool 基类 + entry_points、`Schema` 校验、CronService — 浅依赖、轻替代；
- provider 层 — S18 已决定换 **LiteLLM**（深度阶段 `OpenAICompatStoryLLM` 其实早已直连 OpenAI SDK，不走 nanobot provider）。

grill 评估：去 nanobot 的**唯一真障碍是 agent loop**，而其核心是 `LLM → tool_calls → 执行 → 回灌 → 直到 final` 的循环（#9/#27 spike 已展示形状），可薄自写。BirdBot 已大量自建，再自建一个薄 agent runtime 与项目基因一致，换取**全自主、无 vendor fork 维护负担、依赖图清晰**。

**决定**：

- 迁移到**自建 `AgentRuntime` + LiteLLM**，移除 vendored `nanobot/`。替代映射：
  - provider 层 → **LiteLLM**（多 provider/路由/成本，EU 区域硬约束 + 能力断言 + 拒绝 unimpl 仍留 Model Router 层）；
  - `AgentLoop` → 自建 **AgentRuntime**（多轮工具循环 + 会话历史，状态落 Postgres）；
  - `Tool` 基类/entry_points → 自定义 Tool 协议；
  - `Schema` 校验 → pydantic / jsonschema；
  - `CronService` → croniter（nanobot 内部也用它）/ APScheduler。
- **先 spike**：自写 `AgentRuntime` 让 Nature Chat「它是常客吗」多轮、自主工具编排跑通（真 LLM 经 LiteLLM 验证决策质量，像之前的真冒烟）。
- **spike 成功 → 全面迁移**（机械替换 tool/schema/cron + 移除 nanobot 依赖）；**失败（并发工具/流式/中断/上下文压缩坑多于预期）→ 保留 nanobot，本 ADR 降级为 partial（仅 provider 换 LiteLLM）。**

**否决**：

- 保留 vendored nanobot（大量能力未用，却背 vendor fork 维护 + 上游 diff 包袱；agent loop 自写成本可控）。
- nanoclaw（TS / app 形态 / container-per-agent，[ADR-0011] 已否决）。

**后果**：全自主、依赖清晰、无 vendor fork；代价是中等重写基底层（agent loop 是大头，其余机械）。硬约束延续在自建层：隔离不靠 LLM、可观测一等公民、EU 区域硬约束、关键状态落 Postgres。spike 是不可跳过的 gate——避免在没实测 agent loop 复杂度前就拆基底。
