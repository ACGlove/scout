# Scout

一个从零实现的轻量 LLM Agent 框架，用来学习 **function calling 的完整链路**：

```
工具定义 → JSON Schema 生成 → 插件发现 → 工具管理 → 随请求发给模型
   → 模型返回 tool_calls → 执行工具 → 结果回填 messages → 再次请求
```

不使用 LangChain / LlamaIndex 等任何 Agent 框架，直接调用 OpenAI 兼容接口。代码量小，每一层都可以单独读、单独改。

## 特性

- **零框架依赖** — 只依赖 `openai` SDK 的 HTTP 封装，工具层完全自己实现
- **pydantic 描述工具** — 用 `BaseModel` 声明参数，`@tool` 装饰器自动转成模型的 `tools` 数组
- **插件式加载** — 文件放进 `src/tool/plugins/` 即自动注册，支持单文件与包两种形式
- **Protocol 分层** — `MemoryProtocol` / `ToolExecutorProtocol` / `PluginsLoaderProtocol` 写清组件之间的契约，替换任意一层都不用改别处
- **结构化返回** — 工具统一返回 `{ok, content, error}`，错误信息可直接被模型消费

- **schema 兼容处理** — 剥离 pydantic 自动生成的 `title`，内联 `$ref`/`$defs`，兼容不支持这两个字段的厂商

## 环境要求

- Python 3.12+
- Windows（日志路径与 `taskkill` 进程回收目前是 Windows 专用）
- 任意 OpenAI 兼容端点（DeepSeek / OpenAI / 本地 vLLM 均可）

## 快速开始

```bash
git clone https://github.com/ACGlove/scout.git
cd scout

pip install -r requirements.txt

# 配置密钥（.env 已被 .gitignore 排除，不会上传）
copy src\.env.example src\.env     # Windows
# cp src/.env.example src/.env     # macOS / Linux
```

编辑 `src/.env`，除密钥与模型外还要填 `ROOT`（工具的工作区根目录）和 `TAVILY_API_KEY`（不填则 `search` 插件加载失败）。

启动时会先让你输入 system prompt：

```bash
python -m src
```

`src/__main__.py` 的 `build_agent()` 负责组装 `ConfigContext` → `PluginsLoader` → `ToolManager` → `ToolExecutor` → `Agent`；默认任务写在文件末尾的 `agent('告诉我哔站最近热门的番')`，改那行即可。回答完成后会问「是否满意」，输入 `y` 结束，输入别的内容则当作新建议继续对话。

## 项目结构

```
src/
├── __main__.py             # 入口：日志配置 + 组装组件 + 一次对话
├── config.py               # 环境变量读取
├── deps.py                 # 返回 (model_name, client.chat.completions)
├── agent/
│   ├── agent.py            # 主循环：模型 ↔ 工具，直到模型不再调用工具
│   ├── config_context.py   # 启动配置 dataclass（root、tavily_api_key）
│   ├── plugins_manager.py  # ToolManager：持有工具列表，提供 name → func 映射
│   ├── protocol.py         # Memory / ToolExecutor / PluginsLoader 三个 Protocol
│   └── tool_executor.py    # 工具查找、配置注入、执行与失败重试
├── memory/
│   └── memory.py           # messages 历史（system / user / ai / tool）
└── tool/
    ├── contract.py         # BaseTool 数据契约
    ├── basetool_get.py     # @tool 装饰器 + pydantic → JSON Schema
    ├── plugins_loader.py   # 插件自动发现
    └── plugins/
        ├── get_filepath.py # 列出工作区文件
        ├── read_file.py    # 读文件（超过 200 行分页）
        ├── edit_file.py    # 写文件（自动建父目录）
        └── search/         # 联网搜索（Tavily）
```

## 各组件如何协作

依赖是单向的，改动任何一层都不会牵动其它层：

