from typing import Protocol,Any
from ..tool.contract import BaseTool


class MemoryProtocol(Protocol):
    messages:list[dict[str,Any]]
    max_token:int

    def add_system_msg(self,system='') -> None:...

    def add_user_msg(self,user_input:str) -> None:...

    def add_tool_msg(self,tool_id:str,tool_result='') -> None:...



class ToolExecutorProtocol(Protocol):
    tools:list[BaseTool]
    

    def execute(self,aimsg) -> list[dict]:...

    def get_schema(self) -> list[dict]:...




class PluginsLoaderProtocol(Protocol):
    def load_plugins(self) -> list[BaseTool]:...
    


# protocol.py 里追加
class HookManagerProtocol(Protocol):
    def trigger(self, name: str, *args: Any, **kwargs: Any) -> Any: ...


























