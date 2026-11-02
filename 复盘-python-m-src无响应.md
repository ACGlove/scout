# `python -m src` 没有反应 —— 一次“错误被自己吞掉”的事故复盘

> 适用项目：`E:\agentpra\pra\pr\scout`
> 现象：在终端敲 `python -m src`，光标停住，**一个字都不输出**，也不报错，也不退出。
> 结论：不是环境问题，也不是 MCP 装坏了。是**两个代码错误叠在一起**——一个让程序必然出错，另一个让这个错误永远无法被看见。

---

## 一、三句话版本

1. 重构时把 `McpLoader.load_tools()` 改成了 `async`（异步），但上层的 `get_tools()` 忘了跟着改，还在把“一张待办小票”当成“已经做好的菜”去拼接列表，于是当场抛 `TypeError`。
2. 抛出异常时，代码还没有执行到“关闭 MCP 连接”那一步，MCP 子进程一直活着、管道一直开着。
3. Python 在退出前要等所有后台任务收工，而其中一个任务正卡在“读这个子进程的输出”上，只要子进程不关管道它就永远等下去 —— 于是程序既不退出，也来不及把第 1 步的报错打印出来。

**一句话：第一个 bug 让程序必然出错，第二个 bug 让错误无法被发现。**

---

## 二、你看到的现象，和它对应的真相

| 你看到的 | 你以为的 | 实际发生的 |
|---|---|---|
| 没有任何输出 | 代码没跑 / 卡在启动 | 代码跑了，甚至 MCP 都启动成功了 |
| 不报错 | 代码逻辑没问题 | 有 `TypeError`，但它卡在“打印之前” |
| 不退出（要 Ctrl+C） | 死循环 / 死锁 | 退出流程在等一个永远等不来的读操作 |
| `src/record.log` 是 0 字节 | 日志配置坏了 | 日志在 agent 第一行才写，而程序根本没走到那里 |

> 小提示：`record.log` 每次启动都会被覆盖（`filemode='w'`），所以“0 字节”只说明这次运行没写进 agent，不代表日志功能坏了。

---

## 三、事故前的改动：一次“只改了一半”的重构

MCP 的加载器 `McpLoader` 里，`load_tools` 从同步函数改成了异步函数：

```python
# src/tool/mcp_tool/mcp_manager.py
async def load_tools(self) -> list[BaseTool]:
    ...
```

这个改动本身是对的（因为要等子进程握手，只能用异步）。问题是**调用它的地方没有全部跟着改**。你的 `ToolManager.get_tools` 还是老样子：

```python
# src/agent/plugins_manager.py（出错前的代码）
def get_tools(self) -> list[BaseTool]:
    tools = self.loader.load_plugins()
    mcp_tools = self.mcp_loader.load_tools()   # ← 这里
    wrap_tools = tools + mcp_tools
```

---

## 四、错误一：`load_tools()` 前面少了一个 `await`

### 4.1 先把“协程”讲清楚

调用一个 `async def` 函数，**不会执行函数体**，它只会返回一个“待办小票”（协程对象）。真正执行要靠 `await`：

```python
x = load_tools()          # 得到一张小票，函数体一行都没跑
x = await load_tools()    # 把小票交给事件循环，等它真正执行完，拿到结果
```

所以 `mcp_tools = self.mcp_loader.load_tools()` 这一行，`mcp_tools` 里装的**不是工具列表，而是一张没被兑现的小票**。

### 4.2 于是下一行必然爆炸

```python
wrap_tools = tools + mcp_tools
```

`tools` 是 `list`，`mcp_tools` 是协程对象。Python 报：

```
TypeError: can only concatenate list (not "coroutine") to list
```

同时在垃圾回收时还会补一句警告：

```
RuntimeWarning: coroutine 'McpLoader.load_tools' was never awaited
```

### 4.3 为什么 `TypeError` 没打印出来？

