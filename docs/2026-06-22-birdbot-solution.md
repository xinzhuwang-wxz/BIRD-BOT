# BirdBot 最佳实践方案（v1 · 定靶稿）

> 状态：Solution / 定靶输入稿
> 日期：2026-06-22
> 关系：本文是 [`2026-06-22-birdbot-idea.md`](./2026-06-22-birdbot-idea.md) 的「调研 + 基座审计 + 对抗式校验」产物。**idea 不一定对**；本文逐条校验后给出符合最佳实践的目标架构。
> 一句话：方向（分层取舍、识别适配、两阶段异步、Bird Context Service、LLM 不做视频）大体正确；但基座现实、合规红线、多租户/可靠性落地是 idea 低估或漏掉的部分，必须在「定靶」阶段拍板后才进入规划。

---

## 0. 这份文档怎么来的

由 20 个并行 agent 完成：10 维**只读审计**真实的 vendored 基座代码（区分「真实存在 / 被蒸馏删 / 从未有过」），8 维**外部调研**（eBird 授权、市场、开源许可、模型路由、workflow、多租户、识别媒体、隐私），再做**对抗式批判**与**架构综合**。所有结论尽量带 `file:符号` 出处或来源 URL（见附录）。

本文对应四阶段方法论的 **①审计（已完成）→ ②定靶（本文 + 待拍板决策）**。规划/执行在决策敲定后另起。

---

## 1. Zoom-out：基座真实是什么

`nano-bird-bot` 是 nanobot 的**蒸馏轻量版**（已拍平进仓库根，包名仍为 `nanobot-ai`）。审计要点：它是一个**质量不错的可嵌入 Agent 内核**，但**远不是一个 IoT/多租户/工作流平台**。

### 1.1 真实提供、可直接用的「缝」（不 fork 即可扩展）

| 能力 | 真身（file:符号） | 给 BirdBot 的用法 |
|---|---|---|
| 可嵌入 Agent Loop | `nanobot.py:23` `Nanobot`；`loop.py:1726` `process_direct`（比 `Nanobot.run` 多透传 media/tools/ephemeral/on_progress） | 每个处理任务进程内单回合驱动 agent，无需起 bus/channel |
| 8 阶段回合状态机 | `loop.py:76` `TurnState`（RESTORE→COMPACT→COMMAND→BUILD→RUN→SAVE→RESPOND→DONE） | 固定回合流程；含状态追踪 |
| 工具迭代核心 | `runner.py:272` `AgentRunner.run`（"请求模型→执行工具→回填"，与产品无关） | — |
| 生命周期 Hook | `hook.py:31` `AgentHook`（before/after_iteration、before_execute_tools、on_stream、finalize_content 等 9 个钩子） | 观测/计量/输出清洗（**注意：无状态机阶段级钩子**） |
| Tool 插件机制 | `loader.py:68` entry_points `group='nanobot.tools'` + `registry.py:19` `register` | eBird/识别等做成**内部 Python Tool**，零侵入 |
| Skills 文档加载 | `skills.py` `SkillsLoader`（自动发现 `workspace/skills`、frontmatter 触发、always 常驻） | 承载 Skill **方法论散文** |
| Provider/Preset/Fallback | `providers/factory.py` `make_provider`、`fallback_provider.py`（跨供应商回退+熔断）、`anthropic_provider.py`（原生）、`openai_compat_provider.py`（统一基线）、`model_presets.py` | LLM 网关下层 |
| Session/Memory/Goal/Cron | `session/manager.py`、`agent/memory.py`、`session/goal_state.py`、`cron/service.py`（调度持久化 fsync + 重启幂等） | **仅作会话记忆与定时触发**，不作业务状态/工作流 |

### 1.2 基座**没有**或**已被蒸馏删除**（必须 BirdBot 应用层 100% 新建）

