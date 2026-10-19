
import logging
logger = logging.getLogger(__name__)

# from dataclasses import dataclass
from ..config import get_env

from ..deps import get_model

from ..memory.memory import Memory

from ..tool.registry import Registry
from ..tool.plugins_loader import Plugins_Loader
from .tool_executor import Tool_Executor



class Agent:
    def __init__(self,system=''):
        self.plugins_loader=Plugins_Loader()
        self.register=Registry()

        self.root = get_env('ROOT')
        self.model = get_model()
        self.memory = Memory()
        
        self.tools=self.plugins_loader.load_plugins()       #加载,拿到[BaseTool]
        
        try:
            self.register.register_tools(tools=self.tools)     #注册
        except Exception as e:
            logger.error('插件注册错误:%s',e)
        
        self.tool_schema=self.register.get_tool_schema()
        self.name_func=self.register.get_name_func()
        self.tool_retry=self.register.get_tool_retry()
        
        self.executor = Tool_Executor(root=self.root,func_retry=self.tool_retry)


        
        self.system = system
        if system:
            self.memory.add_system_msg(system)



    def __call__(self,query):
        self.memory.add_user_msg(user_input=query)
        while True:
            logger.info('正在发送请求')
            res = self.model.create(
                model=get_env('MODEL'),
                messages=self.memory.messages,
                tools=self.tool_schema
            )
            logger.info('请求成功')
            aimsg = res.choices[0].message
            self.memory.add_ai_msg(aimsg)
            is_tool_call = self.executor.execute(aimsg=aimsg,memory=self.memory,name_func=self.name_func)
            logger.info('工具调用完成,tool_call:%s',f'{is_tool_call}')
            
            if is_tool_call:
                continue
            else:
                print(aimsg.content)
                feedback=input('是否对结果满意,满意直接提出建议，否则输入y结束对话')
                if feedback!='y':
                    self.memory.add_user_msg(feedback)
                    continue
                        
                return aimsg.content



#报错码422，传入字段不合法





#按照生命周期拆分Agent
#插件加载和注册一次结束，相同生命周期
#memory和工具retry次数持续到对话结束



#有行为无状态的做成函数
#有行为有共享状态的做成类
#只有状态的可以用dataclass










