import logging
logger=logging.getLogger(__name__)


from ..tool.contract import BaseTool
from .protocol import PluginsLoaderProtocol

class ToolManager:
    def __init__(self,plugins_loader:PluginsLoaderProtocol):
        self.loader = plugins_loader
        self.tools=self.loader.load_plugins()

    def get_tools(self) -> list[BaseTool]:
        return self.tools

    def get_name_func(self):
        return {
            tool.name:tool.func for tool in self.tools
        }

    

    


    
        
        












