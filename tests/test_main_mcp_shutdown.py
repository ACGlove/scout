"""main() 抛异常时，finally 里的 stack.aclose() 必须把 mcp 子进程关掉。

不跑真的 mcp 服务：只把 McpLoader.setup 换成"起一个子进程、压进 stack"，
这样测的仍然是 main() 的 try/finally 和 aclose()。
"""
import asyncio
import sys

import pytest

from src import __main__ as main_mod
from src.tool.mcp_tool.mcp_manager import McpLoader

# 只睡不干活，否则它自己就退出了，测不出是谁关的
SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]


async def _stop(proc):
    proc.terminate()
    await proc.wait()


def test_main_closes_mcp_child_when_build_agent_raises(monkeypatch):
    procs = []

    async def setup(self):          # 替换真 setup：不连 mcp，只起子进程交给 stack
        proc = await asyncio.create_subprocess_exec(*SLEEPER)
        procs.append(proc)
        self.stack.push_async_callback(_stop, proc)

    async def boom(mcp_loader):
        raise RuntimeError("build_agent 炸了")

    monkeypatch.setattr(McpLoader, "setup", setup)
    monkeypatch.setattr(main_mod, "build_agent", boom)

    with pytest.raises(RuntimeError, match="build_agent 炸了"):
        asyncio.run(main_mod.main())

    assert len(procs) == 1, "子进程没启动，测试没测到东西"
    assert procs[0].returncode is not None, "main() 抛异常后 mcp 子进程还活着"