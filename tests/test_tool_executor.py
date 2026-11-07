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


def fake_aimsg(*calls):
    return SimpleNamespace(
        tool_calls = [
            SimpleNamespace(
                id = tid,
                function = SimpleNamespace(name = name,arguments = args)
            )
        for tid,name,args in calls]
    )

def make_tools(name, func, max_retry=2):
    return BaseTool(
        func = func,
        json_schema = {'type': 'function', 'function': {'name': name}},
        name = name,
        max_retry = max_retry
    )

def make_executor(*tools):
    hooks = HookManager()
    hooks.register()
    return ToolExecutor(
        hooks=hooks,
        tools=list(tools),
        config=FakeConfig()
    )

def test_no_tool_call_returns_empty_list():    #测试没有工具的返回
    ex = make_executor(make_tools('ehol',lambda:'x'))
    assert asyncio.run(ex.execute(fake_aimsg())) == []   #测没有tool_calls的路径


def test_success_returns_one_tool_message():  #测试有工具的正常返回
    ex = make_executor(make_tools('ehol',lambda word:f'ehol{word}'))
    messages = asyncio.run(ex.execute(
        aimsg=fake_aimsg(
            ('id','ehol','{"word":"hello"}')   #这里的arguments必须是json字符串,这样json.loads(arguments)才不会报错,json字符串里的键值必须是"",外面用''包裹
        )
    ))
    assert messages == [{'role':"tool",'tool_call_id':'id','content':'eholhello'}]

    
def test_bad_json_arguments_are_reported():  #失败路径:模型给了非法json参数
    called = []
    ex = make_executor(make_tools('ehol', lambda word: called.append('不该跑到这里')))
    messages = asyncio.run(ex.execute(
        aimsg=fake_aimsg(('id', 'ehol', "{'word': 'hello'}"))   # 单引号,不是 JSON
    ))
    #json.JSONDecodeError错误
    assert len(messages) == 1       #断言失败一定有一条错误消息返回给大模型,防止消息格式不正确
    assert 'arguments的json解析失败' in messages[0]['content']   #代码中先json.loads解析,再传入func执行
    assert ex.error_retry['ehol'] == 1   #测试失败计数正常执行
  
    #可以证明工具有没有被真的调用（失败应该发生在解析阶段，工具不该产生任何副作用）
    assert called == []  

#未知工具名：这条会走另一个钩子（tool_name_error），而且它发生在 is_tool_accept_call 之前，注意 error_retry 不会被加
def test_unknown_tool_name_is_reported():
    ex = make_executor(make_tools('ehol', lambda: 'x'))
    messages = asyncio.run(ex.execute(
        aimsg=fake_aimsg(('id', 'wrong_name', '{}'))
    ))
    assert len(messages) == 1
    assert '工具名不存在' in messages[0]['content']
    assert ex.error_retry['ehol'] == 0   #失败不计数
    assert 'wrong_name' not in ex.error_retry   #错误工具名不会污染两张表
    assert 'wrong_name' not in ex.func_retry