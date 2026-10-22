from ..config import get_env
# from typing import TypedDict    TypeDict只声明不赋值
from dataclasses import dataclass


#在工具执行时传入必要的参数如root,apikey
@dataclass(frozen=True)  #只读不改
class ConfigContext:      
    root:str = get_env('ROOT')
    tavily_apikey:str = get_env('tavily_apikey')

    


        










