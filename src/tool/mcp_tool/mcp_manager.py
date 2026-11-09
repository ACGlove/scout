import logging
logger = logging.getLogger(__name__)
from mcp import ClientSession, StdioServerParameters, stdio_client
import sys
from pathlib import Path
from ..contract import BaseTool
from contextlib import AsyncExitStack

#关于python垃圾回收
#在离开作用域时,会销毁没有引用的局部变量,但是session也就是子进程这个外部资源不会被关闭,只是代码上无法引用了
#为什么两种外部资源一个会自动关闭,一个不会自动关闭
# 因为文件对象是python内置类型,有__del__方法,当函数结束时,局部变量被销毁,会调用__del__方法销毁内存对象,__del__方法里会调用close()关闭文件
# 如果要关闭子进程需要发送关闭信号,但是垃圾回收是同步的,所以大多异步库不会在__del__里关闭子进程,而是提供一个close()方法
#python的垃圾回收机制是基于引用计数的,当一个对象的引用计数为0时,它会被立即销毁,但是异步资源的关闭通常需要等待异步操作完成


#stack持有强引用,所以文件对象不会在setup函数结束时被销毁,session也不会被销毁,直到stack被关闭,stack关闭时会调用async with的__aexit__方法,关闭文件和session
#因为stack的强引用,文件对象的引用计数不会归零

#为什么不用只用self延长session的生命周期,而要用stack管理session的生命周期
#如果在async with下直接用self保存session,当async with结束时,session调用了__aexit__方法,关闭管道,向子进程发送终止信号,虽然session对象还在,但是外部连接断开,例如子进程,管道
#所以外部资源的释放不是跟内存对象绑死的,而是由代码控制的,因为关闭异步连接和子进程是要等待对方确认的,需要时间,垃圾回收是同步的不会await你的等待,所以异步对象里__del__没有关闭释放资源的操作
#而是提供别的异步方法关闭,此时就要求你持久化这个对象,主动释放资源
# 除非像文件对象调用__del__顺手调用close关闭文件,此时内存对象就和外部资源的释放绑在一起

#总结:
#同步I/O:__del__里有close(),内存死,文件关
#异步I/O:__del__里是空的,内存死,子进程还在跑(由代码控制),主动保存内存对象,以释放外部资源



CMD = [sys.executable, str(Path(__file__).with_name("crawl_server.py"))]

class McpLoader:
    def __init__(self):
        self.stack = AsyncExitStack()   #管理session生命周期,将async with压入,由stack自主决定关闭session,错误时也会自动关闭session
        self.session = []

    
#协议规定握手前,session发出的请求会被无视
    async def setup(self,cmd:list[list] = [CMD]):       #异步生成器,管理mcp server的生命周期,如果直接return,函数一结束session就断开
        for cmd in cmd:
            params = StdioServerParameters(command=cmd[0], args=cmd[1:])
            # self.log_file = await self.stack.enter_async_context(open('src/record.log','w',encoding='utf-8', buffering=1))  #将stderr管道定向到日志文件
            read,write = await self.stack.enter_async_context(stdio_client(params))  #建立子进程拿到管道
            session = await self.stack.enter_async_context(ClientSession(read,write)) #建立会话
            init = await session.initialize()  #握手,确认版本,有无prompt,tool,resource等功能,决定client能发哪些请求,server 决定能不能反过来请求你：能不能让你调 LLM 做摘要、能不能弹窗问你
            if init.capabilities.tools is None:      # 对方压根没开 tools
                logger.error('此mcp服务端无工具能力')
                continue
            self.session.append(session)       #多个会话压入一个stack
              

    async def load_tools(self) -> list[BaseTool]:
        mcp_tools = []
        for session in self.session:
            tools = (await session.list_tools()).tools  #返回list[Tool]  有三个字段:tool.name,tool.description,tool.input_schema(json schema)
            #注意:mcp 2.x 的Tool是普通 pydantic 模型,属性名是下划线风格 input_schema,不是 JSON 里的驼峰 inputSchema
            for tool in tools:
                json_schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (tool.description or "").strip(),
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            }
                name = tool.name
                func = session.call_tool       #签名是 call_tool(name, arguments:dict),由 executor 传两个位置参数
                async def get_func(tool_name,kwargs:dict):
                    result = await func(tool_name,kwargs)
                    return "\n".join(b.text for b in result.content if b.type == "text")            
                mcp_tools.append(BaseTool(
                        name = name,
                        json_schema = json_schema,
                        func = get_func,
                        max_retry = 1
                    ))
        return mcp_tools


