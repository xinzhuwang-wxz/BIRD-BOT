# BirdBot

面向智能喂鸟器的云端 AI Agent 服务的领域语言表。本文件只是术语表（glossary），不放实现细节、不当 spec。

## Language

**内核 (Kernel)**:
vendored 在 `nanobot/` 的蒸馏版 nanobot agent 核心，作为受控 vendor fork 维护（见 [ADR-0001](docs/adr/0001-vendored-nanobot-fork.md)）。
_Avoid_: nanobot（指代不清时）、framework、base

**应用层 (Application Layer)**:
内核之上承载全部 BirdBot 领域逻辑的代码（独立 `birdbot/` 包），如识别适配、Bird Context、Workflow Runtime、多租户。
_Avoid_: 业务层、业务代码（混用时）

**访鸟事件 / BirdEvent**:
IoT 平台就一次鸟类来访提交给 BirdBot 的统一结构化事件（媒体引用、检测框/Top-K/置信度、设备/用户/粗位置、历史摘要）。指真实来访这件事，也指承载它的结构化消息。
_Avoid_: message、payload、observation

**快速阶段 (Fast Stage)**:
访鸟事件进来后秒级同步返回的处理阶段，产出物种候选、可信度、最佳帧。
_Avoid_: phase 1、同步阶段

**深度阶段 (Deep Stage)**:
快速阶段之后异步进行的处理，产出行为理解、当地稀有度解释、Story。
_Avoid_: phase 2、异步阶段

**租户 (Tenant)**:
隔离、计费、配额与数据驻留的**顶层边界**。通常是集成 BirdBot 的 IoT 平台/品牌方；D2C 路径下也可能是终端用户账户——具体身份待上市策略定，隔离模型对两者兼容。
_Avoid_: 客户、账号

**用户 (User)**:
实际体验 AI 赋能功能的终端人（喂鸟器拥有者），归属于某个租户。
_Avoid_: 账户、客户

**设备 (Device)**:
单台智能喂鸟器，归属于某个用户/租户。
_Avoid_: feeder（中英混用时）、终端

**多租户上下文层 (Tenant Context Layer)**:
应用层承担的租户隔离与归因机制（内核三维原语为零，见 [ADR-0004](docs/adr/0004-tenant-isolation-pool-bridge.md)）：Postgres RLS + 向量库一租户一 namespace + `(tenant,skill,model)` 配额 + tenant 维度成本日志。租户上下文只在确定性组件（Workflow/Skill/Tool）间传递，**绝不让 LLM 承载隔离边界**。
_Avoid_: 中间件、auth 层（混用时）

**租户信封 (Tenant Envelope)**:
鉴权流水线解析出、贯穿一次请求所有确定性组件的不可篡改租户身份（至少含 `tenant_id`，通常含 `user_id`/`device_id`）。派生会话键 `tenant:{tid}:user:{uid}:device:{did}`，并据以设置 DB 的 `app.current_tenant`。
_Avoid_: token、claims、上下文（泛指时）

**行级安全 / RLS**:
Postgres 行级安全：业务表带 `tenant_id`+索引、`ENABLE`/`FORCE ROW LEVEL SECURITY` + 策略 `USING (tenant_id = current_setting('app.current_tenant', true))`；业务以**非 owner 角色**连接，请求入口设 `app.current_tenant`。漏写 `WHERE tenant_id` 也被强制过滤（fail-closed：未设租户 = 零可见）。见 [ADR-0009](docs/adr/0009-persistence-asyncpg-raw-sql.md)。
_Avoid_: 权限、ACL

**pool 隔离 / bridge**:
默认隔离模型（[ADR-0004](docs/adr/0004-tenant-isolation-pool-bridge.md)）：全租户共享一套服务与库、按 `tenant_id` 隔离（pool），成本最优；架构预留 bridge（高合规/大客户退化为独立 schema 或独立向量 index + BYOK）。
_Avoid_: 共享/独占（不加限定时）

**可重入 step / durable execution**:
Workflow Runtime 的执行单元（[ADR-0002](docs/adr/0002-workflow-on-postgres.md)）：步骤先 journal 再执行，输出落 `workflow_steps`；进程崩溃重启后已完成步骤**回放而非重跑**。每步 `start_to_close` 超时 + 有限重试（指数退避，区分可重试 429/5xx/超时 与不可重试 4xx/校验失败）。
_Avoid_: task、job（泛指时）

**幂等键 (Idempotency Key)**:
`tenant+device+event_id` 派生的去重标识，贯穿 ingress（重复提交返回同一 job）与 workflow（同 `workflow_id` 步骤幂等回放），达成 exactly-once 业务效果。
_Avoid_: 去重 ID、主键

