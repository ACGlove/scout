"""tool_executor 的单元测试。

契约（改代码之前先对齐这三行）：
  execute(aimsg) -> list[dict]     每条形如 {'role':'tool','tool_call_id':工具调用id,'content':字符串}
  execute 只管"造消息"，不碰 memory；谁调用谁负责塞回去（agent.py 里是 memory.messages += tool_messages）
  返回空列表 == 本轮没有工具调用，主循环该收尾

为什么用 FakeConfig 而不是真的 ConfigContext：
  真 ConfigContext 的 default_factory 会去读 .env，测试就绑死在这台机器的 ROOT 上了。
  换台机器就红，而红的原因跟我测的逻辑无关——测试不该依赖运行环境。
"""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from src.agent.tool_executor import ToolExecutor
from src.tool.contract import BaseTool
from src.hooks.hook_manager import HookManager


@dataclass(frozen=True)
class FakeConfig:
    root: str | None = 'E:/fake/root'
    tavily_client: object = 'fake-client'
