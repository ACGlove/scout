from mcp import ClientSession, StdioServerParameters, stdio_client
import sys
from pathlib import Path
from ..contract import BaseTool
from contextlib import AsyncExitStack


CMD = [sys.executable, str(Path(__file__).with_name("crawl_server.py"))]

class McpLoader:
    def __init__(self):
        self.stack = AsyncExitStack()   #管理session生命周期,将async with压入,由stack自主决定关闭session,错误时也会自动关闭session
        self.session = None

    

    async def setup(self):       #异步生成器,管理mcp server的生命周期,如果直接return,函数一结束session就断开
        params = StdioServerParameters(command=CMD[0], args=CMD[1:])
        read,write = await self.stack.enter_async_context(stdio_client(params))
        self.session = await self.stack.enter_async_context(ClientSession(read,write))
        await self.session.initialize()  #这里函数结束了,但是session没有关,生命周期挂在了stack上,调用await self.stack.aclose()所有with才会退出
              

    async def load_tools(self) -> list[BaseTool]:
        mcp_tools = []
        tools = (await self.session.list_tools()).tools  #返回list[Tool]  有三个字段:tool.name,tool.description,tool.input_schema(json schema)
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
            func = self.session.call_tool       #签名是 call_tool(name, arguments:dict),由 executor 传两个位置参数

            mcp_tools.append(BaseTool(
                    name = name,
                    json_schema = json_schema,
                    func = func,
                    max_retry = 1
                ))
        return mcp_tools