import logging
logger = logging.getLogger(__name__)
from pydantic import BaseModel
from ..basetool_get import tool
from pathlib import Path

import json

class Get_Filepath(BaseModel):
    pass

@tool(args_schema=Get_Filepath,max_retry=3)
def get_filepath(root):
    '''获取工作区中所有文件的路径,工作区路径由代码注入,在有读写文件的需求或者需要知道工作区文件的相对路径时调用'''   #拿到的都是root的相对路径，所以读写工作区文件时要求传root
    logger.info('正在调用get_filepath工具')
    workspace = root
    directory = Path(workspace)
    files = [f.relative_to(workspace) for f in directory.rglob('*') if f.is_file()]
    logger.info(f'工作区文件路径:{files}')
    if not files:
        return json.dumps({
            'ok':True,
            'error':'此目录下无文件',
            'content':None
        })
    paths = '\n'.join([str(i) for i in files])
    return json.dumps({
        'ok':True,
        'error':None,
        'content':paths
    })

    

# TOOL_SCHEMA=tool_schema(model=Get_Filepath,func=get_filepath)








