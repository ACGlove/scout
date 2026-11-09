from openai.types.chat import ChatCompletionMessage
from pydantic import BaseModel
from typing import Optional

#都是必填的,除非设置默认值
class ToolCall(BaseModel):
    id:str
    name:str
    argument:str

class OpenaiConverter:
    def convert(self,aimsg:ChatCompletionMessage):
        if not aimsg.tool_calls:
            return []
        my_tool_calls = []
        tool_calls = aimsg.tool_calls
        for tool_call in tool_calls:
            my_tool_calls.append(
                ToolCall(
                    id = tool_call.id,
                    name = tool_call.function.name,
                    argument = tool_call.function.arguments
                )
            )
        return my_tool_calls