```python
config_context = ConfigContext()                  # 读 .env
loader         = PluginsLoader()                  # 扫 plugins/ 目录
manager        = ToolManager(plugins_loader=loader)
executor       = ToolExecutor(tools=manager.get_tools(), config=config_context)
agent          = Agent(system=input('设定角色：'), model=get_model(),
                       memory=Memory(), executor=executor)
result = agent('告诉我哔站最近热门的番')
```

- **Agent 不认识工具的具体实现**，只依赖 `executor.get_schema()` 和 `executor.execute(aimsg)` 两个方法
- **ToolExecutor 不认识 memory**：它只负责"造出 tool 消息"并返回，由 Agent 自己 `memory.messages += tool_messages` 塞回去
- **返回空列表等于本轮没有工具调用**，主循环据此进入收尾（问用户是否满意）
- 想换掉任意一层，实现对应的 `Protocol` 即可（测试里就是这么做的）

## 编写一个工具

```python
from pydantic import BaseModel, Field
from ..basetool_get import tool
import json

class Grep_Schema(BaseModel):
    pattern: str = Field(description='要搜索的正则表达式')

@tool(args_schema=Grep_Schema, max_retry=2)
def grep(pattern: str, root: str = ''):
    '''在工作区中按正则搜索文件内容'''
    ...
    return json.dumps({'ok': True, 'content': result, 'error': None})
```

要点：

- **函数名就是工具名**，模型看到的就是它
- **docstring 就是 description —— 它是 prompt，不是注释。** 模型靠它决定什么时候调用你的工具，所以写清「什么时候用、什么时候不要用、参数含义、返回什么」
- `Field(description=...)` 同样会发给模型，写清楚约束（单位、范围、格式）
- **参数名与 `ConfigContext` 字段同名时，执行器自动注入**：函数声明 `root` 就得到工作区路径，声明 `tavily_api_key` 就拿到密钥，工具不需要自己读环境变量
- **模型传入的同名参数会被配置覆盖**，可信值永远来自服务端配置，而不是模型生成
- 放进 `src/tool/plugins/` 即生效；目录形式的插件（如 `search/`）需要在 `__init__.py` 里导入工具对象，加载器靠 `inspect.getmembers` 找 `BaseTool` 实例
- 文件名以 `_` 开头的会被跳过
- 返回 `{ok, content, error}`；失败时把「模型该怎么办」写进 `error`
- 工具名不存在、参数 JSON 解析失败、参数类型不对、函数抛异常——这四种情况执行器都不会抛出，而是**回一条 `role='tool'` 的说明消息**让模型自己纠正

## 设计说明

**配置注入而非模型传参。** `root`、`tavily_api_key` 这类值不该经过模型。`ToolExecutor.get_config()` 用 `inspect.signature` 比对工具函数参数名，只注入名字对得上的字段——签名里没有的字段一个都不塞，否则 `func(**tool_args)` 会直接 `TypeError`。

**重试。** 配额由 `@tool(max_retry=N)` 声明。执行器在参数 JSON 解析失败、参数类型错误或工具抛异常时增加该工具的失败计数，达到上限后先回一条「不要再调用此工具」的提示，再把工具从后续 Schema 里摘掉，模型就看不见它了。成功调用会把计数清零，避免偶发失败攒到上限。

**tool 消息必须一一对应。** 一条 assistant 消息里有几个 `tool_call`，就必须回几条 `role='tool'` 的消息（包括工具名不存在的情况），少一条下一轮请求会被服务商直接拒绝（DeepSeek 返回 422）。

**大文件分页。** `read_file` 单次最多返回 200 行，超量时附带 `next_offset`，模型据此续读。这本质上是**控制单次 tool 消息占用的上下文长度**——把整个文件塞进上下文会挤掉对话历史，也会让长文件必然超窗。



**schema 转换。** pydantic 的 `model_json_schema()` 会产出 `title`（与字段名重复，纯浪费 token）和 `$defs`/`$ref`（部分厂商不支持）。`_strip_titles` 与 `_inline_refs` 在发送前处理掉这两类兼容问题。

## 测试

```bash
pip install pytest
python -m pytest tests/ -v
```

