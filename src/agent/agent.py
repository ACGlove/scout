import logging
logger = logging.getLogger(__name__)
from .protocol import MemoryProtocol,ToolExecutorProtocol

class Agent:
    def __init__(self,model,memory:MemoryProtocol,executor:ToolExecutorProtocol,system=''):
        self.memory = memory
        self.executor = executor
        self.model_name,self.model = model
        self.system = system
        if system:
            self.memory.add_system_msg(system)


    def __call__(self,query):
        self.memory.add_user_msg(user_input=query)
        while True:
            logger.info('正在发送请求')
            res = self.model.create(
                model = self.model_name,
                messages = self.memory.messages,
                tools = self.executor.get_schema()
            )
            logger.info('请求成功')
            aimsg = res.choices[0].message
            self.memory.add_ai_msg(aimsg)
            tool_messages = self.executor.execute(aimsg = aimsg)
            self.memory.messages+=tool_messages
            logger.info('工具调用完成')
            if tool_messages:   #工具消息
                continue
            else:
                print(aimsg.content)
                feedback = input('是否对结果满意,满意直接提出建议，否则输入y结束对话')
                if feedback != 'y':
                    self.memory.add_user_msg(feedback)
                    continue
                return aimsg.content



#报错码422，传入字段不合法








#有行为无状态的做成函数
#有行为有共享状态的做成类
#只有状态的可以用dataclass
