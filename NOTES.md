# Scout 开发笔记：踩过的坑与我做过的判断

这份笔记是从代码旁边的注释里整理出来的——那些"当时为什么会这么写"的记录。
按主题归类，每条尽量保持 **现象 → 原因 → 结论** 的形状。

> 标注 `补充` 的条目不是原始注释里的，是我在读代码时发现的、值得一起记下来的东西。

---

## 0. 一句话架构

```
工具定义 → JSON Schema 生成 → 插件发现 → 注册 → 随请求发给模型
   → 模型返回 tool_calls → 执行工具 → 结果回填 messages → 再次请求
```

| 层 | 文件 | 职责 |
|---|---|---|
| 入口 | `src/__main__.py` | 日志配置 + `build_agent()` |
| 主循环 | `src/agent/agent.py` | 模型 ↔ 工具，直到不再调用工具 |
| 执行器 | `src/agent/tool_executor.py` | 查找、参数注入、执行、重试计数 |
| 工具管理 | `src/agent/plugins_manager.py` | `PluginsLoader` 的薄包装 |
| 接口声明 | `src/agent/protocol.py` | `MemoryProtocol` / `ToolExecutorProtocol` / `PluginsLoaderProtocol` |
| 配置 | `src/agent/config_context.py` | `root`、`tavily_api_key` 两个可注入字段 |
| 记忆 | `src/memory/memory.py` | messages 列表，四个 add 方法 |
| 工具契约 | `src/tool/contract.py` | `BaseTool` dataclass |
| 装饰器 | `src/tool/basetool_get.py` | `@tool` + pydantic → JSON Schema |
| 插件加载 | `src/tool/plugins_loader.py` | 目录扫描 + import + 抓 `BaseTool` 实例 |
| 工具实现 | `src/tool/plugins/*` | 单文件插件 + `search/` 包插件 |

---

## 1. 环境与运行

### 1.1 `-m` 决定 `sys.path`，决定能不能 `import src`

```bash
python -m pytest tests/ -v     # cwd=scout/ ✅ 把 scout/ 放进 sys.path，能定位 src
python pytest tests/ -v        # ❌ sys.path 里没有 scout/，ModuleNotFoundError
```

**原因**：`-m` 把当前工作目录加进 `sys.path` 的第 0 位；直接跑脚本时加的是**脚本所在目录**。
**结论**：这个项目永远用 `python -m pytest`。VS Code 的 pytest 集成走的是 `-m`，所以那边正常。

### 1.2 日志配置必须在业务 import 之前

`src/__main__.py:1-18` 先 `basicConfig`，再 import 业务模块。
**原因**：插件模块在 import 时就会执行顶层代码（比如 `logger.info`、`TavilyClient(...)`），日志没配好这些记录直接丢失。
**结论**：入口文件的 import 顺序是刻意排的，不是随手写的。

### 1.3 `filemode='w'` 会清空日志

`src/__main__.py:6`。每次启动覆盖一次 `src/record.log`。
**踩过的后果**：上一次崩掉的现场，被下一次启动冲掉了。
**结论**：排查阶段临时改成 `'a'`，或者把日志按启动时间分文件。

### 1.4 日志是按模块降级的

`src/__main__.py:9-18` 用 `logging.getLogger('src.agent.agent').setLevel(DEBUG)` 逐模块调。
**结论**：模块内统一用 `logging.getLogger(__name__)`，否则外部无法按名字控制。

### 1.5 环境变量永远是字符串

`src/config.py:11` 的 `get_env_int` 存在的唯一理由：`os.getenv` 只返回 `str`，`timeout='60'` 传给 `OpenAI()` 虽然能用，但 `max_retries` 这类参与数值比较的必须转。

---

## 2. 路径与工作区（最容易出事的一层）

### 2.1 `resolve()` 的语义：这才是越权拦截的关键

`edit_file` 的注释（`src/tool/plugins/edit_file.py:13`）：

