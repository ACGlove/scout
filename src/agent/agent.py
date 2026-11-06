import logging
logger = logging.getLogger(__name__)
from .protocol import MemoryProtocol,ToolExecutorProtocol,LLMProvider
import asyncio
import copy
class Agent:
    def __init__(self,model:LLMProvider,memory:MemoryProtocol,executor:ToolExecutorProtocol,system = '',max_step = 25):
        self.max_step = max_step
        self.memory = memory
        self.executor = executor
        self.model = model
        self.system = '你最多只有25轮调用工具的次数,尽量用最少的步骤完成任务\n' + system
        

    async def __call__(self,query):
        self.memory.add_user_msg(user_input=query)
        for i in range(self.max_step):
            logger.info('正在发送请求')
            #to_thread 只负责"在别的线程里调用"，函数在这里被提前执行就等于没用:必须传函数本身+参数
            logger.warning('列表状态:%s',self.memory.get_messages(self.system))
            aimsg = await self.model.chat(               #函数,参数,必须传函数本身+参数,不能传协程对象,否则会报错
                messages = self.memory.get_messages(self.system),                  #动态拼接,防止角色定位丢失
                tools = self.executor.get_schema(),
                on_delta = True               #开启流式打印
            )   
            logger.info('请求成功')
            
            await self.memory.add_ai_msg(aimsg)
            tool_messages = await self.executor.execute(aimsg = aimsg)     #run里面传协程对象,必须加(),run会创建事件循环,结束后销毁,放在for循环里相当于反复创建和销毁,性能上有损失
            self.memory.add_tool_msg(tool_messages)
            if tool_messages:   #工具消息
                continue
            else:
                logger.info('一轮对话结束')
                feedback = await asyncio.to_thread(input, '对回答是否满意:\n')          #input也是同步阻塞事件,input(...) 写在外面会先执行,同样要走 to_thread
                if feedback != 'y':
                    
                    logger.info('用户反馈问题:%s',feedback)
                    self.memory.add_user_msg(feedback)
                    continue
                return aimsg.content
        logger.warning('达到最大步数,结束对话')



#报错码422，传入字段不合法








#有行为无状态的做成函数
#有行为有共享状态的做成类
#只有状态的可以用dataclass
