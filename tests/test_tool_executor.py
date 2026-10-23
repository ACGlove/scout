"""tool_executor 的单元测试。

契约（改代码之前先对齐这三行）：
  execute(aimsg) -> list[dict]     每条形如 {'role':'tool','tool_call_id':工具调用id,'content':字符串}
  execute 只管"造消息"，不碰 memory；谁调用谁负责塞回去（agent.py 里是 memory.messages += tool_messages）
  返回空列表 == 本轮没有工具调用，主循环该收尾

为什么用 FakeConfig 而不是真的 ConfigContext：
  真 ConfigContext 的 default_factory 会去读 .env，测试就绑死在这台机器的 ROOT 上了。
  换台机器就红，而红的原因跟我测的逻辑无关——测试不该依赖运行环境。
"""

from dataclasses import dataclass
from types import SimpleNamespace

from src.agent.tool_executor import ToolExecutor
from src.tool.contract import BaseTool


@dataclass(frozen=True)
class FakeConfig:
    """形状和 ConfigContext 一样，但值是我写死的，不读环境变量。"""

    root: str | None = 'E:/fake/root'
    tavily_api_key: str | None = 'tvly-fake'


def fake_aimsg(*calls):
    """假的 assistant 消息：execute 只用到 tool_calls 这一条路径。

    SimpleNamespace 是"只有数据形状、没有类型和行为"的假货，
    单个 tool_call 需要 id / function.name / function.arguments 三个属性。
    """
    return SimpleNamespace(tool_calls=[
        SimpleNamespace(
            id=tid,
            function=SimpleNamespace(name=name, arguments=args),
        )
        for tid, name, args in calls
    ])


def make_tool(name, func, max_retry=2):
    """把「名字 + 函数 + 重试上限」打成一个工具对象。"""
    return BaseTool(
        func=func,
        json_schema={'type': 'function', 'function': {'name': name}},
        name=name,
        max_retry=max_retry,
    )


def make_executor(*tools):
    return ToolExecutor(tools=list(tools), config=FakeConfig())


# 步骤：造状态 → 调方法 → 断言


def test_no_tool_call_returns_empty_list():
    """没有工具调用时返回空列表，主循环据此判断该收尾。"""
    ex = make_executor(make_tool('echo', lambda: 'x'))

    assert ex.execute(aimsg=fake_aimsg()) == []


def test_success_returns_one_tool_message():
    """正常调用：一条消息，role 固定 tool，tool_call_id 必须和调用对齐。"""
    ex = make_executor(make_tool('echo', lambda word: f'echo:{word}'))

    messages = ex.execute(aimsg=fake_aimsg(('c1', 'echo', '{"word": "hi"}')))

    assert len(messages) == 1
    assert messages[0]['role'] == 'tool'
    assert messages[0]['tool_call_id'] == 'c1'
    assert messages[0]['content'] == 'echo:hi'


def test_bad_json_arguments_are_reported():
    """模型把 arguments 写成非 json 时，回一条错误消息而不是让程序崩。"""
    ex = make_executor(make_tool('echo', lambda **kw: 'x'))

    messages = ex.execute(aimsg=fake_aimsg(('c1', 'echo', 'error_tool_arg')))

    assert len(messages) == 1
    assert messages[0]['tool_call_id'] == 'c1'
    assert 'arguments的json解析失败' in messages[0]['content']
    assert ex.error_retry['echo'] == 1


def test_unknown_tool_name_is_reported():
    """模型编了个不存在的工具名：也要回一条，让它有机会自己改。"""
    ex = make_executor(make_tool('echo', lambda: 'x'))

    messages = ex.execute(aimsg=fake_aimsg(('c1', 'nope', '{}')))

    assert len(messages) == 1
    assert messages[0]['tool_call_id'] == 'c1'
    assert '工具名不存在' in messages[0]['content']


