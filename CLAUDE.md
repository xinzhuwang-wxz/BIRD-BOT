# CLAUDE.md — BirdBot 工作手册

本文件是**所有 AI 会话在本仓库的默认工作模式**，无需用户每次声明。新会话先读本文件，再读 `docs/`。

---

## 项目是什么

**BirdBot**：面向智能喂鸟器的**云端 AI Agent 服务**（目标市场欧美）。它不取代 IoT 平台/端侧模型，而是把设备产生的图片/视频/声音/检测结果/时间/位置/历史组织成「这是什么鸟、在做什么、为何此时出现、是否常客、哪帧最值得存、今天发生了什么」的自然观察体验。

- 方向稿：[`docs/2026-06-22-birdbot-idea.md`](docs/2026-06-22-birdbot-idea.md)（初步想法，**不一定对**）
- 最佳实践方案：[`docs/2026-06-22-birdbot-solution.md`](docs/2026-06-22-birdbot-solution.md)（审计+调研+校验后的目标架构、工程债、待定决策、分期计划）—— **当前权威设计依据**
- 当前阶段：**P1 定靶**（架构已成稿，关键不可逆决策待拍板；尚未进入规划/执行）

## 基座与硬约束

仓库根的 `nanobot/` 是 **nanobot 的蒸馏轻量版（vendored）**，作为 Agent 内核（MIT）。BirdBot 领域代码是**独立应用层**。

- 🚫 **不改 `nanobot/` 内核**（在里面改任何一行即事实 Fork）。只通过 **entry_points Tool 插件 / Skills / Hook / config / MCP** 扩展；领域代码不得落进 `nanobot/agent/tools/`。
- 🚫 **不用 `Nanobot.run`**（私有 hook swap，多租户并发会串扰）——用自建薄门面调 `process_direct`。
- 🚫 关键业务/workflow 状态**不进对话记忆**（`session.metadata`）——落 Postgres。
- 🚫 **租户隔离不靠 LLM**——靠 Postgres RLS + 向量 namespace + 确定性组件传递租户信封。
- 🔴 **eBird/媒体商业授权是 P0 合规门**：未取得 Cornell 书面许可前，eBird 不进付费路径。

> 基座真实能力 vs 缺口、69 条工程债、7 项待定决策（K1–K7）见方案文档第 1/6 节。改动前先核对那里，别把基座「假设的能力」当真（如：无网络 ingress、无 BirdEvent 入口、Cron 非工作流引擎、tenant 原语为零）。

## 开发命令

```bash
source .venv/bin/activate          # Python 3.11（uv 管理）
uv pip install -e ".[dev]"         # 安装内核 + 测试依赖
python -m pytest tests/bus tests/config tests/session -q   # 快速核心回归
python -c "import nanobot"         # 冒烟
ruff check nanobot/                # line-length 100, 规则 E/F/I/N/W, 忽略 E501
```

- Python 3.11+，全程 asyncio。`pytest` 用 `asyncio_mode=auto`。
- 改动以**小步提交**为单位；提交信息英文 + 末尾 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`。
- 远程：`origin → github.com/xinzhuwang-wxz/BIRD-BOT.git`（默认分支 `main`）。仅在用户要求时提交/推送；推送前确认在分支上。

---

## 固定工作模式：审计 → 定靶 → 规划 → 执行

每项工作先判断它落在哪个阶段，按该阶段的产物与手法推进；跨阶段时显式说明切换。

### ① 审计 —— 看清架构与问题
- **产物**：项目全貌 + 工程债清单（zoom-out）。
- **手法**：`zoom-out` / 只读审计；接手不熟悉的部分、阶段性回顾时启用。
- **纪律**：用事实说话（`file:符号` 出处），区分「真实存在 / 已删 / 从未有过」；不改代码。

### ② 定靶 —— 沉淀领域模型 + 决策（**当前阶段**）
- **产物**：`CONTEXT.md`（领域语言/术语）+ `docs/adr/`（不可逆决策）。
- **手法**：`grill-with-docs`——对着领域模型把决策写进 CONTEXT.md 和 ADR。
- **触发**：出现模糊术语、要做不可逆决策时。当前待办：把方案 §6 的 K1–K7 拍板成 ADR；定义 BirdEvent schema 与术语表。

### ③ 规划 —— 找重构点、拆任务
- **产物**：PRD + 可独立交付的 issue（纵切片/tracer-bullet）。
- **手法**：`improve-codebase-architecture` → `to-prd` → `to-issues` → `triage`。
- **触发**：启动一轮改造时。

### ④ 执行 —— 一片一片安全推进
- **产物**：通过测试的小步提交。
- **手法**：`tdd`（红-绿-重构）+ `diagnose`（难 bug）+ `review`（提交前）；小步提交。
- **触发**：拿到一个明确 issue/任务时。
- **纪律**：每改一片，回归判据 = 核心测试仍绿 + `import nanobot` OK；不破坏上面的硬约束。

---

## 文档约定

- 设计/决策类长文放 `docs/`，日期前缀（`YYYY-MM-DD-*.md`）。
- 领域语言进 `CONTEXT.md`；不可逆决策一条一文进 `docs/adr/`（含背景/选项/决定/后果）。
- 文档从 0 起，按需新建——不要把 nanobot 上游的旧文档搬回来。
