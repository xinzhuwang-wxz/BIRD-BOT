# Model Router provider 后端：LiteLLM（提案 · 待确认）

> Status: **Proposed**（S18 / #38，HITL 架构决策；待 review 确认后转 Accepted 并实现适配器）

Model Router([ADR-0007](0007-eu-data-routing.md) / #6) 下层 provider 后端选型。[ADR-0011](0011-agent-boundary-provider-backend.md) 已倾向 LiteLLM；本 ADR 正式化权衡与推荐，供拍板。

**选项**：

- **A · nanobot provider（现状）**：Anthropic 原生 + OpenAI-compat 基线。但 OpenAI-compat 被 Anthropic 自称**非生产级**（`response_format`/`tools.strict`/缓存被静默忽略），factory 对未知 backend **静默 fallthrough**（#6 实地发现，已在 Model Router 层加护栏）；多 provider 路由/成本跟踪/catalog 需自建。
- **B · LiteLLM（推荐）**：100+ provider 统一接口 + 内置 fallback/路由/成本跟踪/Model Catalog；方案 §71/§165 早点名「路由维度与 LiteLLM 高度吻合、可镜像其 Catalog」；活跃维护。代价：新增 `litellm` 依赖。
- **C · 直连 SDK**：最轻，但多 provider 路由/回退全自建。

**推荐 B（LiteLLM）**：作 Model Router(#6) 之下的**可换后端**——业务仍只认逻辑模型名（fast-vision/deep-reasoning/structured-json），**EU 区域硬约束 + 调用前能力断言 + 显式拒绝 unimpl backend 仍在 Model Router 层（LiteLLM 之上）**，不锁定供应商（ADR-0011）。多 provider 覆盖 + 成本跟踪现成，省自建；OpenAI-compat 的非生产级坑由 LiteLLM 的成熟适配规避。

**待确认（HITL）**：是否引入 `litellm` 依赖；确认后实现 LiteLLM 后端适配器接进 Model Router + 真冒烟（DeepSeek/Doubao 经 LiteLLM）复验，逻辑模型名→真实供应商映射不变。

**后果**：+`litellm` 依赖；Model Router 上层接口不变（后端可换）；nanobot provider 仍可作 fallback/共存。EU 区域硬约束与显式拒绝 unimpl 不下放到 LiteLLM，保持在 Model Router 层。