def test_empty_arguments_means_call_without_args():
    """无参数的工具（如 get_filepath）传的是空串，不能被当成解析失败。

    这里同时验证 root 是从 config 注入的，模型不用（也不该）自己填。
    """
    ex = make_executor(make_tool('noargs', lambda root: f'root={root}'))

    messages = ex.execute(aimsg=fake_aimsg(('c1', 'noargs', '')))

    assert len(messages) == 1
    assert messages[0]['content'] == 'root=E:/fake/root'


def test_config_overrides_model_supplied_argument():
    """模型自己塞了 root=C:/windows，也会被 config 里的真值覆盖掉——信任边界在这。"""
    ex = make_executor(make_tool('read_file', lambda root, path: f'{root}|{path}'))

    messages = ex.execute(
        aimsg=fake_aimsg(('c1', 'read_file', '{"root": "C:/windows", "path": "a.txt"}'))
    )

    assert messages[0]['content'] == 'E:/fake/root|a.txt'


def test_retry_limit_disables_tool():
    """重试用光后：先回一条上限提示，再把工具从 schema 里摘掉，模型就看不见它了。"""
    def boom():
        raise RuntimeError('炸了')

    ex = make_executor(make_tool('boom', boom, max_retry=1))

    first = ex.execute(aimsg=fake_aimsg(('c1', 'boom', '{}')))
    assert '工具调用失败' in first[0]['content']
    assert ex.error_retry['boom'] == 1

    second = ex.execute(aimsg=fake_aimsg(('c2', 'boom', '{}')))
    assert '重试次数达到上限' in second[0]['content']
    assert ex.disabled_tools == ['boom']
    assert ex.get_schema() == []


def test_type_error_is_reported_as_argument_error():
    """参数对不上（多了/少了）走 TypeError 分支，提示语和"执行炸了"要区分开。"""
    ex = make_executor(make_tool('strict', lambda only_this: 'x'))

    messages = ex.execute(aimsg=fake_aimsg(('c1', 'strict', '{"other": 1}')))

    assert '参数错误' in messages[0]['content']
    assert ex.error_retry['strict'] == 1


def test_every_tool_call_gets_a_reply():
    """一条 assistant 消息里三个 tool_call，就必须回三条——少一条下一轮请求直接 400。"""
    ex = make_executor(make_tool('a', lambda: 'ra'), make_tool('b', lambda: 'rb'))

    messages = ex.execute(aimsg=fake_aimsg(
        ('c1', 'a', '{}'),
        ('c2', 'b', '{}'),
        ('c3', 'nope', '{}'),
    ))

    assert [m['tool_call_id'] for m in messages] == ['c1', 'c2', 'c3']
    assert [m['role'] for m in messages] == ['tool', 'tool', 'tool']


def test_success_resets_error_retry():
    """失败一次之后再成功，计数要归零，否则偶发失败会攒到上限。"""
    attempts = {'n': 0}

    def flaky():
        attempts['n'] += 1
        if attempts['n'] == 1:
            raise RuntimeError('第一次失败')
        return '好了'

    ex = make_executor(make_tool('flaky', flaky, max_retry=2))

    ex.execute(aimsg=fake_aimsg(('c1', 'flaky', '{}')))
    assert ex.error_retry['flaky'] == 1

    ex.execute(aimsg=fake_aimsg(('c2', 'flaky', '{}')))
    assert ex.error_retry['flaky'] == 0


def test_get_config_injects_only_matching_params():
    """函数签名里没有的参数，一个都不许塞进去（否则 **tool_args 会直接 TypeError）。"""
    ex = make_executor()
    tool_call = fake_aimsg(('c1', 'whatever', '{}')).tool_calls[0]

    args = ex.get_config(func=lambda plain: None, tool_call=tool_call, tool_args={'keep': 1})
    assert args == {'keep': 1}

    args = ex.get_config(
        func=lambda root, tavily_api_key: None,
        tool_call=tool_call,
        tool_args={},
    )
    assert args == {'root': 'E:/fake/root', 'tavily_api_key': 'tvly-fake'}
