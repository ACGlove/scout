from typing import Protocol,Any
from .tool.contract import BaseTool
from openai.types.chat import ChatCompletionMessage

class MemoryProtocol(Protocol):
    messages:list[dict[str,Any]]
    max_token:int

    def add_user_msg(self,user_input:str) -> None:...

    def add_tool_msg(self,tool_id:str,tool_result='') -> None:...

    def get_messages(self,system:str) -> list[dict]:...


class ToolCall(Protocol):
    id:str
    name:str
    argument:str

class OpenaiConverter(Protocol):
    def convert(self,aimsg:ChatCompletionMessage) -> list[ToolCall]: ...

class ToolExecutorProtocol(Protocol):
    tools:list[BaseTool]
    def execute(self,tool_calls:list[ToolCall]) -> list[dict]:...
    def get_schema(self) -> list[dict]:...

class PluginsLoaderProtocol(Protocol):
    def load_plugins(self) -> list[BaseTool]:...

# protocol.py 里追加
class HookManagerProtocol(Protocol):
    def trigger(self, name: str, *args: Any, **kwargs: Any) -> Any: ...


class McpLoaderProtocol(Protocol):
    async def setup(self) -> None:...

    async def load_tools(self) -> list[BaseTool]:...

class LLMProvider(Protocol):
    model_name:str
    async def chat(self, messages:list[dict],tools:list[dict],on_delta:Any) -> Any:...

class AgentStateProtocol(Protocol):
    history:list
    def save_history(self,messages:list[dict]) -> Any:...
    def load_history(self) -> list[dict]:...
    













