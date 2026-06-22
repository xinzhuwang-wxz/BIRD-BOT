# 持久层技术栈：asyncpg + 裸 SQL 迁移

BirdBot 应用层从 S2（issue #3）起落 Postgres 业务状态 + 多租户 RLS 地基（[ADR-0002](0002-workflow-on-postgres.md) / [ADR-0004](0004-tenant-isolation-pool-bridge.md)）。方案未指定具体库。约束：全程 asyncio、运维最轻、独立轻量应用层不拖重依赖、RLS 需会话级 GUC（`app.current_tenant`）直控。

**决定**：

- **驱动 = asyncpg**（async-native、无 DBAPI 包袱、最轻）。业务运行时一律走它。
- **迁移 = 自管极简 runner**：`birdbot/db/migrations/*.sql` 顺序编号 + `schema_migrations` 表跟踪，幂等前向应用；不引入 ORM / Alembic。
- **租户作用域**：事务内 `set_config('app.current_tenant', $1, true)`（= `SET LOCAL`，**参数化**防注入，事务结束自动复位，连接归池不泄漏）。
- **非 owner 角色**：业务连接用 `birdbot_app`（非表 owner、无 `BYPASSRLS`），RLS 才会强制生效（漏写 `WHERE` 也被拦）。**角色生命周期归运维/部署环境**——schema 迁移只 `GRANT`、不创建带凭据的角色；测试 fixture 扮演该环境创建角色。
- **测试库**：docker 一次性 Postgres，经 `BIRDBOT_TEST_DATABASE_URL` 连接；未设则集成测 skip 并提示起库命令。

**否决**：

- SQLAlchemy 2.0 + Alembic——重依赖、与「独立轻量应用层 / 运维最轻」张力，且会话级 GUC 仍须绕 ORM 直发 SQL，得不偿失。
- psycopg3——可行次选，但比 asyncpg 略重、async 性能略逊，无差异化收益。

**后果**：无 ORM 与迁移回滚框架，schema 演进靠裸 SQL 自律（前向迁移；回滚另写补偿迁移）。若将来 schema 复杂度 / 团队规模需要回滚与建模工具，再评估引入（届时 asyncpg 与之并存无碍）。
