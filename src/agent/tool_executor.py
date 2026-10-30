import logging
logger = logging.getLogger(__name__)
import json
import inspect
from concurrent.futures import ThreadPoolExecutor      #导入线程池,让多个工具并发调用,最后将结果统一打包返回给大模型
from dataclasses import fields
from ..tool.contract import BaseTool
from .protocol import HookManagerProtocol

class ToolExecutor:
    def __init__(self,tools:list[BaseTool],config,hooks:HookManagerProtocol):
        self.pool = ThreadPoolExecutor(max_workers = 5)              #支持5个工具并发调用
        self.config=config
        self.hooks = hooks
        self.tools=tools
        self.func_retry={
            tool.name:tool.max_retry for tool in self.tools  #记录工具名映射最大重试次数
                }
        self.error_retry={
            tool.name:0 for tool in self.tools
        }
        self.disabled_tools=[]

    def is_tool_accept_call(self,tool_call,tool_messages:list[dict]) -> bool:
        tool_name = tool_call.function.name
        if self.error_retry[tool_name] >= self.func_retry[tool_name]:
            resp = self.hooks.trigger('retry_limit',tool_call)
            tool_messages.append(resp)
            self.disabled_tools.append(tool_name)
            return False
        return True

    def get_tool_args(self,tool_call,tool_messages:list[dict]) -> dict|None:
        raw = tool_call.function.arguments or '{}'   #无参数的调用传空串或None,补成空字典
        try:
            tool_arg = json.loads(raw)  #dict
            return tool_arg
        except Exception as e:
            self.error_retry[tool_call.function.name] += 1
            resp = self.hooks.trigger('retry_error',e,tool_call)
            tool_messages.append(resp)
            return None          #用None当失败哨兵,因为{}是合法的无参数调用

    def get_config(self,func,tool_call,tool_args) -> dict:
        sig = inspect.signature(func)
        config_items = [(field.name,getattr(self.config, field.name)) for field in fields(self.config)]  #[()]  里面是元组
              #可接收ConfigContext对象
        for name, value in config_items:
            if name in sig.parameters:
                tool_args[name] = value
                logger.info('工具%s注入参数%s',tool_call.function.name,name)
        return tool_args
 
    
    

#dict.values()返回视图[1,2],无法使用列表方法，字典的取值改变，视图跟着变
    def execute(self,aimsg) -> bool:
        tool_messages=[]
        name_func={
            tool.name:tool.func for tool in self.tools
        }
        
        if not aimsg.tool_calls:
            return []
        future_context = {}   #存线程对象和相关信息,便于定位
        for tool_call in aimsg.tool_calls:
            tool_id = tool_call.id
            tool_name = tool_call.function.name
            func = name_func.get(tool_name,None)
            
            if func is None:
                resp = self.hooks.trigger('tool_name_error',tool_id)
                tool_messages.append(resp)
                continue
                
            if not self.is_tool_accept_call(tool_call,tool_messages):
                continue
            tool_args=self.get_tool_args(tool_call,tool_messages)
            if tool_args is None:
                continue            
            tool_args=self.get_config(func,tool_call,tool_args)       #注入工具敏感参数,例如root,apikey
                      
            
            future = self.pool.submit(
                func,
                **tool_args
            )                             #提交任务
            future_context[future] = tool_call   #记录此线程相关信息

        #收卷,拿到处理结果
        logger.warning('线程池的任务:%s',[i.function.name for i in future_context.values()])
        for future,tool_call in future_context.items():         #每次循环返回(键,值)这个元组
            tool_name = future_context[future].function.name
            tool_call = future_context[future]
            #子线程报错在获取结果这一步报错
            try:
                result = future.result()    #任务的报错在这里触发
                tool_messages.append({'role':'tool','tool_call_id':tool_call.id,'content':result})
                self.error_retry[tool_name] = 0        
            except Exception as e:
                resp = self.hooks.trigger('retry_error',e,tool_call)
                self.error_retry[tool_call.function.name] += 1
                tool_messages.append(resp)

        return tool_messages


    def get_schema(self) -> list[dict]:
        disabled=set(self.disabled_tools)
        return [tool.json_schema for tool in self.tools if tool.name not in disabled]




#多工具并发调用:1.提交所有任务创建独立线程执行,将结果收集到列表
#2.将结果遍历提交给大模型
