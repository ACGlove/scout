# Scout

一个从零实现的轻量 LLM Agent 框架，用来学习 **function calling 的完整链路**：

```
工具定义 → JSON Schema 生成 → 插件发现 → 注册 → 随请求发给模型
   → 模型返回 tool_calls → 执行工具 → 结果回填 messages → 再次请求
```

不使用 LangChain / LlamaIndex 等任何 Agent 框架，直接调用 OpenAI 兼容接口。代码量小，每一层都可以单独读、单独改。

## 特性

- **零框架依赖** — 只依赖 `openai` SDK 的 HTTP 封装，工具层完全自己实现
- **pydantic 描述工具** — 用 `BaseModel` 声明参数，`@tool` 装饰器自动转成模型的 `tools` 数组
- **插件式加载** — 文件放进 `src/tool/plugins/` 即自动注册，支持单文件与包两种形式
- **结构化返回** — 工具统一返回 `{ok, content, error}`，错误信息可直接被模型消费
- **可控的命令执行** — 超时控制、进程树回收、stdin 分离、环境变量过滤
- **schema 兼容处理** — 剥离 pydantic 自动生成的 `title`，内联 `$ref`/`$defs`，兼容不支持这两个字段的厂商

## 环境要求

- Python 3.12+
- Windows（日志路径与 `taskkill` 进程回收目前是 Windows 专用）
- 任意 OpenAI 兼容端点（DeepSeek / OpenAI / 本地 vLLM 均可）

## 快速开始

```bash
git clone https://github.com/<your-name>/scout.git
cd scout

pip install -r requirements.txt

# 配置密钥（.env 已被 .gitignore 排除，不会上传）
copy src\.env.example src\.env     # Windows
# cp src/.env.example src/.env     # macOS / Linux
```

编辑 `src/.env` 填入 `API_KEY`、`BASE_URL`、`MODEL`、`ROOT`。

运行：

```bash
python -m src
```

任务在 `src/__main__.py` 的 `llm_call()` 里，改 `query` 参数即可。

## 项目结构

```
src/
├── __main__.py           # 入口：日志配置 + 一次对话
├── config.py             # 环境变量读取
├── deps.py               # OpenAI 客户端（chat.completions）
├── agent/
│   ├── agent.py          # 主循环：模型 ↔ 工具，直到模型不再调用工具
│   └── tool_executor.py  # 工具执行、root 注入、失败重试
├── memory/
│   └── memory.py         # messages 历史（system / user / ai / tool）
└── tool/
    ├── contract.py       # BaseTool 数据契约
    ├── basetool_get.py   # @tool 装饰器 + pydantic → JSON Schema
    ├── registry.py       # 注册表：schema / name→func / 重试配额
    ├── plugins_loader.py # 插件自动发现
    └── plugins/
        ├── get_filepath.py
        ├── read_file.py
        ├── write_file.py
        ├── run_command.py
        └── search/       # 联网搜索（Tavily）
```

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
- **docstring 就是 description —— 它是 prompt，不是注释。** 模型靠它决定什么时候调用你的工具
- `Field(description=...)` 同样会发给模型，写清楚约束（单位、范围、格式）
- 参数列表中带 `root` 时，执行器会自动注入工作区路径（工具不需要知道环境变量）
- 放进 `src/tool/plugins/` 即生效；目录形式的插件需要在 `__init__.py` 里导入工具对象
- 返回 `{ok, content, error}`；失败时把「模型该怎么办」写进 `error`

## 设计说明

**大文件分页。** `read_file` 单次最多返回 200 行，超量时附带 `next_offset`，模型据此续读。这本质上是**控制单次 tool 消息占用的上下文长度**——把整个文件塞进上下文会挤掉对话历史，也会让长文件必然超窗。

**重试。** 配额由 `@tool(max_retry=N)` 声明，执行器在工具抛异常时扣减，归零后向模型回传终止信号（而不是抛错），避免模型在同一个坑里反复重试。失败次数会在日志中逐步打印。

**schema 转换。** pydantic 的 `model_json_schema()` 会产出 `title`（与字段名重复，纯浪费 token）和 `$defs`/`$ref`（部分厂商不支持）。`_strip_titles` 与 `_inline_refs` 在发送前处理掉这两类兼容问题。

## 已知限制

当前是学习阶段的版本，以下问题已知未修：

- [ ] 主循环 `while True` 没有步数上限，模型可能陷入死循环
- [ ] `messages` 只增不减，长对话会持续膨胀直到超出上下文窗口
- [ ] 失败计数是全局的，且不随新任务重置
- [ ] 没有单元测试
- [ ] CLI 交互（`print` / `input`）耦合在 Agent 循环内部，无法批量化运行
- [ ] 暂无流式输出

## 安全提示

`run_command` 与 `write_file` 会在工作区内执行命令、写入文件。**不要把它接到不可信的输入上**，也不要在敏感目录里设置 `ROOT`。

工具返回的文本（尤其是 `search` 的联网结果）属于不可信内容，会被拼进上下文——这是提示注入的入口。

## License

MIT
