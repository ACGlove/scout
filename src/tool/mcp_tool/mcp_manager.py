import logging
logger = logging.getLogger(__name__)
from mcp import ClientSession, StdioServerParameters, stdio_client
import sys
from pathlib import Path
from ..contract import BaseTool
from contextlib import AsyncExitStack


CMD = [sys.executable, str(Path(__file__).with_name("crawl_server.py"))]

class McpLoader:
    def __init__(self):
        self.stack = AsyncExitStack()   #管理session生命周期,将async with压入,由stack自主决定关闭session,错误时也会自动关闭session
        self.session = []

    
#协议规定握手前,session发出的请求会被无视
    async def setup(self,cmd:list[list] = [CMD]):       #异步生成器,管理mcp server的生命周期,如果直接return,函数一结束session就断开
        for cmd in cmd:
            params = StdioServerParameters(command=cmd[0], args=cmd[1:])
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


