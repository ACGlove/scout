import logging
logger=logging.getLogger(__name__)

from typing import Callable
from .contract import BaseTool




class Registry:
    def __init__(self):
        
        self.registry={}

    def register_tools(self,tools:list[BaseTool]):
        for tool in tools:
            self.registry[tool.func]={'json_schema':tool.json_schema,'max_retry':tool.max_retry}
        logger.info('注册完成,工具目录：%s',[tool.name for tool in tools])


    def get_name_func(self) -> dict[str,Callable]:    #Type[BaseTool]指的是类对象不是实例
        name_func={tool.__name__:tool for tool in self.registry}
        logger.info('工具字典:%s',name_func)
        return name_func


    def get_tool_schema(self) -> list[dict]:
        json_schema=[i['json_schema'] for i in self.registry.values()]
        logger.info('json_schema:%s',json_schema)
        return json_schema

    def get_tool_retry(self) -> dict[str,int]:
        tool_retry={}
        for tool,schema in zip(self.registry,self.registry.values()):
            tool_retry[tool.__name__]=schema['max_retry']
        return tool_retry



            
        






    


