注意用 `python -m pytest` 而不是直接 `pytest`：前者会把当前目录加进 `sys.path`，测试文件才能 `import src`。

17 个用例，按「造状态 → 调方法 → 断言」的组织方式：

| 文件 | 覆盖 |
|---|---|
| `tests/test_agent.py` | system 消息入 memory、无工具时一轮收尾、有工具时转两圈、用户反馈不满意继续循环 |
| `tests/test_tool_executor.py` | 无工具调用返回空列表、成功路径、坏 JSON、工具名不存在、空参数、配置覆盖模型参数、重试上限与禁用、TypeError 分支、多 tool_call 一一回复、成功清零计数、只注入签名中存在的字段 |
| `tests/test_edit_file.py` | 写入成功、路径越权被拦、目标指向目录（用 `tmp_path`） |
| `tests/test_plugins_loader.py` | 至少加载出预期的一批工具，且全是 `BaseTool` |

测试的取舍，也是这个项目最值得学的一课：

- **判断类用真的还是假的** —— 问两个问题：「这个零件会不会碰外部世界（网络、键盘、真实文件、真实时间）？」「我想断言的东西是不是就在这个零件里？」Agent 碰网络（`model.create`）、键盘（`input`）、外部世界（真去跑工具），所以三个都换假货，只留 Agent 自己的循环逻辑是真的
- **假货只需要有数据形状** —— `SimpleNamespace` / 小类就够了，不必继承真类。`execute` 只用到 `tool_calls` 一条路径，就只造这一条
- **不读环境变量** —— 假 `ConfigContext`（`FakeConfig`）把值写死，否则测试会绑死在你这台机器的 `ROOT` 上，换台机器就红，而红的原因跟被测逻辑无关
- **monkeypatch 替换 `builtins.input`** —— 测试里没有终端输入，不替换程序会挂在那里等。想测「循环转两圈」就用一个列表当队列：`answers = [...]; monkeypatch.setattr('builtins.input', lambda prompt='': answers.pop(0))`，让替身按需取货
- **断言用固定字段，忽略动态变量** —— 用 `'path 指向的是目录' in result['error']`，而不是整串比较（整串里带路径，换台机器就红）
- **`<=` 想表示"包含"只喂 `set`** —— `['a','b'] <= ['b','c']` 是字典序比较，`{'a','b'} <= {'b','c'}` 才是子集判断

## 已知限制

当前是学习阶段的版本，以下问题仍待处理：

- [ ] 主循环 `while True` 没有步数上限，模型可能陷入死循环
- [ ] `messages` 只增不减，长对话会持续膨胀直到超出上下文窗口
- [ ] 工具失败计数保存在 `ToolExecutor` 实例中，尚未按每次用户任务重置
- [ ] `disabled_tools` 是 list，重复触发会重复 append（`get_schema` 里用 `set()` 兜住了）
- [ ] CLI 交互（`print` / `input`）仍耦合在 Agent 循环内部（`src/agent/agent.py:41`），无法批量化运行
- [ ] 暂无流式输出
- [ ] 工具返回形状不统一：`edit_file` 越权分支缺 `content` 键，`read_file` / `get_filepath` 用字符串而不是对象表示 `error`
- [ ] `read_file` 说好 200 行，实际会给出 201 行（`src/tool/plugins/read_file.py:48`）
- [ ] 联网搜索仍缺少集成测试
- [ ] `Agent.__call__` 只测了正常路径，模型/执行器抛异常时的行为没有覆盖

## 安全提示

`edit_file` 会在 `ROOT` 范围内写入文件。**不要把它接到不可信的输入上**，也不要在敏感目录里设置 `ROOT`：把它指向一个专门的工作目录，而不是家目录或项目源码根。

工具返回的文本（尤其是 `search` 的联网结果）属于不可信内容，会被原样拼进上下文——这是提示注入的入口。

`.env` 已被 `.gitignore` 排除（`.env`、`.env.*`，保留 `!.env.example`）。**密钥一旦进过 git 历史，删文件不等于删历史**，只能去服务商后台作废重发。

## License

MIT