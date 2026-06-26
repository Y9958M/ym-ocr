---
name: fastapi
description: "FastAPI best practices (CLI, Annotated, Pydantic, routers, OpenAPI, streaming). For apiYmy, align with .cursor/rules: multi-project boundaries, python-conventions, UV by user. Use when adding or changing FastAPI routes, dependencies, request/response models, middleware, or when the user mentions FastAPI, APIRouter, or OpenAPI."
---

# FastAPI

Official FastAPI skill to write code with best practices, keeping up to date with new versions and features.

## Use the `fastapi` CLI

Run the development server on localhost with reload:

```bash
fastapi dev
```


Run the production server:

```bash
fastapi run
```

### Add an entrypoint in `pyproject.toml`

FastAPI CLI will read the entrypoint in `pyproject.toml` to know where the FastAPI app is declared.

```toml
[tool.fastapi]
entrypoint = "my_app.main:app"
```

### Use `fastapi` with a path

When adding the entrypoint to `pyproject.toml` is not possible, or the user explicitly asks not to, or it's running an independent small app, you can pass the app file path to the `fastapi` command:

```bash
fastapi dev my_app/main.py
```

Prefer to set the entrypoint in `pyproject.toml` when possible.

## Use `Annotated`

Always prefer the `Annotated` style for parameter and dependency declarations.

It keeps the function signatures working in other contexts, respects the types, allows reusability.

### In Parameter Declarations

Use `Annotated` for parameter declarations, including `Path`, `Query`, `Header`, etc.:

```python
from typing import Annotated

from fastapi import FastAPI, Path, Query

app = FastAPI()


@app.get("/items/{item_id}")
async def read_item(
    item_id: Annotated[int, Path(ge=1, description="The item ID")],
    q: Annotated[str | None, Query(max_length=50)] = None,
):
    return {"message": "Hello World"}
```

instead of:

```python
# DO NOT DO THIS
@app.get("/items/{item_id}")
async def read_item(
    item_id: int = Path(ge=1, description="The item ID"),
    q: str | None = Query(default=None, max_length=50),
):
    return {"message": "Hello World"}
```

### For Dependencies

Use `Annotated` for dependencies with `Depends()`.

Unless asked not to, create a new type alias for the dependency to allow re-using it.

```python
from typing import Annotated

from fastapi import Depends, FastAPI

app = FastAPI()


def get_current_user():
    return {"username": "johndoe"}


CurrentUserDep = Annotated[dict, Depends(get_current_user)]


@app.get("/items/")
async def read_item(current_user: CurrentUserDep):
    return {"message": "Hello World"}
```

instead of:

```python
# DO NOT DO THIS
@app.get("/items/")
async def read_item(current_user: dict = Depends(get_current_user)):
    return {"message": "Hello World"}
```

## Do not use Ellipsis for *path operations* or Pydantic models

Do not use `...` as a default value for required parameters, it's not needed and not recommended.

Do this, without Ellipsis (`...`):

```python
from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float = Field(gt=0)


app = FastAPI()


@app.post("/items/")
async def create_item(item: Item, project_id: Annotated[int, Query()]): ...
```

instead of this:

```python
# DO NOT DO THIS
class Item(BaseModel):
    name: str = ...
    description: str | None = None
    price: float = Field(..., gt=0)


app = FastAPI()


@app.post("/items/")
async def create_item(item: Item, project_id: Annotated[int, Query(...)]): ...
```

## Return Type or Response Model

When possible, include a return type. It will be used to validate, filter, document, and serialize the response.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me")
async def get_item() -> Item:
    return Item(name="Plumbus", description="All-purpose home device")
```

**Important**: Return types or response models are what filter data ensuring no sensitive information is exposed. And they are used to serialize data with Pydantic (in Rust), this is the main idea that can increase response performance.

The return type doesn't have to be a Pydantic model, it could be a different type, like a list of integers, or a dict, etc.

### When to use `response_model` instead

If the return type is not the same as the type that you want to use to validate, filter, or serialize, use the `response_model` parameter on the decorator instead.

```python
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me", response_model=Item)
async def get_item() -> Any:
    return {"name": "Foo", "description": "A very nice Item"}
