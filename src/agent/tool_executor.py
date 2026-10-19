import logging
logger = logging.getLogger(__name__)
import json
import inspect

class Tool_Executor:
    def __init__(self,root,func_retry:dict):
        self.root = root
        self.func_retry=func_retry      #{func_name:maxretry}

        

    def execute(self,aimsg,memory,name_func:dict):
        if aimsg.tool_calls:
            logger.info('工具重试次数情况:%s',self.func_retry)
            for tool_call in aimsg.tool_calls:

                tool_id = tool_call.id

                tool_name = tool_call.function.name

                tool_arg = json.loads(tool_call.function.arguments)  #dict

                func = name_func[tool_name]

                sig = inspect.signature(func)
                if 'root' in sig.parameters:
                    tool_arg['root'] = self.root    #判断函数是否需要传root参数，动态注入

                if self.func_retry[func.__name__]==0:
                    logger.error('工具%s调用重试失败,重试失败',tool_name)
                    memory.add_tool_msg(tool_id=tool_id,tool_result='重试次数达到上限，不要再调用此工具，将错误如实告诉用户')
                    continue
                try:
                    tool_result = func(**tool_arg)
                except Exception as e:
                    logger.error('工具调用错误,回传重试信息')
                    self.func_retry[tool_name]-=1
                    memory.add_tool_msg(tool_id=tool_id,tool_result=f'工具调用失败:{e},请重新调用工具尝试')
                    continue

                logger.info('正在填入工具消息')

                memory.add_tool_msg(tool_id=tool_id,tool_result=tool_result)

                logger.info('填入完成')
            return True
        else:
            return False