> resolve() 一旦遇到不存在的部分，后面的内容就照原样拼上，解析真实的路径落点，将 `..` 等写法转成 cwd 下的绝对路径，防止路径落到 root 外面。

**结论**：必须 **先 resolve，再 `is_relative_to(root)`**。
- 先比字符串再 resolve → `work/../../etc/passwd` 直接绕过
- 只 resolve 不比较 → 什么都没拦住

### 2.2 校验顺序是排过的

`edit_file` 里四个检查的次序：

1. 越界（`is_relative_to`）→ 拒绝
2. 目标是目录（`is_dir`）→ 拒绝，因为后面要 `write_text`
3. 父目录不存在 → `mkdir(parents=True, exist_ok=True)`
4. 写

**原因**：先建目录再判断越界，等于先越权再拦截。

### 2.3 两个来源的参数，信任等级不同

| 参数 | 来源 | 可信度 |
|---|---|---|
| `path` / `content` / `query` | 模型生成 | 不可信，要校验 |
| `root` | `ToolExecutor.get_config` 注入 | 可信，且会**覆盖**模型传的同名参数 |
| `tavily_api_key` | `ConfigContext` | 可信 |

`src/agent/tool_executor.py:52-60` 的注入逻辑：签名里有同名参数就填进去。
`README.md:100` 写明"模型传入的同名参数会被可信配置覆盖"——这是刻意的信任边界。

### 2.4 `get_filepath` 返回的是相对路径

`src/tool/plugins/get_filepath.py:14` 用 `relative_to(workspace)`，所以模型看到的是 `src/agent/agent.py` 这种。
**结论**：模型拿着这个路径回来调 `read_file` / `edit_file` 时必须再传 `root`，因为解析的基准是注入的 `root`，不是 cwd。

---

## 3. 返回值契约（422 事故的根源）

### 3.1 三键约定

```
{ok: bool, content: str | None, error: str | None}
```

### 3.2 那个 422

`src/tool/plugins/read_file.py:62` 的注释：

> 漏填 return 值，tool 消息里的 content 为 None，导致 422 错误，不同服务商错误码可能不同，ds 是 422，openai 是 400

**原因**：函数走到了末尾没有 `return`，返回 `None` → `memory.add_tool_msg(content=None)` → 下一轮请求里 tool 消息的 `content` 是 `None`，接口直接拒。
**结论**：

- 每条分支都必须**显式 return**，宁可返回 `ok:False`
- `tool` 消息的 `content` 不能是 `None`，空也要给 `''`
- 报错位置不在模型，在本地——所以看日志要看"填入工具消息"之前有没有异常

### 3.3 失败时 `error` 写的是"模型下一步做什么"

不是给人看的堆栈，是给模型看的指令：

- `'path不在用户指定的工作区内，请重新调用工具生成你知道的路径'`
- `'path 指向的是目录：xxx，请给出文件路径'`
- `'arguments的json解析失败:xxx,请更换参数传入或者换个策略'`

**结论**：`error` 是 prompt。

### 3.4 补充：现在的返回形状其实不统一

按三键约定检查：

| 位置 | ok | content | error |
|---|---|---|---|
| `edit_file.py:23-26` 越界 | ✗ | **缺** | ✓ |
| `edit_file.py:28-31` 目录 | ✗ | ✓ | ✓ |
| `edit_file.py:37-40` 成功 | ✓ | **缺** | ✓ |
| `read_file.py:50-56` 截断 | ✓ | ✓ | ✓ + `truncated` |
| `read_file.py:57-62` 正常 | ✓ | ✓ | ✓ |

同一个工具的三种分支三种形状。模型不会因此崩，但"工具返回值有统一形状"这件事就不再成立了。**一条 `assert set(result) == {'ok','content','error'}` 就能盯住。**

---

## 4. 模型的输入到底长什么样

### 4.1 `arguments` 是 JSON 字符串，不是 dict

