"""Agent 主循环 + Memory 压缩/修补的测试。

Memory 重构后构造函数变成了 Memory(max_token, model)，model 是 (名字, 真模型) 元组。
FakeModel 同时扮两个角色：Agent 的对话模型、Memory 压缩时要做摘要的模型。
压缩的触发点在 add_user_msg -> split_memory，所以测试里都用 add_user_msg 来触发。
"""

from types import SimpleNamespace

import pytest

from src.memory.memory import Memory
from src.agent.agent import Agent

MODEL_NAME = 'fake-model'
NO_COMPRESS = 10_000_000   # 测试主循环时把上限设得很大，保证不会误触发压缩

# 判断类用真的还是假的
# 这个零件会不会碰外部世界？（网络、键盘、真实文件、真实时间）
# 我想断言的东西，是不是就在这个零件里？
# Agent 碰的东西：网络（model.create）、键盘（input）、外部世界（executor 真去跑工具）
#   -> 三个全换成假货，只留 Agent 自己的循环逻辑是真的


class FakeMsg:
    def __init__(self,content,tool_calls):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self):
        return {'role':'assistant','content':self.content,'tool_calls':self.tool_calls}


class FakeExecutor:
    """假执行器：按顺序吐出预设的 tool 消息，用完了就一直返回空列表。

    契约：execute(aimsg) -> list[dict]，空列表表示"这轮没有工具调用"。
    """
    def __init__(self,*rounds):
        self.rounds = list(rounds)     # 每一轮要返回的消息列表
        self.calls = 0                 # 用来断言主循环到底转了几圈

    def get_schema(self):
        return []

    def execute(self, aimsg):
        self.calls += 1
        return self.rounds.pop(0) if self.rounds else []


#model.creat() -> msg -> msg.choices[0].message -> aimsg -> aimsg.content -> aimsg.tool_calls
class FakeModel:
    """假模型：记住调用参数，返回一个固定回复。"""
    def __init__(self, content='你好'):
        self.content = content
        self.calls = []    #不是真货的属性,但是可以测模型调用次数,每次调用的参数

    def create(self, **kwargs):
        self.calls.append(kwargs)
        # 真货里没工具调用时 tool_calls 返回 None
        return SimpleNamespace(choices=[SimpleNamespace(message=FakeMsg(content=self.content,tool_calls=None))])


def test_init_adds_system_msg():
    fake = FakeModel()
    memory = Memory(max_token=NO_COMPRESS, model=(MODEL_NAME, fake))
    agent = Agent(
        model=(MODEL_NAME, fake),
        memory=memory,
        executor=FakeExecutor(),
        system='你是助手',
    )
    assert agent.model_name == MODEL_NAME                                     # 模型名原样保存下来
    assert memory.messages == [{'role': 'system', 'content': '你是助手'}]      # 第一条就是 system 消息


def test_no_tool_call_returns_content(monkeypatch):     #测试名详细
    monkeypatch.setattr('builtins.input', lambda prompt='': 'y')    #测试里终端没输入，程序挂掉,替换input，输入y使循环结束
    fake = FakeModel()
    memory = Memory(max_token=NO_COMPRESS, model=(MODEL_NAME, fake))
    executor = FakeExecutor()
    agent = Agent(
        model=(MODEL_NAME, fake),
        memory = memory,
        executor = executor,
        system = '你是助手'
    )

    result=agent('hhhhhh')
    assert len(memory.messages) == 3   #验证循环只跑了一轮    [system,user,assistant]
    assert memory.messages[1]['content'] == 'hhhhhh'   #测试用户消息传进去
    assert memory.messages[-1]['content'] == '你好'
    assert result == '你好'      #验证 Agent 把模型回复原样返回给调用方
    assert memory.messages[-1]['role'] == 'assistant'   #确定最后一条消息是ai的返回消息
    assert executor.calls == 1


#测有工具会转第二圈
def test_agent_loop_work(monkeypatch):
    """执行器第一轮吐一条 tool 消息 -> 主循环必须再问一次模型 -> 第二轮没工具就收尾。"""
    monkeypatch.setattr('builtins.input', lambda prompt='': 'y')
    fake = FakeModel()
    memory = Memory(max_token=NO_COMPRESS, model=(MODEL_NAME, fake))
    executor = FakeExecutor([{'role':'tool','tool_call_id':'c1','content':'工具结果'}])
    agent = Agent(
        model=(MODEL_NAME, fake),
        memory=memory,
        executor=executor,
        system='你是助手',
    )

    agent('用一下工具')

    assert executor.calls == 2                    #转了两圈：有工具 -> 再问 -> 没工具
    assert len(memory.messages) == 5              #[system,user,assistant,tool,assistant]
    assert memory.messages[3]['role'] == 'tool'    #工具消息被 Agent 自己塞回 memory
    assert memory.messages[3]['content'] == '工具结果'
    assert memory.messages[-1]['role'] == 'assistant'


