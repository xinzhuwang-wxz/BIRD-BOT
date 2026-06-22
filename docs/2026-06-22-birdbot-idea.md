# BirdBot Idea

> 状态：Idea / 方向稿  
> 日期：2026-06-22  
> 目标市场：欧美为主，面向海外市场

## 1. 我们想做什么

BirdBot 是面向智能喂鸟器的云端 AI Agent 服务。

它不取代已有 IoT 平台、端侧检测模型和专业识别模型，而是把设备产生的图片、短视频、声音、检测结果、时间、位置和历史访问组织起来，形成用户真正能理解和持续使用的自然观察体验。

产品能力不止于回答“这是什么鸟”，而是进一步回答：

- 它正在做什么？
- 为什么这个季节会出现在这里？
- 这是常客、首次访客，还是当地少见访客？
- 这一段素材里哪一帧最值得保存？
- 今天的喂鸟器发生了什么值得回顾的事情？
- 多次访问是否可能来自同一只鸟？

BirdBot 对标 OrniSense 一类产品中的 AI 能力，包括鸟种识别增强、行为理解、最佳照片、Story、日报、自然知识问答、个体识别和迁徙趋势，但不会在第一版同时实现全部能力。

## 2. 第一阶段目标

第一阶段优先打通一条完整的“访鸟智能链路”：

```text
访鸟事件
→ 物种识别与证据融合
→ 最佳帧选择
→ 行为理解
→ eBird 本地和季节背景增强
→ Story
→ 每日摘要
```

处理采用两阶段异步模式：

1. 快速阶段在数秒内返回物种候选、可信度和最佳帧。
2. 深度阶段异步生成行为解读、当地背景和 Story。
3. 日报通过定时任务聚合当天事件后生成。

第一阶段暂不以个体鸟 ReID、迁徙大数据、完整 Nature Chat 或全球鸟鸣商业识别作为交付中心，但架构需要允许后续增加这些能力。

## 3. BirdBot 在系统中的位置

BirdBot 是现有 IoT 云平台之后的智能层，而不是新的 IoT 平台。

```text
设备与端侧模型
        ↓
成熟 IoT 云平台
        ↓ BirdEvent
BirdBot Workflow Runtime
        ↓
nanobot Agent + Skills + Tools
        ↓
识别服务 / eBird / 数据库 / 大模型 API
        ↓
结构化结果、Story、日报和通知
```

IoT 平台向 BirdBot 提交统一的 `BirdEvent`。事件可以包含不同丰富程度的输入，例如：

- 原图、鸟类裁剪图、最佳帧候选；
- 短视频、多帧序列或音频；
- 检测框、目标轨迹和端侧 Top-K 物种候选；
- 设备、用户、时间和粗粒度位置；
- 媒体质量、模型版本和置信度；
- 同一设备的历史访鸟记录。

BirdBot 不要求每个事件都提供完整媒体。不同能力根据自身输入要求执行、补充数据或降级。

位置可以在 BirdBot 内部以约 5–20 公里的精度使用，用于区域物种、季节和稀有度判断。对用户展示、日志和敏感物种处理时，应进一步降低位置精度。

## 4. Agent、Workflow、Skill 和 Tool 的分工

BirdBot 采用混合架构。

### Agent

一个共享的 BirdBot Agent 负责智能决策：

- 根据事件和用户请求选择能力；
- 判断是否需要高级识别；
- 在输入缺失时选择降级方式；
- 融合视觉、声音、地点、季节和历史证据；
- 生成行为解释、Story 和自然知识内容。

MVP 使用一个 Agent 和多个 Skills，不采用多 Agent 架构。未来某项能力成本或复杂度明显增加时，可以将对应 Skill 独立为专用 Agent。

### Workflow

产品的固定主链路由 Workflow 保证可靠执行，负责：

- 快速阶段和深度阶段的拆分；
- 状态、幂等、超时和有限重试；
- 定时日报；
- 结果保存和平台回调；
- 失败后的降级。

Workflow 不依赖大模型自由决定每一个步骤。第一版可以围绕 nanobot 的 Cron、Goal 和运行时能力实现，同时增加一层轻量业务状态记录；关键状态不能只保存在对话记忆中。

### Skill

Skill 是 BirdBot 的领域操作方法，描述某种能力：

- 何时使用；
- 需要哪些输入；
- 可以调用哪些 Tool；
- 如何组合证据；
- 什么情况下接受、升级或拒绝结果；
- 输出必须满足什么结构。

候选 Skills 包括物种识别融合、行为理解、最佳帧选择、当地稀有度解释、Story 和日报生成。

### Tool

Tool 是确定、可测试的原子能力，例如：

- 调用图像识别服务；
- 查询 eBird 附近近期记录；
- 选择或评分视频帧；
- 读取设备历史；
- 查询天气；
- 保存 Story；
- 发送结果回调。

高频和核心能力优先实现为 BirdBot 内部 Python Tool。独立外部服务或生态能力可以通过 MCP 接入。BirdBot 后续也可以向其他 Agent 暴露自己的 MCP Server。

## 5. 为什么选择 nano-bird-bot作为基座

nano-bird-bot是nanobot修改的轻量版

- Python SDK 和可嵌入 Agent Loop；
- Skills、Tools 和生命周期 Hooks；
- MCP 客户端；
- Session、Memory 和持续 Goal；
- Cron 和自动化；
- OpenAI-compatible API；
- 多模型 Provider、Model Preset 和失败回退。

BirdBot 采用外围扩展方式，不修改 nanobot 核心、不维护 Fork：

