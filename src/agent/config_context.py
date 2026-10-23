from ..config import get_env
# from typing import TypedDict    TypeDict只声明不赋值
from dataclasses import dataclass, field


# 在工具执行时传入必要的参数，如 root、API key
@dataclass(frozen=True)
class ConfigContext:
    root: str | None = field(default_factory=lambda: get_env('ROOT'))
    tavily_api_key: str | None = field(default_factory=lambda: get_env('TAVILY_API_KEY'))

    


        










