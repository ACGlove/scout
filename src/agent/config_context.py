from ..config import get_env
# from typing import TypedDict    TypeDict只声明不赋值
from dataclasses import dataclass, field
from tavily import TavilyClient

# 在工具执行时传入必要的参数，如 root、API key
@dataclass(frozen=True)
class ConfigContext:
    root: str | None = field(default_factory=lambda: get_env('ROOT'))   #包装成对象field(name=root,value=默认值)  默认值并不是真实值而是一个函数,通过函数生成value
    tavily_client = field(default_factory=lambda: TavilyClient(api_key=get_env('TAVILY_API_KEY')))

#用field的作用:延迟加载，只有实例化这个类时才会调用get_env读取环境变量,直接root:get_env在导入类的时候就会调用，环境变量就写死了
