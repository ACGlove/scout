from typing import Protocol,Any
from ..tool.contract import BaseTool


class MemoryProtocol(Protocol):
    messages:list[dict[str,Any]]

    def add_system_msg(self,system='') -> None:...

    def add_user_msg(self,user_input:str) -> None:...

    def add_tool_msg(self,tool_id:str,tool_result='') -> None:...



class ToolExecutorProtocol(Protocol):

    def execute(self,aimsg,memory:MemoryProtocol) -> None:...

    def get_schema(self) -> list[dict]:...




class PluginsLoaderProtocol(Protocol):
    def load_plugins(self) -> list[BaseTool]:...
    





