- **网络 ingress 全无**：通道（Telegram/Slack…）、WebUI、OpenAI-compatible HTTP server **都已删**，只剩 CLI。→ idea §3/§5 假设的「对外提交入口 / OpenAI-compatible 公共 API 基线」**不存在**。
- **结构化 BirdEvent 入口为零**：SDK 只吃 `message: str` + media 路径（`nanobot.py:71`），无结构化事件直通；富数据只能塞进文本/自由 `metadata` dict（无类型/无版本/字段易漂移）。
- **多租户原语为零**：唯一隔离是扁平 `session_key` 字符串；config 是**进程级全局单例**；Memory/Cron 单 workspace 全局共享。
- **持久 workflow 为零**：Cron 是「可靠调度器」而非「持久化执行引擎」（无 step-journal / 幂等键 / 有限重试 / outbox，单机 FileLock 不支持多副本）；Goal 状态存 `session.metadata`（对话记忆）——**恰恰违反 idea 自己「关键状态不能只存对话记忆」的原则**。
- **识别适配层 / Bird Context Service / 多维模型路由**：基座都无。

### 1.3 工程债清单（high 级摘要，共审计出 69 条）

> 这些是把基座当 BirdBot 地基时的「坑」，已按严重度归档。完整 69 条在审计原始结果中。

| # | 维度 | 高危工程债 |
|---|---|---|
| D1 | sdk/hook | `Nanobot.run` 靠改写**私有共享** `loop._extra_hooks` 注入 hook → **多租户并发会串扰**，且非公开 API 易随上游破裂。**对策：不复用 `Nanobot.run`，改自建薄门面调 `process_direct`，hook 在构造期/按请求注入。** |
| D2 | hook | `AgentHookContext` 不含 tenant/device/session_key → 租户上下文需在 hook 构造时闭包带入、每请求新建实例 |
| D3 | state | `flush_all()` 定义了但**全仓无调用点**，且 `save` 默认 `fsync=False` → 进程被 kill 可能丢最近写（**耐久缺口**） |
| D4 | state | 业务/workflow 状态全堆在无 schema 的 `session.metadata` 自由 dict；**内核无结构化业务实体/工作流状态持久化** |
| D5 | cron | 调度器在应用层**从不 `start()`、`on_job` 从不接线、投递链路无消费者** → 默认是「哑存储」（能写盘回报 Created 但永不触发）；以「定时日报」为卖点是致命缺口 |
| D6 | providers | registry/schema 残留 4 个**无实现 backend**（bedrock/azure_openai/github_copilot/openai_codex），factory `else` 分支会把它们**静默误路由**到 OpenAI-compat → 用错 wire 协议打端点 |
| D7 | ingress | 总线是**无界内存** `asyncio.Queue`（崩溃即丢、无背压、无 ack/重试）→ 不能直接当对外 IoT 事件总线 |
| D8 | config | config 进程级全局单例、数据目录单根、凭据明文散落、模型路由缺 region/合规/价格/延迟维度 |
| D9 | subagent | 子代理运行态**仅内存无持久化**（重启即丢）；`max_concurrent` 默认 1 且全局单值，无 per-tenant 配额 → 单租户深度任务顶满全局名额阻塞所有人 |
| D10 | skills | `allowed-tools` 是「假约束」（validator 认、loader 忽略）；Skill 无 input/output schema、决策全是模型可忽略的散文 → **硬契约/工具白名单/隐私降精度必须下沉到 Tool/Workflow 代码闸** |

---

## 2. 对初步想法的对抗式校验

### 2.1 站得住、保留（idea 最稳的判断）

- **§4/§7 分层取舍**：Workflow=代码固定控制流、不让 LLM 决定每一步（被 Anthropic《Building Effective Agents》背书）；**LLM 不做视频流水线**、只吃精选帧+结构化证据（成本/注意力复杂度/上下文三重论证成立，与 OrniSense 私有视觉模型+LLM 叙事层的业界共识吻合）。
- **§7 识别适配范式**「消费上游 Top-K → 按位置/时间/历史/eBird 重排 → 输出候选+证据+可信度+决策」有成熟先例（Merlin 用 eBird 频率重排、geo prior `P(y|I)×P(y|loc)`、SpeciesNet 的 detector→classifier→ensemble+geofence+rollup）。
- **§8 统一 Bird Context Service**（缓存/限流/分类映射/隐私/单 key 出口）——**全文最稳的架构判断**，被 eBird 1000 req/day 硬额度、key 不可共享、key 持有者对全部使用负责等条款强制要求。
- **§8 三套独立授权边界**（近期 API / Status & Trends / Macaulay Library）+「可访问 ≠ 可商用」的警示准确。
- **§2 第一阶段链路与两阶段快/慢异步**逐环被竞品商用验证；把 ReID/迁徙大数据/商业鸟鸣识别后置符合产业成熟度（ReID 在 Bird Buddy 官方仍标 experimental）。
- **§6 模型路由维度**与 LiteLLM 类网关最佳实践高度吻合（全部可落地）。
- **§3 位置精度分级**与 eBird 敏感物种官方做法（约 325 taxa、400 km² 网格）和 GDPR 数据最小化一致。