def test_feedback_not_y_keeps_looping(monkeypatch):
    """用户不满意（非 y）时：把反馈当成新的 user 消息追加，然后继续问模型。"""
    answers = ['说得再具体点', 'y']
    monkeypatch.setattr('builtins.input', lambda prompt='': answers.pop(0))    
    #劫持当场生效（名字被换掉），但替身的行为（answers.pop(0)）要等后面的代码喊到 input() 才执行。
    fake = FakeModel()
    memory = Memory(max_token=NO_COMPRESS, model=(MODEL_NAME, fake))
    executor = FakeExecutor()
    agent = Agent(
        model=(MODEL_NAME, fake),
        memory=memory,
        executor=executor,
        system='你是助手',
    )

    agent('hhhhhh')

    assert executor.calls == 2        #两圈：第一圈被 feedback 打回
    assert len(memory.messages) == 5  #[system,user,assistant,user(反馈),assistant]
    assert memory.messages[3]['content'] == '说得再具体点'


# ---------------------------------------------------------------- Memory 压缩


def test_split_memory_compresses_when_over_max_token():
    """记忆的 token 超过 max_token：把历史发给模型做摘要，列表压成 system + 摘要。"""
    fake = FakeModel(content='这是摘要')
    memory = Memory(max_token=20, model=(MODEL_NAME, fake))
    memory.add_system_msg('你是助手')
    # 直接往列表里塞一条很长的消息：add_user_msg 会先压缩再加消息，塞进去才能制造超限
    memory.messages.append({'role': 'user', 'content': '很长' * 100})

    assert memory.count_token() > memory.max_token        # 前置条件：确实超了上限

    memory.add_user_msg('第二轮')

    assert len(fake.calls) == 1                            # 超限时只发了一次压缩请求
    sent = fake.calls[0]['messages']
    assert sent[-1]['content'].startswith('将这些对话消息做成')  # 末尾那条就是压缩指令
    assert all(m['role'] != 'system' for m in sent)         # system 不参与压缩，不能发给摘要模型
    assert len(sent) == 2                                  # 只发了那条长消息 + 压缩指令

    assert len(memory.messages) == 2                       # 压完只剩 system + 这一轮新的 user
    assert memory.messages[0]['role'] == 'system'
    assert memory.messages[0]['content'].startswith('你是助手')   # 原 system 内容没被覆盖
    assert '这是摘要' in memory.messages[0]['content']            # 摘要拼到 system 后面
    assert memory.messages[1] == {'role': 'user', 'content': '第二轮'}  # 新 user 消息照常追加


def test_split_memory_keeps_history_under_max_token():
    """没超过 max_token：不压缩、不调摘要模型，历史原样保留。"""
    fake = FakeModel()
    memory = Memory(max_token=NO_COMPRESS, model=(MODEL_NAME, fake))
    memory.add_system_msg('你是助手')

    memory.add_user_msg('你好')

    assert fake.calls == []                                 # 没超限就不该调模型做摘要
    assert [m['role'] for m in memory.messages] == ['system', 'user']   # 历史一条都没少


# ------------------------------------------------------ check_messages 补 tool 消息

# 一次 assistant 里同时发起两个工具调用，两条 tool 消息按 id 回传
_TOOL_CALLS = [
    {'id': 'c1', 'type': 'function', 'function': {'name': 'get_weather', 'arguments': '{"city":"北京"}'}},
    {'id': 'c2', 'type': 'function', 'function': {'name': 'get_weather', 'arguments': '{"city":"上海"}'}},
]


def _conversation_with_tool_reply():
    """一段完整对话：assistant 调两个工具，两条 tool 消息都回来了。"""
    return [
        {'role': 'user', 'content': '查一下北京和上海的天气'},
        {'role': 'assistant', 'content': None, 'tool_calls': [dict(c) for c in _TOOL_CALLS]},
        {'role': 'tool', 'tool_call_id': 'c1', 'content': '北京晴'},
        {'role': 'tool', 'tool_call_id': 'c2', 'content': '上海雨'},
        {'role': 'assistant', 'content': '北京晴，上海雨'},
    ]


