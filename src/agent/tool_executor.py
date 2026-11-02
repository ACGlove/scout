import logging
logger = logging.getLogger(__name__)
import json
import inspect

import asyncio
from dataclasses import fields
from ..tool.contract import BaseTool
from .protocol import HookManagerProtocol
from mcp.types import CallToolResult
class ToolExecutor:
    def __init__(self,tools:list[BaseTool],config,hooks:HookManagerProtocol):
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
    async def execute(self,aimsg) -> list[dict]:
        tool_messages=[]
        name_func={
            tool.name:tool.func for tool in self.tools
        }
        
        
        if not aimsg.tool_calls:
            return []
        tasks = []                #存线程对象和相关信息,便于定位
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
            #把任务收集起来,to_thread会自己使用线程池,不用手动创建
            logger.warning('正在加入工具%s',tool_name)
            tasks.append((asyncio.to_thread(func,**tool_args),tool_call,tool_name) if not inspect.iscoroutinefunction(func) else (func(tool_name,tool_args),tool_call,tool_name))
            #异步分支(mcp工具):call_tool 的签名是 (name, arguments:dict),必须传两个位置参数
            #不能写 func(tool_name, **tool_args),那会把 url=... 当成 call_tool 自己的关键字参数 -> TypeError  
            
        #解包协程对象列表传入,result里是协程任务的顺序
        result = await asyncio.gather(*[task[0] for task in tasks],return_exceptions = True)   #并发收集执行结果,把结果打包成列表
        logger.warning('线程池中的任务:%s',[task[2] for task in tasks])
        
        for (_,tool_call,_),res in zip(tasks,result):
            if isinstance(res,Exception):
                resp = self.hooks.trigger('retry_error',res,tool_call)
                self.error_retry[tool_call.function.name] += 1
                tool_messages.append(resp)
            else:
                tool_messages.append({'role':'tool','tool_call_id':tool_call.id,'content':res})
        return tool_messages


    def get_schema(self) -> list[dict]:
        disabled=set(self.disabled_tools)
        return [tool.json_schema for tool in self.tools if tool.name not in disabled]




#如果用线程池的submit和result执行拿到任务会有以下问题:
#通过for循环拿结果的时候是按顺序拿的,如果第一个卡了10秒就得等10秒才能拿到后面的结果
#如果用await协程,就会优先拿到先返回的结果,最后总耗时还是10秒,但是短耗时操作已经先处理了
#协程的gather是监听器,谁返回结果了就拿谁的结果