- 有参数：`'{"path": "a.py", "content": "..."}'`
- 无参数：`''`（空串，不是 `'{}'`）
- 幻觉参数时：语法坏掉的 JSON

`json.loads('')` 抛 `JSONDecodeError`，`json.loads(dict)` 抛 **`TypeError`**（不是 `JSONDecodeError`）。
`src/agent/tool_executor.py:46` 只捕获了前者。

### 4.2 两条失败路径必须分开

| 失败 | 异常 | 现在的处理 |
|---|---|---|
| JSON 解析失败 | `JSONDecodeError` | `'arguments的json解析失败'` |
| 参数名/签名不匹配 | 调用时 `TypeError` | `'参数错误:...'` |
| 工具内部炸 | 任意 `Exception` | `'工具调用失败:...'` |

**结论**：三种错误的"重试建议"不一样，混在一起模型会做无效重试。

### 4.3 假货要按真实结构造

`src/agent/tool_executor.py` 只需要 `aimsg.tool_calls[*].id / .function.name / .function.arguments`，所以测试里用 `SimpleNamespace` 足够（`tests/test_tool_executor.py:27-37`）。

**但**：`FakeMemory.add_tool_msg` 的参数名必须和真的一样（`tests/test_tool_executor.py:20` 的注释），否则 `**kwargs` 一改名就静默错位。

**踩过的坑**：曾经用 `{'x': 'er'}`（dict）当 `arguments` 想测"工具调用失败"，结果抛的是 `TypeError` 而不是预期的那条错误，测试跑不通被注释掉了。真实该测的是 `''`、`'{}'`、`'{"x": 1,}'`。

### 4.4 一条 message 可以有多个 tool_call

`src/record.log:9-15` 那次真实运行里，模型一次返回了两个 search 调用，`execute` 的 `for tool_call in aimsg.tool_calls` 逐个处理。

**结论**：每个 `tool_call_id` 都必须回填一条 tool 消息。漏一个，下一轮请求直接 400/422。

### 4.5 存进 memory 之前要 `model_dump()`

`src/memory/memory.py:19`。`res.choices[0].message` 是 openai SDK 的对象，直接塞进 `messages` 再发回去会序列化失败，必须 `.model_dump()` 转成 dict。

---

## 5. 重试状态机

`src/agent/tool_executor.py:14-20` 两个字典：

```
func_retry  = {工具名: max_retry}   # 上限，来自 @tool(max_retry=N)
error_retry = {工具名: 0}           # 当前失败次数
```

三个转移：

1. **失败**（解析错 / TypeError / 工具异常）→ `error_retry += 1`
2. **成功** → `error_retry = 0`
3. **达到上限** → 回一条"重试次数达到上限，不要再调用此工具" + 进 `disabled_tools` + 从后续 schema 里摘掉（`:34-38`、`:112`）

**实际语义**：`max_retry=2` 不是"最多调 2 次"，是"允许失败 2 次，**第 3 次调用时被拦**"。off-by-one 就在这里，只有序列测试能钉住。

**已知没解决**（README 已知限制第 3 条）：计数挂在 `ToolExecutor` 实例上，不按每次用户任务重置。一次对话里前面失败过，后面换个任务还背着旧账。

---

## 6. 插件加载

### 6.1 两种形式

- **单文件**：`plugins/xxx.py`，模块里有个 `BaseTool` 实例
- **包**：`plugins/xxx/__init__.py`，必须在里面显式 `from .search import search`（`src/tool/plugins/search/__init__.py:1`）
  **原因**：`inspect.getmembers(module)` 只扫这个模块的属性。工具对象挂在 `search.search` 子模块上，不 import 到 `__init__` 里就抓不到。注释原话："此时 search 已经成为一个 BaseTool 实例了，能被加载"。

### 6.2 下划线开头的文件跳过

`src/tool/plugins_loader.py:24`。`__init__.py`、`_draft.py` 都不会被当成插件。

