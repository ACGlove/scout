from dataclasses import dataclass

from typing import Callable


@dataclass
class BaseTool:
    func:Callable
    json_schema:dict
    name:str
    max_retry:int









