# BirdBot 产品样子 · Product Showcase

一个**可一键运行、完全离线**的演示，把 BirdBot 的价值具象成三个视角：

| 视角 | 页面 | 是谁看的 | 看到什么 |
|---|---|---|---|
| 🛰 **Device Simulator** | `/device.html` | 模拟 IoT 喂鸟器/平台 | 配置并发出一次 sighting，实时看 `BirdEvent` 流过识别 → 稀有度 → 故事的每一阶段 |
| 📱 **NatureFeed App** | `/app.html` | 终端用户（喂鸟器主人） | 鸟种观察卡时间线 + 今日日报 + 真正懂这台设备历史的 Nature Chat |
| 🏢 **Ops Console** | `/console.html` | 厂商运营 | 每一次受治理的 LLM 调用（成本/延迟/逻辑→真实供应商/区域）、被 surface 的降级、eBird 合规拦截、模型路由表 |

## 运行

```bash
source .venv/bin/activate
uv pip install -e "birdbot/[dev]"     # 若还没装；本演示还需 fastapi/uvicorn（已是 birdbot 依赖）
python -m demo.server                 # 打开 http://127.0.0.1:8800
```

无需任何 API key、Postgres、Redis 或外网。打开总览页，点 “⚡ Fire a random sighting”，
然后在三个视角间切换——它们共享同一个后端、通过 SSE 实时联动。

## 这不是 mockup：跑的是**真实** BirdBot 组件

演示刻意只把 BirdBot 真正需要外部世界的那几样换成确定性离线假实现，其余全是生产代码：

| 环节 | 真实复用的生产组件 | 离线假实现的部分 |
|---|---|---|
| 识别快速阶段 | `recognition.run_fast_stage` + `Calibrator` + `FrameScorer`，并**真正注入** `context.rerank.make_geo_temporal_reranker`（功能盘点里"已实现但未接线"的 reranker，这里接上了） | 端侧 Top-K 由场景脚本合成（本就是设备产出） |
| 本地稀有度 | `context.BirdContextService` + 真实的 source-mode 选择 + **真实的 eBird/iNat 商用拦截（ADR-0005）**，降级经 observer surface | eBird/iNat/taxonomy 的 HTTP 适配器换成内存频率表 |
| 深度故事 | `deep.GatewayStoryLLM` + `build_story_prompt` + `STORY_SCHEMA` 硬闸，每次调用都过真实的 `LLMGateway`（quota→route→telemetry→cost，ADR-0014） | LLM provider 换成 `FakeCompletion`（确定性、schema 合法、离线） |
| Nature Chat | 真实的 `chat.NatureChatHandler` + `runtime.AgentRuntime` + 真实工具（`device_history` / `bird_context`），走真实的两步 tool-use loop | Postgres 换成 `FakeDB`（设备历史从内存事件日志算，因此"看过 N 次"是真的） |
| 观测/治理 | 真实的 `CallRecord` 遥测 + `Alert`（DEGRADED / QUOTA_EXHAUSTED / SOURCE_SWITCH） | 遥测/告警 sink 额外把每条镜像到 SSE 总线给前端 |
| 模型路由 | 真实的 `router.ModelRouter` + `CapabilityRegistry`（区域硬约束 / 能力断言 / 拒 unimpl backend，ADR-0007/0012） | 注册表里填的是演示用逻辑→后端条目 |

**唯一绕过的主链路环节**：Postgres / Outbox / WorkflowRuntime（`ingress.store` / `workflow.*`）。
演示用内存事件日志 + 内联深度阶段代替，因此不需要数据库。这也是与生产主链路唯一的结构性差异。

## 三个可玩的硬约束演示

- **识别三态**：场景 `clear-cardinal`→accept、`two-finches`→rollup（卷到科 Fringillidae，即便经过本地频率 rerank 仍贴太近）、`blurry-visitor`→escalate（低于接受阈值）。
- **eBird 合规（ADR-0005）**：默认"未授权"，eBird/iNat 被商用拦截 → 稀有度回退到 key-less 的 taxonomy 基线；切到 `eBird only` + 未授权 → 稀有度直接 `unknown`（硬门，可见不静默），运营后台升起 `source_switch` 告警。
- **区域路由（ADR-0007）**：柏林设备（region `EU`）的数据流区域在遥测里可见；路由表展示 EU-resident 选项与 DPF/SCC 合规标签。

## 文件

```
demo/
  scenarios.py   鸟种目录 + 区域稀有度表 + 设备机群 + sighting 场景
  fakes.py       FakeCompletion / FakeContextSource / FakeDB / AsyncQuota / 广播 sink
  engine.py      DemoEngine —— 装配真实组件，驱动整条管线（ingest / chat / digest / metrics）
  bus.py         极简 async pub/sub，喂 SSE
  server.py      FastAPI：静态页 + /api/* + /api/events/stream（SSE）
  static/        index / device / app / console 四个页面（纯 vanilla，无构建步骤）
```
