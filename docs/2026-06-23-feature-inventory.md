# BirdBot 功能梳理（G1）— 已实现 vs 预期 · 缺口 + 优先级

> 持续优化 goals 的第 1 个（画地图）。盘点 `birdbot/` 实现，对照方案 + PRD #33 的功能预期。事实出处 `file:符号`。
> 基线：去 nanobot 完成（ADR-0013）、LLMGateway 治理闭环 + 可部署组装根（ADR-0014），with-DSN 165 passed。

## 一句话结论

骨架（ingress/fast/deep/workflow/outbox/digest）+ 治理（LLMGateway）+ 隔离（RLS）+ 持久化 + 隐私都**生产就绪且测试覆盖**。核心缺口是一类系统性问题——**「组件实现了 + 测试了，但没接进生产 pipeline」**。换句话说：能力都在，差最后的**接线**与**自动驱动**。

## 功能矩阵

### ✅ 生产就绪（实现 + 接线 + 测试）
| 能力 | 出处 |
|---|---|
| ingress 202 + 幂等 + job 状态 | `ingress/{app,store,schema}.py` |
| 快速阶段：校准/决策(accept/rollup/escalate)/最佳帧 | `recognition/{calibrator,adapter,frame_scorer,fast_stage}.py` |
| 深度阶段：GatewayStoryLLM + 硬 schema 闸 + 多模态 | `deep/{llm,story,workflow}.py` |
| Workflow runtime：journaling/replay/retry/超时 | `workflow/runtime.py` |
| Outbox：事务性 enqueue + at-least-once relay + HttpDeliver + RelayWorker | `workflow/{outbox,deliver,worker}.py` |
| 日报：聚合 + 幂等 + Cron 触发 | `digest/*.py` + `runtime/cron.py` |
| **治理（ADR-0014）**：LLMGateway quota→route→telemetry→cost，by-construction | `runtime/gateway.py` |
| Model Router：区域硬约束 + 能力断言 + 拒 unimpl backend | `router/{router,registry,region}.py` |
| 租户隔离：RLS（SET LOCAL + FORCE + fail-closed）+ 信封 | `db/pool.py` + `db/migrations/0002_rls.sql` + `tenant/context.py` |
| 观测/配额：telemetry/alert sinks（Logging+List）、quota（内存+Redis fair-share） | `observability/*.py` |
| 隐私：位置三层降级 + redaction + 敏感种 + DSAR + retention/TTL | `privacy/*.py` |
| 组装根：assemble → app + gateway + story_llm + advance + relay_worker | `bootstrap.py` |

### 🟡 已实现但未接进生产 pipeline（**头号缺口类**）
| 能力 | 实现处 | 缺口 |
|---|---|---|
| **fast→deep 自动触发** | `bootstrap.py:Assembly.advance` 就绪 | **无消费者自动驱动**——deep 阶段要手动调 advance；主链路自动贯通的断点 |
| **BirdContextService（本地稀有度）** | `context/{service,sources,models}.py`（eBird/iNat HTTP 适配器 + 源模式 + 商用门 + 缓存/配额 + 署名，全测试） | **`pipeline/orchestrate.py:advance_deep` 硬编码 `"rarity": {}`**——service 从不被调；深度 Story **没有本地稀有度数据**（而稀有度叙事是 BirdBot 卖点） |
| **geo/temporal reranker** | `context/rerank.py:make_geo_temporal_reranker`（按本地频率重排，测试过） | **未注入 fast stage**——`recognition/adapter.py` 默认 `_identity_rerank` stub；真 reranker 在但不在执行路径 |
| **Nature Chat HTTP 入口** | `runtime/agent.py:AgentRuntime` + `chat/tools.py` + 治理（全测试） | **无 `/chat` 端点**——开放层只在 spike 测试里活；主链路 ingress 只有 `/v0/events` |
| chat 工具真实后端 | `chat/tools.py:DeviceHistoryTool/BirdContextTool` | **stub 数据**（mock 访问数/硬编码稀有度）——无真实设备历史/稀有度后端 |

### ⚪ Stubbed / 设计外置（非缺陷，按 ADR）
| 能力 | 说明 |
|---|---|
| 视觉物种分类器 | 设计外置（ADR-0008）：fast stage 只校准注入的端侧 top_k，不自己调视觉模型；识别后端选型是业务门 |
| 帧质量特征（NIMA/BRISQUE） | 外部程序产出，注入 `FrameFeatures`（本层只组合打分） |

### 🔴 合规阻断门（业务/法务，代码动不了）
eBird Cornell 商业许可（ADR-0005 P0）、欧盟 DPA+SCC/zero-retention/DPIA（ADR-0007）、识别后端选型+基准（ADR-0008）。代码侧门控已就位（源模式商用拦截、区域硬约束、位置降级/DSAR/TTL）。

## 缺口清单 + 优先级

**P0 — 接线（组件都有，差接进 pipeline，直接影响「能 work + 卖点」）**
1. **BirdContextService 接进深度阶段** —— 让 Story 有真实本地稀有度（卖点叙事，现在是空的）。
2. **geo/temporal reranker 接进 fast stage** —— 识别质量（reranker 已有，差注入）。
3. **fast→deep 自动触发 worker** —— 主链路自动贯通（advance 就绪，差消费者）。

**P1 — 体验/上线**
4. **Nature Chat HTTP 入口** —— 开放层上线（PRD user story 3）。
5. chat 工具真实后端（设备历史/稀有度）—— 依赖真实数据源就位。

**后置/外置**：视觉分类器（业务门 ADR-0008）、帧特征提取（外部）。
**合规门**：eBird/DPA/DPIA（业务/法务）。

## 对后续 goals 的地图

- **G2「真实生命周期贯通」应扩展**为：P0 三项接线（context + reranker + fast→deep 触发）一起做——这才让「一个真事件产出有本地稀有度的真 Story 并自动投递回调」端到端跑通。这是「真正能 work」的实质。
- **G3「质量 eval 集」**：G2 通后，Story/Nature Chat 有真实输出可衡量。
- **G4「压测」**：G2 通 + 部署目标后。
- Nature Chat HTTP 入口（P1）可并入 G2 或单列。
