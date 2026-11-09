import logging
logger = logging.getLogger(__name__)
from ..protocol import MemoryProtocol,ToolExecutorProtocol,LLMProvider,OpenaiConverter
class Agent:
    def __init__(self,model:LLMProvider,memory:MemoryProtocol,executor:ToolExecutorProtocol,converter:OpenaiConverter,max_step = 25):
        self.max_step = max_step
        self.memory = memory
        self.executor = executor
        self.model = model
        self.converter = converter
        self.memory.add_system_msg()
        

    async def __call__(self,query,system):
        self.memory.add_user_msg(user_input=query)
        for i in range(self.max_step):
            logger.info('正在发送请求')
            #to_thread 只负责"在别的线程里调用"，函数在这里被提前执行就等于没用:必须传函数本身+参数
            aimsg = await self.model.chat(                                          #函数,参数,必须传函数本身+参数,不能传协程对象,否则会报错
                messages = await self.memory.get_messages(system),                  #动态拼接,防止角色定位丢失
                tools = self.executor.get_schema(),
                on_delta = True               #开启流式打印
            )   
            logger.info('请求成功')
            
            self.memory.add_ai_msg(aimsg)
            tool_messages = await self.executor.execute(tool_calls = self.converter.convert(aimsg))     #run里面传协程对象,必须加(),run会创建事件循环,结束后销毁,放在for循环里相当于反复创建和销毁,性能上有损失
            self.memory.add_tool_msg(tool_messages)
            if tool_messages:   #工具消息
                continue
            else:
                break
     



#报错码422，传入字段不合法
#有行为无状态的做成函数
#有行为有共享状态的做成类
#只有状态的可以用dataclass