因为它遇到了错误二。

### 4.4 为什么“静态检查”没帮你发现？

因为三处都在说谎：

- `get_tools` 的返回标注写着 `-> list[BaseTool]`，但它实际返回的是“小票 + 列表”的拼接结果；
- `src/agent/protocol.py` 里 `McpLoaderProtocol` 还写着 `def load_tools(self)`（同步），和实现不一致；
- Python 运行时不校验返回标注，只把它当注释。

**教训：`async` 是会“向上传染”的。** 一个函数变异步，它的调用者、调用者的调用者……整条链都得变异步。你改了中间两环（`build_agent`、`main`），漏了最关键的 `get_tools`，而程序不会因此编译失败，只会在运行时炸。

---

## 五、错误二：出异常时没有关掉 MCP 连接

### 5.1 原来的 `main()` 长这样（简化）

```python
mcp_loader = McpLoader()
await mcp_loader.setup()          # 启动子进程，建立连接
agent = await build_agent(mcp_loader)   # ← 这里会抛 TypeError
result = await agent("...")
await mcp_loader.stack.aclose()   # ← 永远走不到
```

`build_agent` 里调用了 `get_tools()`，`TypeError` 就在这里抛出。于是 `aclose()` 被跳过。

### 5.2 `aclose()` 被跳过意味着什么

MCP 是“父进程 + 子进程”的结构：父进程（你的程序）通过两根管道和子进程（`mcp_server_fetch`）通信。`aclose()` 要做三件事：

1. 通知后台“别再读了”；
2. 关掉管道；
3. 等子进程退出。

这三件事没做，子进程就一直活着，管道就一直开着。

### 5.3 这里的“收尾”有两层，别混

**第一层：你自己写的收尾。** 就是那句 `await mcp_loader.stack.aclose()`。它负责通知子进程下班、关掉管道。它本该放在 `finally` 里，但原来的代码写在流程末尾，一出错就被跳过。

**第二层：`asyncio.run()` 自动做的收尾。** 它不关心你业务上要关什么，只做一件事：把还活着的后台任务全部取消，并**等它们真正结束**。“读子进程输出”就是这样一个后台任务。

两层是因果关系：

```
get_tools 出错 → TypeError 已经产生
        ↓
第一层收尾（aclose）：被跳过 ❌        ← 子进程和管道都还开着
        ↓
第二层收尾（asyncio.run）：
    取消“读子进程”的后台任务
    等它结束 → 它卡在管道读上 → 永远等  ← 卡在这里
        ↓
打印 traceback、退出                    ← 永远到不了
```

一句话：**第一层没做，导致第二层永远做不完，于是报错永远打不出来。**

### 5.4 于是 Python 在退出时卡住

`asyncio.run()` 在退出前有一个固定动作：**把所有还开着的后台任务取消掉，并等它们真正结束**。这些后台任务里有一个是“读子进程输出”的任务，它正卡在“等管道来数据”上。

- 取消，只是“请求”，任务要在下一个等待点才会响应；
- 它卡在管道读上，回不到等待点；
- 只有管道另一端关闭（子进程退出），这个读才会结束。

**子进程不退 → 读不结束 → 任务不结束 → 退出流程不结束 → 程序永远挂着。**

此时报错信息其实早就生成好了，只是卡在“打印”之前。

### 5.5 为什么报错不是“一出现就打印”（实验 A、B）

很多人以为“异常一发生，进程立刻崩掉并打印报错”。在顶层同步代码里确实如此，但“崩溃”其实分两步：先把异常沿调用栈向上抛，穿过所有收尾动作，最后由解释器打印 traceback、以退出码 1 结束。**收尾拖多久，报错就晚多久。**

**实验 A（纯同步，没有 async）**：在 `finally` 里睡 3 秒，并给 `sys.excepthook` 打时间戳：

