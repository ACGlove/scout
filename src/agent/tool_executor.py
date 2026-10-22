import logging
logger = logging.getLogger(__name__)
import json
import inspect
from dataclasses import fields
from ..tool.contract import BaseTool
from .protocol import MemoryProtocol

class ToolExecutor:
    def __init__(self,root,tools:list[BaseTool],config):
        self.config=config
        self.root = root
        self.tools=tools
        self.func_retry={
            tool.name:tool.max_retry for tool in self.tools  #记录工具名映射最大重试次数
                }
        self.error_retry={
            tool.name:0 for tool in self.tools
        }
        self.disabled_tools=[]



    def is_tool_name_true(self,name_func:dict,memory:MemoryProtocol,tool_call) -> bool:
        tool_name = tool_call.function.name
        if tool_name not in name_func:
            logger.error('工具名不存在，重新传回给大模型')
            memory.add_tool_msg(tool_id=tool_call.id,tool_result=f'工具名不存在，重新传入正确的工具名')
            return False
        return True

    def is_tool_accept_call(self,memory,tool_call) -> bool:
        tool_name = tool_call.function.name
        if self.error_retry[tool_name]==self.func_retry[tool_name]:
            logger.error('工具%s重试次数达到上限,不允许调用',tool_name)
            memory.add_tool_msg(tool_id=tool_call.id,tool_result='重试次数达到上限，不要再调用此工具，将错误如实告诉用户')
            self.disabled_tools.append(tool_name)
            return False
        return True


    def get_tool_args(self,memory,tool_call) -> bool:
        try:
            tool_arg = json.loads(tool_call.function.arguments)  #dict
            return tool_arg
        except json.JSONDecodeError as e:
            self.error_retry[tool_call.function.name] += 1
            logger.error('json格式参数错误解析，重新传回给大模型')
            memory.add_tool_msg(tool_id=tool_call.id,tool_result=f'arguments的json解析失败:{e},请更换参数传入或者换个策略')
            return False

    def get_config(self,func,tool_call,tool_args):
        sig = inspect.signature(func)
        config_items = [(field.name,getattr(self.config, field.name)) for field in fields(self.config)]  #[()]  里面是元组
              #可接收ConfigContext对象
        for name, value in config_items:
            if name in sig.parameters:
                tool_args[name] = value
                logger.info('工具%s注入参数%s',tool_call.function.name,name)
        return tool_args

    

#dict.values()返回视图[1,2],无法使用列表方法，字典的取值改变，视图跟着变
    def execute(self,aimsg,memory:MemoryProtocol) -> bool:
        name_func={
            tool.name:tool.func for tool in self.tools
        }
        
        if aimsg.tool_calls:
            for tool_call in aimsg.tool_calls:
                tool_id = tool_call.id
                tool_name = tool_call.function.name
                func = name_func.get(tool_name)
                if func is None:
                    logger.error('工具名不存在，重新传回给大模型')
                    memory.add_tool_msg(tool_id=tool_id,tool_result='工具名不存在，请重新生成正确的工具名')
                    continue
                
                if not self.is_tool_name_true(name_func,memory,tool_call):
                    continue
                if not self.is_tool_accept_call(memory,tool_call):
                    continue
                tool_args=self.get_tool_args(memory,tool_call)
                if tool_args is False:
                    continue            
                tool_args=self.get_config(func,tool_call,tool_args)
                         
                try:
                    tool_result = func(**tool_args)
                except TypeError as e:
                    logger.error('参数错误，重新传回给大模型')
                    memory.add_tool_msg(tool_id=tool_id,tool_result=f'参数错误:{e},请更换参数传入或者换个策略')
                    self.error_retry[tool_name] += 1
                    continue
                except Exception as e:
                    logger.error('工具调用错误,回传重试信息')
                    self.error_retry[tool_name] += 1
                    memory.add_tool_msg(tool_id=tool_id,tool_result=f'工具调用失败:{e},请重新调用工具尝试')
                    continue
                self.error_retry[tool_name] = 0
                logger.info('正在填入工具消息')
                
                memory.add_tool_msg(tool_id=tool_id,tool_result=tool_result)

                logger.info('填入完成')
            return True
        else:
            return False


    def get_schema(self) -> list[dict]:
        disabled=set(self.disabled_tools)
        return [tool.json_schema for tool in self.tools if tool.name not in disabled]
