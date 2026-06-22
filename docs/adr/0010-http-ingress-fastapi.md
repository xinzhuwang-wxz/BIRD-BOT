# HTTP Ingress 框架：FastAPI

内核无任何网络 ingress（[ADR-0003](0003-ingress-pattern.md)）。从 S3（issue #4）起 BirdBot 自建 HTTP server 接收 BirdEvent。约束：pydantic 校验（BirdEvent v0 带版本）、全程 asyncio、秒级 `202` 回执、便于进程内集成测。

**决定**：

- **框架 = FastAPI**。pydantic v2 原生集成 → 请求体自动校验（非法 body 自动 `422`）；async-first；依赖注入便于把多租户作用域的存储注入端点；OpenAPI 免费。其底座 `starlette` + `pydantic` 已在环境，增量仅 `fastapi` 一个包。
- **应用经 `create_app(store)` 工厂构造**（依赖注入），便于测试替换存储、便于后续按租户作用域装配。
- **测试用 httpx `ASGITransport` 进程内打 app**（不起真 server）；生产用 `uvicorn`（已在环境）起。
- **BirdEvent v0** 用带 `schema_version` 字段的 pydantic 模型；缺媒体可接受（不同设备丰富度不同）。
- **v0 租户来源 = BirdEvent body** 携带的 `tenant/user/device`（[ADR-0003](0003-ingress-pattern.md)）。鉴权流水线（验证 API key/JWT → 覆盖/校验租户身份，B9）留作后续 issue；租户经 `TenantEnvelope` 在确定性组件间传递、**绝不让 LLM 承载**（[ADR-0004](0004-tenant-isolation-pool-bridge.md)），不破坏已落地的 RLS 机制。

**否决**：

- 裸 Starlette——已装、更轻，但要手写 pydantic 校验与错误映射，省下的依赖不抵手写成本。
- aiohttp——另一套生态，与 pydantic/httpx 测试栈不如 FastAPI 顺滑，无差异化收益。

**后果**：新增 `fastapi` 运行时依赖（starlette/pydantic 已在，增量小）。v0 信任 body 自报租户是已知局限，鉴权 hardening 在 B9 落地前不得视为安全边界——代码与文档明确标注。