```

This can be particularly useful when filtering data to expose only the public fields and avoid exposing sensitive information.

```python
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class InternalItem(BaseModel):
    name: str
    description: str | None = None
    secret_key: str


class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me", response_model=Item)
async def get_item() -> Any:
    item = InternalItem(
        name="Foo", description="A very nice Item", secret_key="supersecret"
    )
    return item
```

## Performance

Do not use `ORJSONResponse` or `UJSONResponse`, they are deprecated.

Instead, declare a return type or response model. Pydantic will handle the data serialization on the Rust side.

## Including Routers

When declaring routers, prefer to add router level parameters like prefix, tags, etc. to the router itself, instead of in `include_router()`.

Do this:

```python
from fastapi import APIRouter, FastAPI

app = FastAPI()

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/")
async def list_items():
    return []


# In main.py
app.include_router(router)
```

instead of this:

```python
# DO NOT DO THIS
from fastapi import APIRouter, FastAPI

app = FastAPI()

router = APIRouter()


@router.get("/")
async def list_items():
    return []


# In main.py
app.include_router(router, prefix="/items", tags=["items"])
```

There could be exceptions, but try to follow this convention.

Apply shared dependencies at the router level via `dependencies=[Depends(...)]`.

## Dependency Injection

See [the dependency injection reference](references/dependencies.md) for detailed patterns including `yield` with `scope`, and class dependencies.

Use dependencies when the logic can't be declared in Pydantic validation, depends on external resources, needs cleanup (with `yield`), or is shared across endpoints.

Apply shared dependencies at the router level via `dependencies=[Depends(...)]`.

## Async vs Sync *path operations*

Use `async` *path operations* only when fully certain that the logic called inside is compatible with async and await (it's called with `await`) or that doesn't block.

```python
from fastapi import FastAPI

app = FastAPI()


# Use async def when calling async code
@app.get("/async-items/")
async def read_async_items():
    data = await some_async_library.fetch_items()
    return data


# Use plain def when calling blocking/sync code or when in doubt
@app.get("/items/")
def read_items():
    data = some_blocking_library.fetch_items()
    return data
```

In case of doubt, or by default, use regular `def` functions, those will be run in a threadpool so they don't block the event loop.

The same rules apply to dependencies.

Make sure blocking code is not run inside of `async` functions. The logic will work, but will damage the performance heavily.

When needing to mix blocking and async code, see Asyncer in [the other tools reference](references/other-tools.md).

## Streaming (JSON Lines, SSE, bytes)

See [the streaming reference](references/streaming.md) for JSON Lines, Server-Sent Events (`EventSourceResponse`, `ServerSentEvent`), and byte streaming (`StreamingResponse`) patterns.

## Tooling

See [the other tools reference](references/other-tools.md) for details on uv, Ruff, ty for package management, linting, type checking, formatting, etc.

## Other Libraries

See [the other tools reference](references/other-tools.md) for details on other libraries:

* Asyncer for handling async and await, concurrency, mixing async and blocking code, prefer it over AnyIO or asyncio.
* SQLModel for working with SQL databases, prefer it over SQLAlchemy.
* HTTPX for interacting with HTTP (other APIs), prefer it over Requests.

## Do not use Pydantic RootModels

Do not use Pydantic `RootModel`, instead use regular type annotations with `Annotated` and Pydantic validation utilities.

For example, for a list with validations you could do:

```python
from typing import Annotated

from fastapi import Body, FastAPI
from pydantic import Field

app = FastAPI()


@app.post("/items/")
async def create_items(items: Annotated[list[int], Field(min_length=1), Body()]):
    return items
```

instead of:

```python
# DO NOT DO THIS
from typing import Annotated

from fastapi import FastAPI
from pydantic import Field, RootModel

app = FastAPI()


