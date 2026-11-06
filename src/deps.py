import logging
logger = logging.getLogger(__name__)
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage  #aimsg的类型,后面要用它的model_dump()方法
from .config import get_env,get_env_int
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function


async def assemble(stream,on_delta):
    content = []
    calls = {}   #收集tool_calls
    async for chunk in stream:
        if chunk.choices:                       #收尾空块要跳过,有些流式输出的最后会发一个空的choices=[]过来,此时choices[0]会报错
            delta = chunk.choices[0].delta
            if delta.content:
                content.append(delta.content)
            if on_delta and delta.content:     #流式打印的开关
                print(delta.content, end='', flush=True)
            for part in delta.tool_calls or {}:
                #index 表示“这个分片属于哪个工具调用”，而不是“第几个分片”。流式分片是交错到达的，并非“工具 A 全部发完，再发工具 B
                #setdefault相当于如果part.index的键存在,slot=calls[part.index],不存在就calls[part.index]={'id':'', 'name':'', 'arguments':''}
                slot = calls.setdefault(part.index, {'id':'', 'name':'', 'arguments':''})     #tool_call的三个属性
                if part.id:
                    slot['id'] = part.id    #只在第一片出现
                if part.function and part.function.name:
                    slot['name'] = part.function.name
                if part.function and part.function.arguments:
                    slot['arguments'] += part.function.arguments    
            tool_calls = [ChatCompletionMessageToolCall(
                        id=s['id'], type='function',
                        function=Function(name=s['name'], arguments=s['arguments']))
                    for _, s in sorted(calls.items())]    #calls.items->(index,slot),sorted按元组第零项排序
    return ChatCompletionMessage(
        role = 'assistant',
        content = ''.join(content) or None,   #None是json里的null,官方强制要求发起tool_calls时content字段必须是null,如果传''可能会报400错误
        tool_calls=tool_calls or None
    )

class OpenAIClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url=get_env('BASE_URL'),
            api_key=get_env('API_KEY'),
            timeout=get_env_int('LLM_TIMEOUT'),
            max_retries=get_env_int('LLM_MAX_RETRIES')
        )
        self.model_name = get_env('MODEL')

    async def chat(self, messages:list[dict], tools:list[dict] = [], on_delta = None) -> dict:
        stream = (await self.client.chat.completions.create(      #流式输出是分片返回的
            model=self.model_name,
            messages=messages,
            tools=tools,
            stream=True
        ))
        return await assemble(stream,on_delta)
           


#只按part.index 归集，不能按 function.name：模型可以同时调两次 read_file，名字一样，按名字合并会把 A 的参数接到 B 上，最后得到一个“语法正确但内容错”的 JSON，比报错更难查

#流式输出chunk.choices[0].delta的形状
# ChoiceDelta(audio=None, content='', function_call=None, refusal=None, role='assistant', tool_calls=None, reasoning_content='')                              
# ChoiceDelta(audio=None, content='', function_call=None, refusal=None, role=None, tool_calls=None, reasoning_content='用户')                                 
# ChoiceDelta(audio=None, content='', function_call=None, refusal=None, role=None, tool_calls=None, reasoning_content='问高斯的成就')                         
# ChoiceDelta(audio=None, content='', function_call=None, refusal=None, role=None, tool_calls=None, reasoning_content='有哪些。我有')                         
# ChoiceDelta(audio=None, content='', function_call=None, refusal=None, role=None, tool_calls=None, reasoning_content='25轮工具')                             
# ChoiceDelta(audio=None, content='', function_call=None, refusal=None, role=None, tool_calls=None, reasoning_content='调用限制，但其实')   

#第一段只提供空片
#reasoning_content是大模型的思考过程
#当大模型思考结束之后reasoning_content停止,content开始一段一段输出




#异步迭代器:async for
#因为chunk不是一次性存在stream里的,而是网络传输一个接一个生成的
#网络数据的chunk还没传过来就await,数据块到了就接着执行for循环下的代码
#