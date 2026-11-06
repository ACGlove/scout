"""测试 tavily 工具连续调用失败后是否被 ToolExecutor 禁用。

用假类替代真实 TavilySearchTool，在调用方法里 raise TimeoutError，
模拟多轮 tool_call，验证 error_retry 累计到 max_retry 后
工具名出现在 self.disabled_tools 中。
"""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from src.agent.tool_executor import ToolExecutor
from src.tool.contract import BaseTool
from src.hooks.hook_manager import HookManager


@dataclass(frozen=True)
class FakeConfig:
    """和 ConfigContext 字段对齐的假配置，避免 get_config 里 fields() 报错。"""
    root: str | None = 'E:/fake/root'
    tavily_client: object = 'fake-client'


# ── 假货工厂 ──────────────────────────────────────────────

class FakeTavily:
    """假装是 TavilySearchTool：名字、签名都对得上，但一调就超时。"""

    def __call__(self, query: str, **kwargs) -> str:
        raise TimeoutError("Connection to Tavily API timed out")


def fake_aimsg(*calls):
    return SimpleNamespace(tool_calls=[
        SimpleNamespace(
            id=tid,
            function=SimpleNamespace(name=name, arguments=args),
        )
        for tid, name, args in calls
    ])


def make_executor(max_retry: int = 3):
    fake_tool = BaseTool(
        func=FakeTavily(),
        json_schema={
            "type": "function",
            "function": {"name": "tavily_search"},
        },
        name="tavily_search",
        max_retry=max_retry,
    )
    hooks = HookManager()
    hooks.register()
    return ToolExecutor(tools=[fake_tool], config=FakeConfig(), hooks=hooks)


def run(coro_func, **kwargs):
    return asyncio.run(coro_func(**kwargs))


# ── 测试 ──────────────────────────────────────────────────

def test_consecutive_failures_disable_tavily():
    """连续 max_retry 次 TimeoutError 后，tavily_search 必须进入 disabled_tools。"""
    ex = make_executor(max_retry=3)

    # 第 1~3 轮：每次都失败，error_retry 逐步累加
    for i in range(1, 4):
        msgs = run(ex.execute, aimsg=fake_aimsg((f"c{i}", "tavily_search", '{"query":"test"}')))
        assert len(msgs) == 1
        assert "工具调用失败" in msgs[0]["content"]
        assert ex.error_retry["tavily_search"] == i

    # 此时还没禁用（error_retry == max_retry，但 is_tool_accept_call 是 >= 才拦）
    assert "tavily_search" not in ex.disabled_tools

    # 第 4 轮：触发上限拦截
    msgs = run(ex.execute, aimsg=fake_aimsg(("c4", "tavily_search", '{"query":"test"}')))
    assert "重试次数达到上限" in msgs[0]["content"]
    assert "tavily_search" in ex.disabled_tools


def test_disabled_tool_excluded_from_schema():
    """被禁用的工具不再出现在 get_schema() 返回的列表里。"""
    ex = make_executor(max_retry=2)

    # 两轮失败 + 一轮触发上限
    run(ex.execute, aimsg=fake_aimsg(("c1", "tavily_search", '{"query":"a"}')))
    run(ex.execute, aimsg=fake_aimsg(("c2", "tavily_search", '{"query":"b"}')))
    run(ex.execute, aimsg=fake_aimsg(("c3", "tavily_search", '{"query":"c"}')))

    assert ex.get_schema() == []


def test_multiple_calls_in_one_message_all_count():
    """一条 assistant 消息里塞多个 tavily_search 调用，每个都独立计数。"""
    ex = make_executor(max_retry=2)

    msgs = run(ex.execute, aimsg=fake_aimsg(
        ("c1", "tavily_search", '{"query":"x"}'),
        ("c2", "tavily_search", '{"query":"y"}'),
    ))

    # 两个调用都失败，error_retry 应该累加到 2
    assert len(msgs) == 2
    assert ex.error_retry["tavily_search"] == 2

    # 下一轮直接触发上限
    msgs = run(ex.execute, aimsg=fake_aimsg(("c3", "tavily_search", '{"query":"z"}')))
    assert "重试次数达到上限" in msgs[0]["content"]
    assert "tavily_search" in ex.disabled_tools