```python
import sys, time
def ts(): return time.strftime("%H:%M:%S")
def hook(t, v, tb):
    print(f"[{ts()}] 解释器准备打印 traceback", file=sys.stderr)
    sys.__excepthook__(t, v, tb)
sys.excepthook = hook
try:
    print(f"[{ts()}] 异常发生")
    raise ValueError("A: 出错了")
finally:
    print(f"[{ts()}] finally 开始收尾，睡 3 秒")
    time.sleep(3)
    print(f"[{ts()}] finally 收尾结束")
```

实测输出：

```
[18:02:54] 异常发生
[18:02:54] finally 开始收尾，睡 3 秒
[18:02:57] finally 收尾结束
[18:02:57] 解释器准备打印 traceback
...
ValueError: A: 出错了
```

异常在 :54 就发生了，报错 :57 才出现。注意这里**没有 async** —— 报错延迟和异步无关，只和“收尾里等了多久”有关。这次把 3 秒换成了“永远”。

**实验 B（异步的反面）**：后台任务里的错误，如果没人 `await`，根本不会让进程崩：

```python
async def boom():
    raise RuntimeError("B: 后台任务炸了")

async def main():
    asyncio.create_task(boom())   # 起了任务，但从不 await
    await asyncio.sleep(0.2)

asyncio.run(main())
print("主流程照常结束")
```

实测输出：

```
主流程照常结束
===== 退出码: 0 =====
（stderr）Task exception was never retrieved ... RuntimeError: B: 后台任务炸了
```

退出码是 0，看起来完全正常；错误只被存进 Task 对象，直到垃圾回收时才补一句抱怨。

所以异常在异步代码里有两种结局：

| 结局 | 条件 | 你看到什么 |
|---|---|---|
| 被收尾拖住 | 错误沿 `await` 链冒出，但收尾卡住 | 无输出、不退出（**本次事故**） |
| 被彻底吞掉 | 错误在没人 `await` 的后台任务里 | 一切正常，退出码 0 |

这次是第一种：`TypeError` 确实冒出来了、没丢，只是排在收尾后面，而收尾永远结束不了。

“错误一出现就崩”需要同时满足三个前提：错误在主执行路径上、传播路上没有阻塞的收尾、中途没人捕获它。缺一个，“立即崩溃”就不成立。

> 补充：Python 里没有真正“立即终止”的异常。连 `sys.exit()` 也是抛 `SystemExit`，照样走完 `finally`；只有 `os._exit()` 或解释器自身崩溃才会跳过收尾。

### 5.6 我们做的验证实验

写了一个 8 行的最小脚本：启动 MCP，然后故意抛 `TypeError`，不关连接。

| 时刻 | 观察结果 |
|---|---|
| 启动后 12 秒 | 进程活着，日志只到“mcp 已启动”，没有报错 |
| 手动杀掉 MCP 子进程 | **6 秒内**父进程退出，并打印出完整 `TypeError` |

我们什么都没改父进程，只是关掉了管道另一头。这证明：**不是子进程在“卡”父进程，而是父进程在等一个只有子进程关闭管道才能完成的“读结束”。** 子进程自己 CPU 占用为 0，它只是安静地握着管道。

### 5.7 为什么这个错误比第一个更危险

`aclose()` 缺失会**吞掉所有类型的异常**：不止这次的 `TypeError`，任何发生在它之前的错误都会变成“没反应”。排查时你会误以为是网络慢、模型超时、代码没跑，实际上程序早就崩了。

---

## 六、两个错误叠加的完整时间线

```
你敲下 python -m src
   │
   ├─ 加载配置、启动 MCP 子进程            ✅ 成功（所以看起来“在跑”）
   ├─ build_agent → get_tools
   │     └─ tools + 协程对象               ❌ TypeError
   │
   ├─ 抛出异常 → 跳过 aclose()              ⚠️ 子进程还活着，管道还开着
   │
   └─ asyncio.run 准备退出
         └─ 等“读子进程输出”的后台任务结束
               └─ 该任务卡在管道读上
                     └─ 子进程不退 → 永远等  → 界面“无反应”
```

