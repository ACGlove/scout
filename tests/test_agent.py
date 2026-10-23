from types import SimpleNamespace

from src.memory.memory import Memory
from src.agent.agent import Agent

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
    memory = Memory()
    agent = Agent(
        model=('fake-model',FakeModel()),
        memory=memory,
        executor=FakeExecutor(),
        system='你是助手',
    )
    assert agent.model_name == 'fake-model'
    assert memory.messages == [{'role': 'system', 'content': '你是助手'}]


def test_no_tool_call_returns_content(monkeypatch):     #测试名详细
    monkeypatch.setattr('builtins.input', lambda prompt='': 'y')    #测试里终端没输入，程序挂掉,替换input，输入y使循环结束
    memory = Memory()
    executor = FakeExecutor()
    agent = Agent(
        model=('fake-model',FakeModel()),
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
    memory = Memory()
    executor = FakeExecutor([{'role':'tool','tool_call_id':'c1','content':'工具结果'}])
    agent = Agent(
        model=('fake-model',FakeModel()),
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
    memory = Memory()
    executor = FakeExecutor()
    agent = Agent(
        model=('fake-model',FakeModel()),
        memory=memory,
        executor=executor,
        system='你是助手',
    )

    agent('hhhhhh')

    assert executor.calls == 2        #两圈：第一圈被 feedback 打回
    assert len(memory.messages) == 5  #[system,user,assistant,user(反馈),assistant]
    assert memory.messages[3]['content'] == '说得再具体点'


