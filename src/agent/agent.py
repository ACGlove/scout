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
        self.system = system
        


    async def __call__(self,query):
        self.memory.add_system_msg('')  #存放摘要的地方
        self.memory.add_user_msg(user_input=query)
        for i in range(self.max_step):
            logger.info('正在发送请求')
            #to_thread 只负责"在别的线程里调用"，函数在这里被提前执行就等于没用:必须传函数本身+参数
            
            messages = copy.deepcopy(self.memory.messages)  #这里如果用copy()或者self.messages[:]，只是复制了外层列表,里面的字典对象还是同一个,后续修改会影响到原来的对象,所以要用deepcopy
            messages[0]['content'] = self.system  + messages[0]['content']  #动态拼接系统角色定位,防止丢失
            logger.warning('列表状态:%s',messages)
            res = await self.model.chat(               #函数,参数,必须传函数本身+参数,不能传协程对象,否则会报错
                messages = messages,                  #动态拼接,防止角色定位丢失
                tools = self.executor.get_schema()
            )   
            logger.info('请求成功')
            aimsg = res
            await self.memory.add_ai_msg(aimsg)
            tool_messages = await self.executor.execute(aimsg = aimsg)     #run里面传协程对象,必须加(),run会创建事件循环,结束后销毁,放在for循环里相当于反复创建和销毁,性能上有损失
            self.memory.add_tool_msg(tool_messages)
            logger.info('工具调用完成')
            if tool_messages:   #工具消息
                continue
            else:
                print(aimsg.content)
                logger.info('一轮对话结束')
                feedback = await asyncio.to_thread(input, '对回答是否满意:\n')          #input也是同步阻塞事件,input(...) 写在外面会先执行,同样要走 to_thread
                if feedback != 'y':
                    
                    logger.info('用户反馈问题:%s',feedback)
                    self.memory.add_user_msg(feedback)
                    continue
                return aimsg.content



#报错码422，传入字段不合法








#有行为无状态的做成函数
#有行为有共享状态的做成类
#只有状态的可以用dataclass