---

## 七、修复清单

一共改了 4 个文件。核心思路：**把异步链补齐 + 保证异常时也一定关连接**。

### 7.1 `src/agent/plugins_manager.py` —— 补 `async` 和 `await`

```diff
- def get_tools(self) -> list[BaseTool]:
+ async def get_tools(self) -> list[BaseTool]:
      tools = self.loader.load_plugins()
-     mcp_tools = self.mcp_loader.load_tools()
+     mcp_tools = await self.mcp_loader.load_tools()
      wrap_tools = tools + mcp_tools
```

### 7.2 `src/agent/protocol.py` —— 让“接口声明”和实现一致

```diff
  class McpLoaderProtocol(Protocol):
-     def setup(self) -> None: ...
-     def load_tools(self) -> list[BaseTool]: ...
+     async def setup(self) -> None: ...
+     async def load_tools(self) -> list[BaseTool]: ...
```

> 这一步不是“为了让程序跑起来”，而是为了让类型检查器以后能抓到同类错误。声明说谎，检查器就帮不了你。

### 7.3 `src/__main__.py` —— `try/finally` 保证一定关连接

```python
async def main() -> None:
    mcp_loader = McpLoader()
    await mcp_loader.setup()
    try:
        agent = await build_agent(mcp_loader)
        result = await agent("...")
    finally:
        await mcp_loader.stack.aclose()   # 无论成功还是抛异常，都执行
```

同时 `build_agent` 改成 `async def`，并在里面 `tools = await tool_manager.get_tools()`。

### 7.4 `src/agent/agent.py` —— 顺带修掉一个“镜像错误”

原代码：

```python
await asyncio.to_thread(self.model.create(messages=..., tools=...))
```

这里 `self.model.create(...)` 的括号写在了里面，意思是“**先在主线程把请求发完**，再把结果交给线程池”，等于同步阻塞，异步白写了。正确写法是把函数和参数分开传：

```python
await asyncio.to_thread(self.model.create, model=..., messages=..., tools=...)
```

同理，`input()` 也要这样包：

```python
await asyncio.to_thread(input, "对回答是否满意:\n")
```

> 判断标准：`await` 右边必须是“**还没开始执行**的东西”。如果它已经执行完了，`await` 就只是个摆设。

---

## 八、我是怎么定位的（这套流程可以复用）

1. **先确认代码到底跑没跑**
   看日志文件：0 字节 → 说明没进到 agent 第一行。这一步就排除了“模型/网络慢”。

2. **确认环境没问题**
   检查解释器版本、依赖包（mcp、openai、anyio 都在）、`.env` 配置。都正常 → 问题在代码。

3. **给卡住的进程拍一张“快照”**
   用 `faulthandler` 在 10 秒后打印所有线程的调用栈。看到栈停在“等待网络/管道事件”的收尾流程里，而不是业务代码里 → 说明是**退出流程卡住**，不是逻辑死循环。

4. **写最小复现**
   把“启动 MCP → 故意报错 → 不关连接”缩成 30 行脚本。它稳定复现卡死 → 证明与业务无关。

5. **做对照实验**
   卡住时杀掉子进程，父进程立刻恢复并打印报错 → 锁定“子进程管道 + 未关闭的连接”是根因。

6. **修完做端到端验证**
   - `python -m src` 空输入：立刻打印“设定角色：”，随后正常 `EOFError` 退出（不再卡）；
   - 工具装配：6 个工具（`edit_file`、`get_filepath`、`read_file`、`run_command`、`search`、`fetch`）；
   - 真实调用 `fetch https://example.com` 返回页面内容；
   - 真实对话一轮返回“收到”，日志齐全，进程正常退出。

---

## 九、以后怎么避免（照着做就行）