**transactional outbox**:
解业务写与外部回调的双写不一致（[ADR-0002](docs/adr/0002-workflow-on-postgres.md)）：事件行与业务写**同事务**提交进 `outbox`，独立 relay **至少一次**投递、消费者按 `dedupe_key` 幂等去重。
_Avoid_: 消息队列、MQ（泛指时）

**位置三层降级 (Location Three-Tier)**:
位置精度分级（[ADR-0007](docs/adr/0007-eu-data-routing.md)，GDPR 数据最小化）：`raw` 不持久化（瞬时入口）/ `internal` 5–20km 网格（仅供稀有度）/ `public·log` 城市级（展示/日志）。**先降精度再跨境**；与敏感物种、PII 同归统一脱敏层。
_Avoid_: 坐标、定位（不加限定）

**留存 TTL / DSAR**:
各类数据（位置/媒体/事件/会话记忆）定留存 TTL + 到期清理任务（purge 用 superuser 跨租户扫）；DSAR 按 `tenant/user/device` 级联删除/导出（走 tenant_scope，RLS 保证不跨租户）。面向欧盟硬要求。
_Avoid_: 删除、清理（不加限定）

**识别后端 (Recognition Backend)**:
给识别适配层做**物种分类**的专用视觉模型/API（第三方可商用 vision API、SpeciesNet 或自建分类器）。与推理/叙事用的 LLM 是不同的层。
_Avoid_: 模型、provider（本项目「模型 / provider」专指 LLM 层）

**置信度校准 / Calibrator**:
对端侧 Top-K 的过自信 softmax 做**温度缩放**（按模型/物种粒度学 T）：**先校准再设升级阈值**（[ADR-0008](docs/adr/0008-recognition-backend.md)）。神经网络分数系统性过自信，不校准直接设阈值会失效。
_Avoid_: 归一化、置信度（不加限定时）

**识别适配层 / Recognition Adapter**:
快速阶段消费 Top-K 的四段（SpeciesNet 范式）：校准 → geo/temporal 重排 → 决策（接受 / **taxonomic rollup** 回退到属/科 / **升级**触发付费后端）→ 输出候选+证据+决策。read_only。
_Avoid_: 分类器（那是识别后端）

**帧评分 / Frame Scorer**:
从帧序列选**最佳帧**（NIMA 美学 + BRISQUE/锐度/运动模糊）：特征由普通程序/专业模型算、本层组合打分；缺媒体降级为无最佳帧。LLM 只收 3–8 张精选帧。
_Avoid_: 选帧、截图

**Bird Context Service / 数据源模式**:
当地鸟类上下文的唯一受治出口（[ADR-0005](docs/adr/0005-ebird-compliance-source-mode.md)）：持唯一 API key（不下发租户/设备）、按 region+date 缓存+限流、「来源×用途×授权」矩阵 + **商用拦截**（未授权前 eBird/iNat 不进付费路径）+ 强制署名。数据源模式 `auto|ebird-only|non-ebird-only` 显式可调试，当前模式与任何降级/熔断/额度耗尽**埋点可见、绝不静默**（[ADR-0006](docs/adr/0006-observability-first-class.md)）。
_Avoid_: eBird 客户端（指代整体时）、数据源（不加限定）

**稀有度标签 (Rarity Label)**:
由当地频率映射的物种标签——常见 / 季节访客 / 近期罕见（COMMON/SEASONAL/RARE）。喂给 geo/temporal 重排与稀有度叙事；稀疏格点平滑，**别压没当地数据的真实罕见种**。
_Avoid_: 频率（指标签时）

### 能力分层（idea §4 四分法）

**Agent**:
由 LLM 驱动、做智能决策的角色（选能力、融合证据、生成解释与 Story）。MVP 用一个共享 Agent + 多 Skills，不上多 Agent。

**Workflow**:
由**代码固定**的主链路控制流（快/慢拆分、幂等、超时、有限重试、日报、回调），**不交给 LLM 决定每一步**。
_Avoid_: pipeline（泛指时）、流程

**Skill**:
描述某项领域能力**方法论**的 Markdown 文档（何时用、需要什么输入、如何融合证据、输出结构）。**无强制力**——硬契约/工具白名单/输出 schema/隐私降精度的闸在 Tool 与 Workflow 代码里，不在 Skill。

**Tool**:
确定、可测试的**原子能力**（调识别后端、查 eBird、帧评分、读设备历史、存 Story、发回调…），实现为内部 Python Tool。
