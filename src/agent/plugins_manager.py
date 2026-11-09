import logging
logger=logging.getLogger(__name__)


from ..tool.contract import BaseTool
from ..protocol import PluginsLoaderProtocol,McpLoaderProtocol





class ToolManager:
    def __init__(self,plugins_loader:PluginsLoaderProtocol,mcp_loader:McpLoaderProtocol):
        self.loader = plugins_loader
        self.mcp_loader = mcp_loader
        

    async def get_tools(self) -> list[BaseTool]:     #load_tools 是 async,这里必须 await,否则拿到的是协程对象
        tools = self.loader.load_plugins()
        mcp_tools = await self.mcp_loader.load_tools()
        wrap_tools = tools + mcp_tools
        return wrap_tools

    

    def get_name_func(self):
        return {
            tool.name:tool.func for tool in self.tools
        }

    

    


    
        
        