def test_check_messages_fills_lost_tool_msg_in_middle():
    """本轮调了三个工具，中间那个（c2）的回执被 executor 跳过，只有 c1、c3 传了回来。

    这是 tool_executor.py:91 的 `if not tool_result: continue` 造成的真实缺口：
    工具返回空值时不 append tool 消息，缺口就落在同一组的中间。
    "只查最后一轮"的语义下，缺口后面还没有新的 assistant，所以补位追加在末尾；
    协议只看 tool_call_id 对不对得上，不要求顺序和声明顺序一致。
    """
    memory = Memory(max_token=NO_COMPRESS, model=(MODEL_NAME, FakeModel()))
    memory.add_system_msg('你是助手')
    memory.add_user_msg('查三个城市的天气')
    tool_calls = list(_TOOL_CALLS) + [
        {'id': 'c3', 'type': 'function', 'function': {'name': 'get_weather', 'arguments': '{"city":"广州"}'}},
    ]
    memory.add_ai_msg(FakeMsg(content=None, tool_calls=[dict(c) for c in tool_calls]))  # 模型发起三个调用
    memory.add_tool_msg([
        {'role': 'tool', 'tool_call_id': 'c1', 'content': '北京晴'},
        {'role': 'tool', 'tool_call_id': 'c3', 'content': '广州阴'},   # 中间的 c2 被跳过
    ])

    assert [m['role'] for m in memory.messages] == [
        'system', 'user', 'assistant', 'tool', 'tool', 'tool'
    ]                                                        # 补回一条 tool，总数对上了
    assert [m['tool_call_id'] for m in memory.messages[3:]] == ['c1', 'c3', 'c2']  # 真实回执原样，c2 的占位追加在末尾
    assert memory.messages[-1]['content'] == '此工具未能成功调用,请重新调用'   # 补的是占位文案，提醒模型重新调用
    assert sum(1 for m in memory.messages if m.get('tool_call_id') == 'c1') == 1  # 已有回执的 c1 不会被重复补


def test_check_messages_heals_interrupted_tool_reply():
    """模拟断在 tool 消息回传：assistant 一次调两个工具，只回了 c1 就断了。

    executor 是收齐 tool 消息后一次性 add_tool_msg 的，所以残缺只可能出现在末尾；
    add_tool_msg 收尾会调 check_messages，应该把没回传的 c2 补成占位消息。
    """
    memory = Memory(max_token=NO_COMPRESS, model=(MODEL_NAME, FakeModel()))
    memory.add_system_msg('你是助手')
    memory.add_user_msg('查一下北京和上海的天气')
    memory.add_ai_msg(FakeMsg(content=None, tool_calls=[dict(c) for c in _TOOL_CALLS]))  # 模型一次发起两个调用
    memory.add_tool_msg([{'role': 'tool', 'tool_call_id': 'c1', 'content': '北京晴'}])   # 只回了一条就断了

    assert [(m['role'], m.get('tool_call_id')) for m in memory.messages] == [
        ('system', None),
        ('user', None),
        ('assistant', None),
        ('tool', 'c1'),   # 真实回执在前
        ('tool', 'c2'),   # 补的占位消息紧跟在真实回执后面，没有跑到 assistant 前面
    ]
    assert memory.messages[-1]['content'] == '此工具未能成功调用,请重新调用'   # 补的是占位文案，提醒模型重新调用
    assert sum(1 for m in memory.messages if m.get('tool_call_id') == 'c1') == 1  # c1 已经有真实回执，不能重复补


def test_check_messages_keeps_complete_round_untouched():
    """两个工具都正常回传：check_messages 不该插占位，历史必须一条不多一条不少。"""
    memory = Memory(max_token=NO_COMPRESS, model=(MODEL_NAME, FakeModel()))
    memory.add_system_msg('你是助手')
    memory.messages += _conversation_with_tool_reply()
    before = [dict(m) for m in memory.messages]   # 先拍个快照，等下确认内容没被改

    memory.add_tool_msg([])                       # 模型给出最终回答那轮，agent.py:27 照样会调一次 add_tool_msg([])

    assert [m['role'] for m in memory.messages] == [
        'system', 'user', 'assistant', 'tool', 'tool', 'assistant'
    ]                                             # 没超限、没缺失，就不该多出占位消息
    assert memory.messages == before              # 每条消息内容也和快照完全一致（没有重复的 tool 回执）
