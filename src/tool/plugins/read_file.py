import logging
logger = logging.getLogger(__name__)
import json
from pathlib import Path
from ..basetool_get import tool
from pydantic import BaseModel,Field

class Read_Tool_Schema(BaseModel):
    path:str = Field(description='文件路径')
    offset:int = Field(description='开始读取的行数')
    encoding:str = Field(description='默认为utf-8',default='utf-8')





@tool(args_schema=Read_Tool_Schema,max_retry=2)
def read_file(path:str,offset,encoding:str='utf-8',root=''):   #传工作区路径
    '''读取指定路径的文件内容,用于审查，优化代码，当文件行数超过200行时会触发截断，需要重新调用工具读取剩余内容'''
    logger.info('正在调用read_file工具')
    p = Path(root) / path  
    if not p.exists():
        logger.warning('文件不存在,读取失败')
        return json.dumps({
            'ok':False,
            'content':None,
            'error':f'文件不存在：{p}'
        })
    logger.info('正在读取文件%s',path)
    collected = []
    with p.open('r',encoding=encoding,errors='replace') as f:
        
        for lineno, line in enumerate(f, start=1):
            if lineno < offset:
                continue
            collected.append(line)
            if len(collected)>200:
                logger.info('文件超过最大行数,分段读取')
                return json.dumps({
                    'ok':True,
                    'error':'超出最大行数，重新调用工具读取剩下内容',
                    'next_offset':lineno+1,
                    'content':''.join(collected),
                    'truncated':True
                })
    return json.dumps({
                    'ok':True,
                    'error':None,
                    'next_offset':None,
                    'content':''.join(collected)
                })              #漏填return值，tool消息里的content为None,导致422错误,不同服务商错误码可能不同，ds是422，openai是400

    

# TOOL_SCHEMA=tool_schema(func=read_file,model=Read_tool_schema)                

            


        
        
        

        