### 2.2 必须纠正（按严重度）

| 严重 | idea 问题 | 校正 |
|---|---|---|
| **高** | §5 自称「nanobot 作固定依赖、不 Fork」，但现实是**整包源码已 vendored 进仓库**（`nanobot/` 在根、包名 `nanobot-ai`、§9 自述「轻量版已复制」）——这就是事实 Fork | 二选一**写死纪律**：**(A)** 改为外部 pip 固定版本依赖、业务代码全部迁出 `nanobot/`、只靠 entry_points/Skills/Hook/config/MCP 扩展；**(B)** 承认为受控 vendor fork、放弃「跟进上游」承诺、建 patch+diff 流程。**不要两头都要。推荐 A。** |
| **高** | §8 把 eBird 当随取随用的上下文源，**未点明 BirdBot 是商业 SaaS → eBird API/数据/S&T/Macaulay 默认全禁商用，须先取 Cornell 书面许可** | 列为 **P0 阻断性合规门槛**：上线前邮件 `ebird@cornell.edu` 启动商业许可；未获许可前 eBird 仅内部原型；并行备 iNaturalist 公开记录 + taxonomy(免 key) + 缓存做降级 |
| **高** | §4「围绕 nanobot Cron/Goal 实现 Workflow」——但 Cron 非执行引擎、Goal 存对话记忆 | Cron **仅作日报/聚合触发器**；真正的状态机/幂等/超时/重试/outbox **第一天就建在事务型 Postgres**；Goal 不承担可靠工作流职责 |
| 中 | §1/§2 把 **OrniSense 当独立竞品**、Netvue/Birdfy 当并列三家 | 实为两大阵营：**Bird Buddy（Nature Intelligence）vs Birdfy（OrniSense 是其 AI 层，Netvue 是渠道线）**。差异化收敛到**跨品牌/跨 IoT 中立 + 本地稀有度叙事/证据融合质量**（最佳帧/日报/Story 已被竞品商品化，不是护城河） |
| 中 | §6 把 OpenAI-compatible 当**能力基线** | Anthropic 官方称其兼容层**非生产级**，`response_format`/`tools.strict`/audio/file/缓存**被静默忽略**；Gemini 兼容层仍 beta。改述为「**接入/降级基线（仅文本+基础工具调用）**」，能力关键路径走**原生适配器** + 调用前断言能力 + 调用后 JSON schema 校验 |
| 中 | §6 把 DeepSeek/Qwen/智谱与 OpenAI/Gemini 并列可路由 | BirdBot 面向欧美：欧盟/英国数据流向**无 GDPR 充分性认定的第三国**门槛远高。把「允许目的地区域/合规标签」做成模型注册表**一等字段+硬约束**，默认**禁止** EU/UK 数据流向中国境内端点 |
| 中 | §9 把 pyinaturalist「库 MIT」等同「数据可商用」 | 区分代码许可 vs 数据许可：iNaturalist **CV 模型私有、数据默认 CC BY-NC、条款禁商业 AI/训练**。库仅用于查询公开记录；商业识别后端走可商用方案 |
| 中 | §5 把「OpenAI-compatible API」当现成入口 | 已被蒸馏删除；BirdBot **必须自建 HTTP server 适配层**；清理残留 `ChannelsConfig` 等死配置 |

### 2.3 缺失的关键点（gaps，idea 完全没提）