class ItemList(RootModel[Annotated[list[int], Field(min_length=1)]]):
    pass


@app.post("/items/")
async def create_items(items: ItemList):
    return items

```

FastAPI supports these type annotations and will create a Pydantic `TypeAdapter` for them, so that types can work as normally and there's no need for the custom logic and types in RootModels.

## Use one HTTP operation per function

Don't mix HTTP operations in a single function, having one function per HTTP operation helps separate concerns and organize the code.

Do this:

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str


@app.get("/items/")
async def list_items():
    return []


@app.post("/items/")
async def create_item(item: Item):
    return item
```

instead of this:

```python
# DO NOT DO THIS
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str


@app.api_route("/items/", methods=["GET", "POST"])
async def handle_items(request: Request):
    if request.method == "GET":
        return []
```

# FastAPI（apiYmy）

## 必须先于本 Skill 的仓库规则

本 Skill **不覆盖**仓库已有约定。动手前阅读并对齐：

- [`.cursor/rules/agents-skills-prerequisite.mdc`](.cursor/rules/agents-skills-prerequisite.mdc)
- [`.cursor/rules/framework-multi-project.mdc`](.cursor/rules/framework-multi-project.mdc)（禁止 `app/wg` ↔ `app/ab` 等跨项目 import）
- [`.cursor/rules/python-conventions.mdc`](.cursor/rules/python-conventions.mdc)（本仓库 **小驼峰** 文件/方法名等）
- [`.cursor/rules/uv-environment.mdc`](.cursor/rules/uv-environment.mdc)（勿擅自改 `pyproject.toml` / `uv.lock` 或执行 `uv sync`，除非用户明确要求）

与上述规则冲突时，**以 `.cursor/rules` 为准**并简要说明取舍。

## 项目结构

- 按业务域拆分路由模块；在单项目目录内（如 `app/wg`）组织 `api/`、`models/` 等，不把兄弟项目的代码 import 进来。
- 配置走 `app.config` / 环境变量；复杂依赖用 `Depends()` 注入，避免隐式全局单例。
- 中间件、CORS、异常处理放在应用装配层（如 `main` 或框架初始化），与具体业务路由解耦。

## API 设计

- HTTP 方法与状态码语义一致；错误返回结构化且与现有项目风格一致。
- 请求/响应用 Pydantic 模型；校验失败交给框架默认或统一的异常处理器。
- 为可公开接口维护清晰的 OpenAPI（摘要、标签、示例字段说明按需补充）。

## 模型（Pydantic）

- 使用类型注解；模型按领域拆分文件，避免巨型 schema 文件。
- 序列化/反序列化边界明确；敏感字段不要进入响应模型（单独 DTO）。

## 数据访问（若使用 ORM）

- 连接池与事务边界清晰；长事务避免；查询注意 N+1。
- 迁移与 schema 变更按团队流程（本 Skill 不代替数据库规范）。

## 认证与安全

- 密码哈希、JWT/OAuth2、角色等按项目既有方案延续，不另起一套。
- CORS、限流、输入校验、安全响应头与日志：与生产配置一致；不在代码中硬编码密钥。

## 性能与异步

- I/O 密集路径优先 `async`；CPU 密集考虑线程池/进程池，避免阻塞事件循环。
- 缓存、后台任务、连接池与监控按项目已有模式扩展。

## 测试

- 新路由优先补集成测试（`TestClient` 等）或项目既有测试风格；覆盖错误分支与鉴权边界。

## 文档

- 公开端点的 docstring / 字段说明与 OpenAPI 保持同步；版本变更时更新破坏性说明。

## 参考来源

内容与结构参考社区整理的 FastAPI 实践清单（如 [awesome-cursorrules `rules-new/fastapi.mdc`](https://github.com/PatrickJS/awesome-cursorrules/blob/main/rules-new/fastapi.mdc)），已按 apiYmy 规则做优先级说明；**mdskills** 等安装器在无法使用 `npx` 时可直接依赖本目录的 `SKILL.md`。