### 9.1 改 `async` 时，顺着调用链一路改到底

用编辑器的“查找引用”功能，从被改的函数往上找，一直改到 `main`。**只要中间有一环没改，就一定会炸**，而且往往是运行到一半才炸。

### 9.2 有资源的地方，一律 `try/finally`

```python
try:
    ...
finally:
    await close_everything()
```

判断标准：**“如果这里抛异常，还有什么东西会留在外面？”** 子进程、文件、连接、锁，都算。

### 9.3 打开“未 await 协程”的报警

```powershell
python -X dev -W error::RuntimeWarning -m src
```

正常情况下会直接报 `coroutine ... was never awaited`，不用等到卡死。

### 9.4 跑一次类型检查

```powershell
mypy src
```

它能看到“标注说返回 list，实际却是协程”这种矛盾 —— 前提是 `protocol.py` 里的声明是真实的。

### 9.5 别在“卡住”时干等

下次遇到“没反应”，先做三件事：看日志文件、看子进程还在不在、按 Ctrl+C 看它停在哪个栈。**能复现的卡死，一定有可以观测的现场。**

---

## 十、留给你自己判断的两件事（我还没动）

1. **测试过期**：`tests/test_tool_executor.py` 里 10 个用例还按“同步调用”写（`ex.execute(...)`），但 `execute` 早就改成了 `async def`，所以报 `object of type 'coroutine' has no len()`。这是之前 commit `356c885`（“改成异步执行工具”）留下的，不是这次改动引入的。修法是把调用包进 `asyncio.run(...)`。
2. **`mypy src` 还没跑**：跑一次能看出还有多少“声明与实现不一致”，尤其是 `protocol.py` 里那几个 `Protocol`。

---

## 十一、术语小抄

| 词 | 大白话 |
|---|---|
| 协程（coroutine） | 调用 `async def` 函数拿到的“待办小票”，不是结果 |
| `await` | 把小票交出去、等它真正做完、拿回结果 |
| 事件循环 | 一个“总调度”，负责把等待中的任务轮流推进 |
| 异步传染 | 一个函数变 `async`，所有调用它的函数都得跟着变 |
| 子进程 | 你的程序另外启动的一个独立程序（这里指 `mcp_server_fetch`） |
| 管道 | 父子进程之间传数据的通道；一端不关，另一端的“读”就一直等 |
| 收尾 | 程序结束前必须做完的打扫（关文件、关连接、停后台任务），发生在报错打印之前 |
| 后台任务 | 用 `create_task` 之类起在背后跑的任务，没人 `await` 它时，它出错也不会让进程崩 |
| `traceback` | 报错时那一段“哪个文件第几行出错”的调用栈信息 |
| 事件循环收尾 | 程序退出前，把还开着的后台任务取消并等它们结束 |

---

## 十二、一页速查

- **症状**：`python -m src` 无输出、无报错、不退出。
- **根因 1**：`load_tools` 变 `async` 后，`get_tools` 忘记 `await` → `list + coroutine` 的 `TypeError`。
- **根因 2**：异常时没执行 `stack.aclose()` → 子进程和管道还在 → 退出流程死等。
- **关键证据**：卡住 12 秒无输出；杀掉子进程后 6 秒内打印完整 `TypeError` 并退出。
- **为什么看起来像没反应**：异常要等收尾做完才打印；收尾被“等子进程”卡住，报错就永远排不上号。
- **修法**：`async def get_tools` + `await load_tools()`；`protocol.py` 同步改签名；`main()` 用 `try/finally` 包住 `aclose()`；顺手修 `to_thread(func(...))` 的写法。
- **验证**：空输入正常 `EOFError` 退出；6 个工具装配成功；`fetch` 真实返回；一轮对话返回“收到”。
- **预防**：`try/finally`、`-W error::RuntimeWarning`、`mypy src`、异步改动顺着调用链改到底。