1. **BirdEvent 结构化契约**：基座入口承载不了检测框/Top-K/置信度/位置/历史。→ 应用层定义**带版本的 pydantic BirdEvent schema** + 序列化层 + 旁路（结构化证据不全过 LLM）。
2. **多租户运行时强制**：idea 只列了三维度，把「列出维度」当「隔离已解决」。→ **三支柱**：Postgres RLS + 向量库一租户一 namespace + 租户上下文只在确定性组件间传递（绝不让 LLM 承载隔离边界）。
3. **吵闹邻居 / 配额 / 成本归因**：pool 共享不等于免费午餐。→ 按 `(tenant, skill, model)` 三元组 Redis 限流（RPM/TPM/Spend/并发），第一天埋 tenant 维度成本日志。
4. **数据留存/删除 + GDPR DSAR**（访问/导出/删除/可携/被遗忘）：面向欧盟是硬要求。→ 位置/媒体/事件/会话记忆各定 TTL + 级联删除 + DPIA。
5. **processor 合规链路**：把含个人/位置数据发往 LLM/识别 API = 交给 sub-processor，**不签 DPA/SCC 即违规**；EU-US DPF 因 FISA 702 续授权有不确定性。
6. **置信度校准**：神经网络 softmax 系统性过自信，**不先做温度缩放校准就设升级阈值会失效**。
7. **可观测性 / 评测（eval）**：多租户需可证明数据去向；识别重排/Story 质量是护城河，需评测闭环。基座 hook 默认 `reraise=False` 会静默吞错。
8. **结果出口 outbox / 幂等 / 回调**：基座总线无 `event_id`/`callback_url`；同步在业务事务里发 HTTP 回调会双写不一致。→ **transactional outbox**（同事务提交、独立 relay、at-least-once + 消费者幂等）。
9. **第三方商用识别 API 的鸟类覆盖/欧美准确率基准**未评测就选型 = 升级形同虚设。

---

## 3. 目标架构（最佳实践）

### 3.1 两层总图

```text
        IoT 平台（成熟）
            │  POST BirdEvent
            ▼
┌─────────────────────────── L2: BirdBot 应用层（新建，独立包，不碰内核） ───────────────────────────┐
│  HTTP Ingress / BirdEvent 适配器  →  Workflow Runtime（Postgres 状态机 + outbox）                  │
│  多租户上下文层（RLS / namespace / 配额 / 成本归因）                                                │
│  识别适配层(Tool)   Bird Context Service(Tool)   LLM 网关/五维路由   领域 Skill 包   观测&回调 Hook  │
│  BirdBot Agent 薄门面 ──调用──┐                                                                     │
└───────────────────────────────┼────────────────────────────────────────────────────────────────┘
                                 ▼
┌─────────────────────────── L1: nanobot 内核（固定依赖，零改动） ─────────────────────────────┐
│  process_direct / AgentLoop  ·  AgentRunner  ·  AgentHook  ·  Tool entry_points  ·  Skills    │
│  Provider/Preset/Fallback  ·  Session/Memory  ·  Cron（仅作日报触发器）                        │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
   识别 API / eBird / Postgres / 向量库 / 大模型 API
```

### 3.2 组件清单

| 组件 | 职责 | built_on |
|---|---|---|
| HTTP Ingress / BirdEvent 适配器 | 接 POST BirdEvent → pydantic 校验 → 幂等键 → 租户解析 → 落库 → 立即 202+`job_id`+`status_url`；序列化为 `process_direct(content+media)` | **新建**（内核无 ingress、无结构化入口） |
| Workflow Runtime | 快/慢拆分、状态持久化、幂等、超时+有限重试、失败降级、日报触发 | **新建**（状态机）；触发器 built_on nanobot Cron |
| 业务状态存储（Postgres） | BirdEvent 全链路状态、识别快照、Story/日报、幂等键、outbox、设备历史；全表带 `tenant_id`+RLS | **新建** |
| 识别适配层 | 消费 Top-K → 置信度校准 → geo/temporal 重排 → 决策(接受/rollup/升级) → 输出候选+证据+决策 | **新建**（read_only Tool + Skill），范式参照 SpeciesNet |
| Bird Context Service | eBird/Xeno-canto/iNat 公共记录统一出口：单 key + 缓存 + 限流 + 分类映射 + 敏感物种粗网格 + 来源/许可字段化 | **新建**（Tool） |
| 多租户上下文层 | 鉴权流水线（认证→租户解析→会话派生→上下文编译）；不可篡改租户信封贯穿确定性组件；密钥按租户作用域+信封加密 | **新建**（内核三维原语为零） |
| LLM 网关 / 五维路由 | 业务只引用逻辑模型名/能力档；真实供应商/重试/回退/熔断/区域过滤下沉；能力注册表 + 调用前断言 + 调用后校验 | built_on Provider/Preset/Fallback + **新建**路由器 |
| 领域 Skill 包 | 物种融合/行为/最佳帧/稀有度/Story/日报的**方法论**（SKILL.md） | built_on Skills（**硬闸不在此，在 Tool/Workflow**） |
| 领域 Tool 插件包（独立 pip 包） | eBird/识别/帧评分/设备历史/天气/保存 Story/回调；子类化 `Tool` + entry_points 声明 | built_on Tool entry_points（**不可落进 `nanobot/agent/tools/`**） |
| 观测&回调 Hook + RuntimeEvent 订阅 | 工具调用审计、usage/成本计量、`finalize_content` 注入署名/AI 声明、订阅 `TurnCompleted` 落库+回调 | built_on AgentHook + RuntimeEventBus |
| BirdBot Agent 薄门面 | 封装 `AgentLoop.from_config + process_direct`（构造期传 hooks + 按阶段换 ToolRegistry + ephemeral + media） | built_on 可嵌入 Loop（**明确不用 `Nanobot.run`**） |