- nanobot 作为固定版本依赖；
- BirdBot 领域代码位于独立应用；
- 通过公开 SDK、Hooks、Skills、Tools 和 MCP 扩展；
- BirdBot 的多租户、任务状态和业务数据不侵入 nanobot 内核。

这样既能快速利用 nanobot 的 Agent 能力，又能持续跟进上游版本。

## 6. 多租户与模型路由

BirdBot 作为共享云服务运行，不为每个用户或设备启动完整 Agent 实例。

用户、设备、会话、记忆和数据按以下维度隔离：

```text
tenant_id / user_id / device_id
```

模型层采用供应商中立设计。OpenAI-compatible API 作为公共调用基线，支持国内外模型，例如：

- OpenAI；
- Gemini；
- DeepSeek；
- Qwen；
- 智谱；
- 其他兼容端点或自建模型服务。

模型路由综合考虑：

- 用户和数据所在区域；
- 任务所需能力；
- 是否需要图片、视频或结构化输出；
- 延迟和价格；
- 合规和数据驻留要求；
- 当前服务可用性。

OpenAI-compatible 不代表所有高级能力完全一致。BirdBot 需要维护模型能力信息；视频、文件、缓存和供应商特有参数在必要时使用原生适配器。

## 7. 识别服务的边界

BirdBot 不重新承担全部机器学习推理。

默认优先消费端侧或现有云端 ML 服务提供的：

- 检测结果；
- 鸟类裁剪图；
- Top-K 物种候选；
- 模型置信度和版本。

BirdBot 增加统一识别适配层：

1. 接收已有模型候选；
2. 根据位置、时间、历史和 eBird 数据进行候选重排；
3. 当结果不确定、冲突或属于高级会员任务时，调用第三方视觉 API 或自建云端模型；
4. 输出候选、证据、可信度和决策，而不是只返回一个物种名称。

LLM 不作为视频处理流水线。视频解码、目标轨迹、帧评分和媒体转换应由普通程序或专业模型完成。多模态大模型主要接收少量精选帧、拼图和结构化证据，用于行为理解和内容生成。

## 8. eBird 的产品价值

[eBird API](https://documenter.getpostman.com/view/664302/S1ENwy59) 不只用于验证物种名称，而是 BirdBot 的本地鸟类上下文来源。

它可以支持：

- 根据设备地点和日期重排相似物种；
- 判断访客是当地常见种、季节访客还是近期少见记录；
- 为 Story 提供“为什么此时出现在这里”的解释；
- 预测近期可能出现的物种；
- 将设备网络数据与社区观测进行对照；
- 为未来迁徙趋势建立外部参照。

BirdBot 应建立统一的 Bird Context Service，对 eBird 查询进行缓存、限流、分类体系映射和隐私处理，避免每个 Skill 独立请求外部 API。

eBird 的近期 API、长期 Status and Trends 产品以及 Macaulay Library 媒体拥有不同使用边界。尤其是图片、声音和商业展示不能因可访问而默认获得商业授权。

## 9. 开源项目复用策略

可移植的就直接拉到项目中不跟踪的_ref目录，然后按需复制（可调整）到我们的业务代码中

### 直接作为依赖

- [HKUDS/nanobot](https://github.com/HKUDS/nanobot)：Agent 内核，MIT。其实我们用的是轻量版我已经复制到项目中了
- [pyinaturalist](https://github.com/pyinat/pyinaturalist)：iNaturalist Python 客户端，MIT；后续支持非鸟访客和自然观察背景。

### 可移植或复用部分代码

- [Birding Buddy MCP](https://github.com/woodcreeper/birding-buddy-mcp)：MIT。可移植 eBird、Xeno-canto、区域解析和地理计算适配层；正式版倾向转换为 BirdBot 内部 Python Tool。
- [iNaturalist MCP](https://github.com/cvsouth/inaturalist-mcp)：MIT。可参考或复用 Tool schema、查询封装和限流逻辑。
- [CameraTrapAI / SpeciesNet](https://github.com/google/cameratrapai)：Apache-2.0。可借鉴分类输出、Top-K、geofence 和多模型证据组合；模型权重与商业条款单独审核。
- [MCP Data Server](https://github.com/boettiger-lab/mcp-data-server)：BSD-3-Clause。后期迁徙分析和大规模 DuckDB、Parquet、H3 地理查询可使用。

### 只参考设计并重新实现

- [BirdLense Hub](https://github.com/Gfermoto/BirdLense-Hub)：参考访鸟事件、最佳帧、轨迹、行为特征、ReID、纠错和时间线设计。其发布与模型存在非商业或禁止演绎限制，不能作为商业 BirdBot 的直接代码底座。
- [BirdNET Analyzer](https://github.com/birdnet-team/BirdNET-Analyzer)：代码为 MIT，但官方模型为 CC BY-NC-SA 4.0。可参考音频处理和结果格式，商业 Sound ID 需要单独授权或替代模型。
- [Ecology Harness](https://github.com/ECNU-ICALK/Ecology-Harness)：MIT。只借鉴生态 Tool catalog、能力检查和运行轨迹审计，不与 nanobot 合并。

基本原则是：

> 许可清晰且边界独立的代码可以依赖或移植；非商业、禁止演绎或许可不清晰的项目只研究产品和架构思想，再进行独立实现。

## 10. 暂不展开的内容

本文档不定义：

- 代码目录结构；
- BirdEvent 的完整字段；
- 每个 Skill 的详细提示词；
- Tool API 和数据库表；
- Workflow 状态机的具体实现；
- 模型供应商和价格配置；
- 部署拓扑和容量规划；
- 详细开发排期。

这些内容在 Idea 方向确认后再分别形成设计和实施计划。

