import logging
logger = logging.getLogger(__name__)

from pathlib import Path
from pydantic import BaseModel,Field
from ..basetool_get import tool
import json

class Edit_tool_schema(BaseModel):
    path:str = Field(description='写入文件的路径')
    content:str = Field(description='写入的内容')



@tool(args_schema=Edit_tool_schema,max_retry=4)
def edit_file(path:str,content,root):
    '''写入文件的工具,当用户提出编码需求时调用，如果用户指定的工作区文件不存在,调用此工具创建文件'''
    logger.info('正在调用edit_file文件')
    p = Path(root)
    file_path = p / path
    file_path.parent.mkdir(parents=True,exist_ok=True)    #p.parent是p的父目录,如src\untils\a.py，p.parent返回src\untils,验证目标文件的父目录是否存在，自动创建
    logger.info('正在写入文件%s',file_path)
    file_path.write_text(content,encoding='utf-8')
    return json.dumps({
        'ok':True,
        'error':None
    })




# TOOL_SCHEMA=tool_schema(func=edit_file,model=Edit_tool_schema)

















