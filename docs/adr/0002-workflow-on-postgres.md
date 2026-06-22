# Workflow 可靠性建在 Postgres，而非内核 Cron/Goal

BirdBot 固定主链路（快速/深度两阶段、定时日报、平台回调）的可靠性——状态、幂等、超时、有限重试、transactional outbox——从第一天起建在事务型 **Postgres**，采用可重入 step 函数（DBOS 式 durable execution）。

**决定**：业务 workflow 状态落 Postgres。内核 **Cron 仅作定时日报/聚合的触发器**（其调度持久化 fsync + 重启幂等可靠，但它不是执行引擎）。**不**把业务状态放进内核 `session.metadata`（对话记忆）或 Cron 单机 JSON 文件——它们无 step-journal/幂等/重试，且单机 FileLock 不支持多副本水平扩展。

**否决**：纯 Cron+文件（A，不可靠、不可扩展、违反「状态不进对话记忆」）；Temporal（C，MVP 阶段三服务集群对小团队过重，约 $400–900/月）。

**演进**：出现长挂起 workflow / 确定性 replay 审计需求 / 大量外部 API fan-out / 单库瓶颈 / 硬多租多区信号时，迁 DBOS→Temporal（同基于 Postgres，迁移平滑）。