### 6.3 `importlib` 的锚点

```python
importlib.import_module(f'.plugins.{module_name}', package=__package__)
```

`__package__` 是 `src.tool`，所以拼出来是 `src.tool.plugins.edit_file`。
**结论**：不能写死 `src.tool.plugins.xxx`，否则一旦整个项目被当成子包挪位置就全挂。

### 6.4 加载失败只 log，不抛

`src/tool/plugins_loader.py:32-34` catch 完 `continue`。
**后果**：一个插件写错语法 → 只有一个 error 日志 → 其余照常 → **模型那边静默少一个工具**。这是最坏的失败类型。

### 6.5 模块顶层代码 = import 时执行

`search.py:10` 模块级 `tavily = TavilyClient(api_key=TAVILY_API_KEY)`。
**后果**：key 无效 / `tavily` 没装 / 网络问题 → import 就炸 → 整个 search 插件消失，而且只在 error 日志里说了一句。

### 6.6 插件加载的验证方式

```python
names = {t.name for t in PluginsLoader().load_plugins()}   # 别用 set(tools)，BaseTool 不可哈希
assert {'edit_file', 'read_file', 'get_filepath', 'search'} <= names
```

---

## 7. Schema 生成与 token

`src/tool/basetool_get.py`（AI 写的，但逻辑值得看懂）：

1. `args_schema.model_json_schema()` 出标准 JSON Schema
2. `_inline_refs` 把 `$defs` / `$ref` 就地展开（部分厂商不认）
3. `_strip_titles` 递归删掉 `title`（和字段名重复，纯占 token）
4. 包成 `{"type": "function", "function": {"name", "description", "parameters"}}`

三个要点：

- **函数名就是工具名**，模型看到的是 `func.__name__`
- **docstring 就是 description，就是 prompt，不是注释**
- **`Field(description=...)` 同样发给模型**，约束（单位、范围、格式）写在这里

**补充**：`@tool` 装饰器返回的是 `BaseTool` 实例，所以模块级的 `read_file` **不是函数**，是对象。测试里必须走 `read_file.func(...)`。

---

## 8. 分层与生命周期（我自己的判断）

`src/agent/agent.py:58-66` 的原文：


> memory 和工具 retry 次数持续到对话结束
>
> 有行为无状态的做成函数
> 有行为有共享状态的做成类
> 只有状态的可以用 dataclass

对应到代码：

| 东西 | 生命周期 | 形态 |
|---|---|---|
| `# 工具 schema 转换` | 调用即结束 | 函数 `to_tool_schema` |
| `PluginsLoader` | 启动一次 | 类 |
| `Memory` / `ToolExecutor` | 整个对话 | 类（有状态） |
| `BaseTool` / `ConfigContext` | 只是数据 | dataclass |

**另外两个判断**：

- **用 `Protocol` 而不是 ABC**（`src/agent/protocol.py`）：只描述形状，不强制继承。所以测试里 `FakeMemory` 随便造，不需要 `class FakeMemory(Memory)`。
- **配置注入优于让模型传**：`root`、`key` 这类不该经过模型的内容由执行器注入，并覆盖模型传的同名参数。

---

## 9. 测试方法论（这部分是最近的结论）

### 9.1 测什么

测的是**对外契约**和**对外部世界的假设**，不是复述实现。

一条断言的价值 ≈ 它失败时你能知道多少原本不知道的事。`assert result['ok'] is True` 如果是照着刚写的那行抄的，价值为零；如果它约束的是"执行器 / 模型 / 下一轮解析依赖这个键存在"，价值就来了。

### 9.2 三个测试的位置

| 文件 | 覆盖 | 缺口 |
|---|---|---|
| `tests/test_edit_file.py` | 成功 / 越权 / 目录 | 返回形状（三键）没断言 |
| `tests/test_tool_executor.py` | 只有 JSON 解析失败 1 条 | 成功路径、重试序列、多 tool_call、空串参数 |
| `tests/test_plugins_loader.py` | `assert tools` | 名字集合、静默缺工具 |

