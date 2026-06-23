# geo/temporal 重排放在深度阶段（而非快速阶段）

> Status: **Accepted**（G2b）。偏离方案「快速阶段：校准→geo/temporal 重排→决策」的一个工程取舍。

**背景**：

方案的识别适配层设计四段：校准 → geo/temporal 重排 → 决策（accept/rollup/escalate）→ 输出。重排按本地出现频率（`P(species|cell,week)` 先验）重加权候选。但 geo/temporal 重排需要 **Bird Context**（本地频率），而 context 是**异步 HTTP**（eBird/iNat/taxonomy + 缓存/限流）；快速阶段是**秒级同步** 202 路径。把异步 HTTP 塞进 202 会拖垮延迟或频繁降级。

同时，深度阶段（`advance_deep`）在 G2a 已经为「本地稀有度叙事」**取过一次 context**。

**决定**：

geo/temporal 重排放在**深度阶段**，复用 `advance_deep` 已取的 context（`make_geo_temporal_reranker(ctx)` 重排 snapshot 的 candidates，再喂给 Story）。快速阶段保持同步：端侧 Top-K **只做校准 + 决策**，不依赖 context。

**后果**：

- 快速阶段 202 不被异步 HTTP 拖；深度阶段 Story 的候选按本地频率重排（识别叙事更准）。
- **代价**：快速阶段的决策（尤其 `escalate` 触发付费识别后端）**不享受**本地频率重排——它基于校准后的端侧分数。可接受：校准（temperature scaling）已处理端侧过自信这一主要失真；本地频率重排的主要价值在 Story 候选排序，而非召回兜底决策。
- 若将来要让 escalate 决策也吃本地频率，需把 context 预取/缓存进快速阶段（届时重开本 ADR）。

**否决**：

- 快速阶段 `await` context（贴合方案原意，但 202 引入异步 HTTP，慢/降级，违背秒级同步契约）。
- 预加载本地频率表进快速阶段（避开 HTTP，但要额外的 region 级频率表加载/刷新机制，MVP 过重）。