### 3.3 关键链路：BirdEvent 接入 + 两阶段快/慢

- **接入**：IoT POST → Ingress 校验/幂等(`tenant+device+event_id`)/租户解析 → 落库(`queued`) → **202+status_url**。位置入口即三层降级（raw 不持久化 / internal 5–20km 网格 / public·log 城市级）。结构化字段作为识别 Tool 的入参约定，**不全塞进自由文本过 LLM**。
- **快速阶段（秒级、同步 202）**：识别适配 Tool 消费 Top-K → 校准 → Bird Context 取当地 eBird 频率（命中缓存优先）→ geo/temporal 重排 → 帧评分选最佳帧 → 返回候选+校准可信度+最佳帧，落库为深度阶段输入快照。
- **深度阶段（异步、后台 worker、可断点续跑）**：薄门面 `process_direct`（深度 ToolRegistry）+ Skill 做行为理解/稀有度解释/Story；耗时子任务可经内核 `spawn` 子代理执行；每步落库 + 经 **outbox** 回调。
- **日报**：nanobot Cron 定时触发 → 聚合当天事件生成日报 → outbox 投递。
- 每步 `start_to_close` 超时 + 有限重试（指数退避+上限，区分可重试 429/5xx/超时 与不可重试 4xx/校验失败）；幂等键达成 exactly-once 业务效果。

### 3.4 识别适配层（SpeciesNet ensemble 四段）

1. 接收上游检测框+裁剪图+Top-K+置信度+版本（不重做全部推理）。
2. **置信度校准**：温度缩放（按模型/物种粒度学 T，ECE/NLL 评估）——**先校准再设阈值**。
3. **geo/temporal 重排**：`P(y|I) × P(species|cell,week)`（eBird 频率，稀疏格点平滑/补零，别压没当地真实罕见种）→ 当地常见/季节访客/近期罕见标签。
4. **决策**：top-1/top-2 接近或与 geo 先验冲突时 **taxonomic rollup** 回退到属/科/目（输出"可能是 X 类"），并触发升级。升级**只走可商用后端**（Nyckel/Roboflow/MS Custom Vision/自建 EfficientNet-V2），仅会员/不确定/冲突任务在深度阶段异步调用。
- 视频解码/追踪（YOLO+ByteTrack，需跨遮挡 ReID 才用 DeepSORT）/帧评分（NIMA 美学 + BRISQUE/锐度/运动模糊）由**普通程序/专业模型**完成；LLM 只收 3–8 张精选帧/拼图 + 结构化证据。

### 3.5 Bird Context Service

- 持唯一 API key（**绝不下发设备/租户**）；按 `regionCode+日期+物种` 粒度缓存（TTL 数小时~1 天）；全局限流（**远低于 1000 req/day**）；按 hotspot/region 网格合并请求；taxonomy（免 key）长缓存；退避熔断；对齐 eBird 敏感物种名录（约 325 taxa）强制粗网格；**来源×用途×授权矩阵**字段化（可缓存/可展示/需署名/禁商用），并做**商业用途拦截**。
- 降级：额度耗尽/许可未到位时，仅凭 taxonomy + 缓存 + iNaturalist 公开记录提供降级上下文。展示层强制注入 `Source: eBird.org` 署名。

