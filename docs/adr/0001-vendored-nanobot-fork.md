# nanobot 基座作为受控 vendor fork

BirdBot 把蒸馏版 nanobot 内核整包 vendored 在仓库根（`nanobot/`，包名 `nanobot-ai`）。

**决定**：将其作为**受控 vendor fork** 维护，而非外部固定版本依赖。默认优先通过应用层扩展（entry_points Tool / Skills / Hook / config / MCP，领域代码放独立 `birdbot/` 包，不落进 `nanobot/agent/tools/`）；但**保留在确有需要时直接修改内核的自由**（例如补结构化 BirdEvent 入口、增加状态机阶段级 hook、修复 `flush_all`/`fsync` 耐久缺口）。

**代价（接受）**：放弃「自动跟进上游」，升级 nanobot 需手动 merge；须维护与上游的 diff 与 patch 记录，避免改动失控。

**否决**：外部固定版本依赖（方案 §6 K1 选项 A）——因为团队预期会需要改内核行为，钉死外部依赖会让那些改动无处落地。
