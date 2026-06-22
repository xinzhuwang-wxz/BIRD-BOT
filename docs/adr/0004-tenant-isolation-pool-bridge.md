# 多租户隔离：默认 pool + 预留 bridge

BirdBot 作为共享云服务（不为每用户起完整 Agent 实例）采用 AWS **pool** 隔离模型：全租户共享一套服务与库，按 `tenant_id` 索引/分区，成本最优。

**决定**：默认 pool，架构上**预留 bridge**（高合规 / 大客户 / 品牌方可退化为独立 DB schema 或独立向量 index + BYOK 密钥）。pool 的四大代价用以下机制**主动抵消**，不靠「共享」本身：

- **越权/blast radius** → Postgres RLS（`SET app.current_tenant` + `USING tenant_id = current_setting`，非 owner 角色连接）+ 向量库一租户一 namespace + 租户上下文只在确定性组件（Workflow/Skill/Tool）间传递，**绝不让 LLM 承载隔离边界**。
- **吵闹邻居** → 按 `(tenant, skill, model)` Redis 配额（RPM/TPM/Spend/并发，fair-share 每租户 1/N）。
- **成本归因** → 第一天埋 `tenant_id` 维度结构化成本日志 + chargeback。
- **合规** → 强数据驻留租户退化 bridge。

内核多租户原语为零，全部由应用层承担。当前阶段实现 pool；bridge 待出现企业/合规租户时再落地。

**否决**：纯 pool（无 bridge 退路，将来强驻留客户须重写架构）。