### 9.3 具体技巧

- **`tmp_path`**：pytest 内置临时目录，不碰真文件、不污染工作区
- **断言用固定字段，忽略动态变量**：`assert 'path 指向的是目录' in result['error']`，而不是整串比较（整串里带路径，换台机器就红）
- **顺序无关的包含用集合**：`expected <= set(names)`
- **顺序有关才用列表相等**：`[t.name for t in tools] == [...]`

### 9.4 坑：`list <= list` 不是"包含"

```python
['a', 'b'] <= ['b', 'c']   # True —— 只是 'a' < 'b'，字典序比较！
{'a', 'b'} <= {'b', 'c'}   # False —— 这才是子集判断
```

**结论**：`<=` 想要"包含"只喂 `set`。

### 9.5 该删的测试

复述实现的断言（"我刚写了 `ok: True`，所以断言 `ok is True`"）会在重构时制造噪音，却抓不到 bug。`Plugins_Loader` 改名 `PluginsLoader` 那次，`test_plugins_loader` 红了——红的原因不是 bug。

---

## 10. 安全

- **`ROOT` 不要指向敏感目录**（`README.md:127-129`）：`run_command` 与写文件工具都在这个范围内活动。
- **工具返回的文本是不可信输入**：`search` 的联网结果会被原样拼进上下文，这是提示注入的入口。
- `.env` 已被 `.gitignore` 排除（`.env`、`.env.*`，保留 `!.env.example`）。

### 10.1 补充：`src/tool/plugins/search/config.py:3` 里硬编码了真实 Tavily key

该文件**被 git 跟踪**（不在 `.gitignore` 里），key 已经在提交历史里了。

**要做的事**：

1. 改成 `os.getenv('TAVILY_API_KEY')`，和其它配置一个来源
2. 去 Tavily 后台**作废这把 key 并重发**——删文件不等于删历史
3. 顺便：`.env.example:16` 写着"未填写则 search 插件加载失败"，实际这个插件根本没读 env，文档和代码现在不一致

---

## 11. 尚未解决

来自 `README.md` 已知限制，外加读代码时看到的：

- [ ] 主循环 `while True` 没有步数上限，模型可能死循环
- [ ] `messages` 只增不减，长对话必然超窗
- [ ] 失败计数不按任务重置
- [ ] CLI 的 `print` / `input` 耦合在 Agent 循环里（`agent.py:43`），无法批量化
- [ ] 无流式输出
- [ ] 联网搜索 / 命令执行的集成测试
- [ ] `edit_file` 三种返回形状不统一（见 3.4）
- [ ] `read_file` 注释说 200 行，`len(collected) > 200` 实际给 201 行（`read_file.py:48`）
- [ ] `get_tool_args` 用 `False` 当"解析失败"的哨兵（`tool_executor.py:50`），合法 JSON `false` 会被误判
- [ ] `disabled_tools` 是 list，重复调用会重复 append（`get_schema` 用 `set()` 兜住了）
- [ ] 整个项目没有一条测试跑过 `Agent.__call__`

---

## 12. 常用命令

```bash
pip install -r requirements.txt
copy src\.env.example src\.env        # 然后填值

python -m src                         # 跑一次对话（会先问你 system prompt）
python -m pytest tests/ -v            # 测试，注意 -m
python -m pytest tests/test_edit_file.py::test_edit_file -v
```

---

## 附：`run_command` 说明

`src/tool/plugins/run_command.py` 是 AI 写的，不在本笔记的总结范围内。
它的设计要点（超长命令/输出截断、静态黑名单、cwd 沙箱、进程树回收、环境变量过滤、stdin 分离）看文件头注释即可。它同样依赖执行器注入的 `root`（`src/record.log:18` 能看到 `工具run_command注入参数root`）。
