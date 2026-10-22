
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.agent.config_context import ConfigContext
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   #在查找目录里加入scout目录
#有这一行，python tests/test_tool_executor.py命令才会生效，python查找tests目录会优先在scoout目录下找

from src.agent.tool_executor import ToolExecutor
from src.tool.contract import BaseTool


#造个假的Memory，execute方法需要个memory类


class FakeMemory:   #execute只需用到add_tool_msg方法和messages属性
    def __init__(self):       
        self.messages = []

    def add_tool_msg(self, tool_id, tool_result=''):    #假货的参数名必须一模一样，否则报错
        self.messages.append({
            'tool_call_id': tool_id,
            'content': tool_result,
        })


#造个假的aimsg,需要有tool_calls属性，tool_calls还是个列表，存的单个tool_call有id,function,function.name,function.arguments属性

def fake_aimsg(*calls):     #SimpleNamespace 是「只有数据形状、没有类型和行为」的假货，适合代替对参数进行属性访问的数据，如果参数有指定的类就不能用

    return SimpleNamespace(tool_calls=[
        SimpleNamespace(
            id=tid,
            function=SimpleNamespace(name=name, arguments=args)
        )
        for tid,name,args in calls
    ])
 

#步骤：造状态 → 调方法 → 断言


def make_tool(name, func, max_retry=2):
    """把「名字 + 函数 + 重试上限」打成一个工具对象。"""
    return BaseTool(func=func, json_schema={}, name=name, max_retry=max_retry)

def make_executor(*tools):
    """造被测对象。root='.' 表示工作区是当前目录（测试里不真碰文件）。"""
    return ToolExecutor(root='.', tools=list(tools))

def test_calls_tool_and_writes_result():
    mem = FakeMemory()
    ex = make_executor(make_tool('echo', lambda **kw: f'echo:{kw}'))

    result_true = ex.execute(
        aimsg=fake_aimsg(('c1', 'echo','error_tool_arg')),         #传错误工具调用参数,json.load解析失败
        memory=mem,
        config=ConfigContext().get_config()
    )
    assert len(mem.messages) == 1

    assert result_true is True

    assert 'arguments的json解析失败' in mem.messages[-1]['content']

    # result_tool_error = ex.execute(
    #     aimsg=fake_aimsg(('c1', 'echo',{'x':'er'})),         
    #     memory=mem
    # )
    # assert '工具调用失败' in result_tool_error[-1]['content']

    