### 3.6 模型路由 / LLM 网关

- 业务只引用**逻辑模型名/能力档**（`fast-vision` / `deep-reasoning` / `structured-json`）；真实供应商绑定、重试、跨组回退、熔断冷却、区域过滤下沉到网关。
- 维护**模型能力注册表**（vision/function-calling/structured-output/audio/prompt-caching/context-window/pricing/**驻留区域/合规标签**，可镜像 LiteLLM Model Catalog + 自有字段）。
- **OpenAI-compatible 仅作接入/降级基线**；结构化输出/缓存/音视频/thinking 走原生适配器；调用前断言能力（不支持就路由原生通道，不发会被静默降级的请求）、调用后 JSON schema 校验+回退。
- **显式拒绝** registry 残留的 4 个无实现 backend（防静默误路由）；`_setup_env` 写进程级 `os.environ` 有多租户 key 串号风险，须按 key 显式传参规避。
- 欧美：EU/UK 数据默认 EU 区域处理或仅向已签 DPA+SCC/DPF 的美国端点；默认禁止流向无充分性认定第三国。

### 3.7 多租户隔离（pool 模型 + bridge 预留）

采用 AWS **pool** 模型（成本最优），但承担其四大代价（noisy neighbor / 成本归因 / blast radius / 合规）并主动抵消；高合规/大客户预留 **bridge**（独立 DB schema 或独立向量 index + BYOK）。运行时三支柱：

- **(a) DB 层 RLS**：所有业务表带 `tenant_id`+索引，进入请求 `SET app.current_tenant`，非 owner 角色连接（漏写 WHERE 也强制过滤）。
- **(b) 向量/记忆 namespace**：一租户一 namespace，每次检索强制 `tenant_id` 过滤。
- **(c) 确定性传递**：从校验过的 JWT 取 `tenant/user/device` 作不可篡改请求信封，只在 Workflow/Skill/Tool 间传递，**绝不让 LLM 承载隔离边界**；每请求构造租户作用域的 ToolRegistry/Hook。
- 会话/记忆/缓存按 tenant 命名空间，禁全局共享键（防 cross-session leak 与 KV-cache 前缀侧信道）。配额按 `(tenant, skill, model)` Redis 桶，fair-share 限每租户 1/N。成本第一天埋 tenant 维度日志 + chargeback。

### 3.8 状态与 Workflow 可靠性

- 关键状态落 **Postgres**（呼应 §4「关键状态不能只存对话记忆」），**不依赖** Goal(`session.metadata`)/Cron(单机 JSON)。
- 内核定位：**Cron** = 可靠调度器（仅日报/聚合触发器，BirdBot 须自接 `start()` 与 `on_job`）；**Goal/long_task** = 会话级 agent 式持续目标（适合开放 Nature Chat，**不跑固定主链路**）。
- Workflow Runtime 实现 **durable-execution**：步骤先 journal 再观察、崩溃回放；幂等键 `tenant+device+event_id`；每步超时+有限重试；**transactional outbox** 解双写；saga 轻量化（多为生成步骤，补偿主要是标记降级/重排队）。
- 演进：MVP 用 **Postgres 状态表+outbox+可重入 step（DBOS-style，运维最轻）**；出现长挂起 workflow/确定性 replay 审计/大量外部 fan-out/单库瓶颈/硬多租多区时，优先迁 **DBOS**（同 Postgres 迁移平滑），再考虑 **Temporal**。

### 3.9 隐私与位置降精度

位置三层降级纳入**统一 per-tenant 输出/日志脱敏层**（与敏感物种、PII 同管）；对持续位置/行为追踪做 DPIA；与所有 LLM/识别 provider 签 DPA+SCC、开 zero-retention/不用于训练、披露 sub-processor。**合规结论需法务确认。**

---

## 4. 开源复用与许可（核验后）

> 原则：**许可清晰且边界独立 → 可依赖/移植；非商业/禁演绎/许可不清 → 只研究思想再净室独立实现。**

| 项目 | 模式 | 许可（核验后） | 要点 |
|---|---|---|---|
| nanobot（轻量版，已 vendored） | dependency | MIT | 须保留 MIT 声明与来源版本号；**建议改为外部固定版本依赖**（见 2.2 高危项） |
| pyinaturalist | dependency | MIT | 仅查公开记录；**严禁**把 iNat 数据/CV 模型用于商业识别/训练 |
| Birding Buddy MCP | port | MIT | TS→Python 是**重写**；eBird/Xeno-canto/OSRM 各自条款独立；key 收敛到 Bird Context Service |
| iNaturalist MCP | port | MIT | 参考 Tool schema/限流（60 req/min）；数据许可独立 |
| google/cameratrapai（SpeciesNet） | port | Apache-2.0（**代码+权重均 Apache-2.0，明确可商用**） | **比 idea 设想更宽松**；可 port ensemble+geofence+rollup；鸟类细分覆盖需评估；留存 Kaggle 模型页 LICENSE 快照 |
| MCP Data Server | study-only | BSD-3 | 后期迁徙分析/DuckDB/Parquet/H3；所查数据集各自许可 |
| BirdLense-Hub | study-only | **CC BY-NC-ND 4.0**（比 idea「非商业或禁演绎」更严：**且**非商业**且**禁演绎，连源码改写再分发都禁） | **只净室重写**，任何代码片段不得入库；落地前逐仓核对 LICENSE（`Gfermoto` vs `AleksandrRogachev94/BirdLense` 归属存疑） |
| BirdNET-Analyzer | study-only | 代码 MIT / 模型 CC BY-NC-SA 4.0 | 代码可借鉴；**商业 Sound ID 不可用其权重**（须采购授权/换可商用模型/仅消费第三方识别结果） |
| Ecology-Harness | study-only | MIT | 仅借鉴 Tool catalog/能力检查/运行轨迹审计思路，**不与 nanobot 合并** |

---

## 5. 合规红线（P0）

1. **eBird 商业许可前置**（阻断性）：付费产品上线前取得 Cornell 书面许可；未获前 eBird 仅内部原型；Bird Context Service 做商业用途拦截；备 iNat/taxonomy 降级。
2. **媒体授权**：Macaulay/S&T 各自独立、禁商用/禁再分发；Story/最佳帧只用**设备自拍**或已签授权媒体，不回链/转存 ML 媒体；展示强制署名。
3. **跨境数据**：EU/UK 数据默认不流向无充分性认定第三国；与 provider 签 DPA+SCC；DPF 视为可变假设备 SCC 兜底。
4. **GDPR DSAR + 留存**：位置/媒体/事件/会话记忆各定 TTL + 级联删除 + DPIA。

---

## 6. 待定的不可逆决策（进入「定靶」必须拍板）

| # | 决策 | 推荐 |
|---|---|---|
| K1 | nanobot 形态：vendored fork vs 外部固定依赖 | **A 外部固定依赖**，业务代码迁出 `nanobot/`，只靠 entry_points/Skills/Hook/config 扩展 |
| K2 | Workflow 引擎：Cron+文件 vs Postgres 自建 vs Temporal | **B Postgres 状态表+outbox+可重入 step（DBOS-style）**；Cron 仅日报触发器 |
| K3 | eBird 商业合规路径 | **并行 A（即发起 Cornell 洽谈）+ 备 B（iNat+taxonomy 降级）**，许可落定前按 C 约束付费路径 |
| K4 | 多租户：pool vs bridge | **B 默认 pool + 预留 bridge**（高合规/大客户退化 silo） |
| K5 | 商业升级识别后端 | 先用真实欧美场景**基准评测**再定，倾向 **A 第三方可商用 API** 起步 + **C SpeciesNet** 作参考/自训基线；**排除 iNat CV 模型** |
| K6 | EU 数据模型目的地策略 | **B 默认仅 EU 端点或已签 DPA+SCC/DPF 美国端点**，路由层硬约束（合规结论交法务） |
| K7 | ingress 形态 | **A+B**：快速阶段 HTTP 同步 `process_direct`；深度/高频走持久化队列（Redis/SQS）；**排除 C**（基座内存总线对外） |

---

## 7. 分期计划（对齐 审计→定靶→规划→执行）

- **P0 审计（✅ 已完成）**：八/十维内核审计 + 八维调研；确认硬约束（无 ingress、tenant 原语为零、无 BirdEvent 入口、无持久 workflow）。
- **P1 定靶（本文 + 决策）**：锁定本架构、`数据源×用途×授权`矩阵 + eBird 洽谈、开源许可分级写入 PR 模板/CI、逻辑模型名+能力注册表 schema、**BirdEvent pydantic schema 草案** + 幂等键 + `session_key` 三维编码约定。→ 产出 `CONTEXT.md` + 关键 ADR。
- **P2 规划**：Postgres schema+RLS+outbox+位置三层/TTL/DSAR；Workflow 状态机定义；领域 Tool 包 entry_points + **最小 Tool 冒烟计划**；Skill 目录+SKILL.md 模板；LLM 网关路由器+Redis 配额+成本日志 schema；部署/多副本调度治理。
- **P3 执行**：entry_points 冒烟 → 识别适配 + Bird Context Tool → Ingress+薄门面+快速阶段贯通(202) → 深度阶段 Story + 日报 Cron 接线 + outbox 回调 → 多租户 RLS+配额+脱敏 → LLM 网关五维路由 → 可观测全链路 → 进程 shutdown `flush_all()`/关键写 `fsync=True`（修内核耐久缺口的应用层兜底）。全程**不改 nanobot 内核**。

---

## 8. 范围

- **MVP**：合规 P0 前置 · entry_points Tool 冒烟基线 · HTTP Ingress+BirdEvent schema · Agent 薄门面 · 快速阶段（校准+eBird 重排+最佳帧）· Bird Context Service · 深度阶段 Story · Workflow+Postgres 状态机+outbox · 日报 Cron · 多租户 pool+RLS+配额+成本 · LLM 网关 · 位置降级/TTL/DSAR/脱敏 · 视频流水线（普通程序）。
- **后置**：个体 ReID（仅留挂载点）· 迁徙趋势（受 S&T 再分发禁令，需单独许可）· 完整 Nature Chat（可借 Goal/long_task）· 商业 Sound ID（须授权/换模型）· Skill 升级为专用 Agent · 对外暴露 MCP Server · 升级专用编排器（DBOS→Temporal）· 企业 bridge 隔离。

---

## 附录：关键来源

- eBird API & 条款：`https://documenter.getpostman.com/view/664302/S1ENwy59` · `https://www.birds.cornell.edu/home/ebird-api-terms-of-use/` · S&T `https://science.ebird.org/status-and-trends/products-access-terms-of-use` · 敏感物种 `https://support.ebird.org/en/support/solutions/articles/48000803210-sensitive-species-in-ebird` · Macaulay `https://support.ebird.org/en/support/solutions/articles/48001064551-using-and-requesting-media`
- 市场：Birdfy/OrniSense `https://www.einpresswire.com/article/880939841/` · Bird Buddy Nature Intelligence `https://www.prnewswire.com/news-releases/bird-buddy-launches-nature-intelligence-allowing-users`
- 许可：GitHub License API（nanobot/pyinaturalist/birding-buddy-mcp/inaturalist-mcp/mcp-data-server）· SpeciesNet `https://github.com/google/cameratrapai`
- 模型路由：Anthropic OpenAI 兼容层 `https://platform.claude.com/docs/en/api/openai-sdk` · Gemini `https://ai.google.dev/gemini-api/docs/openai` · LiteLLM `https://docs.litellm.ai/docs/routing`
- Workflow：Restate `https://www.restate.dev/blog/building-a-modern-durable-execution-engine-from-first-principles` · Temporal idempotency `https://temporal.io/blog/idempotency-and-durable-execution` · outbox `https://microservices.io/patterns/data/transactional-outbox.html` · saga `https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga.html`
- 多租户：AWS pool isolation `https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/pool-isolation.html` · PG RLS `https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/` · cross-session leak `https://www.giskard.ai/knowledge/cross-session-leak-when-your-ai-assistant-becomes-a-data-breach`
- 识别/校准：geo prior `https://arxiv.org/pdf/1906.05272` · 温度缩放 `https://geoffpleiss.com/blog/nn_calibration.html`
- Agent 设计：Anthropic《Building Effective Agents》（workflow vs agent 定义）
