import logging
logger = logging.getLogger(__name__)

from pathlib import Path
from pydantic import BaseModel,Field
from ..basetool_get import tool
import json

class Edit_tool_schema(BaseModel):
    path:str = Field(description='写入文件的路径')
    content:str = Field(description='写入的内容')

#resolve()     一旦遇到不存在的部分，后面的内容就照原样拼上,解析真实的路径落点，将..等写法转成cwd下的绝对路径，防止路径落到root外面

@tool(args_schema=Edit_tool_schema,max_retry=4)
def edit_file(path:str,content,root):
    '''写入文件的工具,当用户提出编码需求时调用，如果用户指定的工作区文件不存在,调用此工具创建文件'''
    logger.info('正在调用edit_file文件')
    p = Path(root).resolve()
    file_path = (p / path).resolve()
    if not file_path.is_relative_to(p):
        logger.warning('路径越界：%s',path)
        return json.dumps({
            'ok':False,
            'error':'path不在用户指定的工作区内，请重新调用工具生成你知道的路径'
        })
    if file_path.is_dir():    #使最终落点在文件而不是目录
            return json.dumps({
                'ok': False, 'content': None,
                'error': f'path 指向的是目录：{path}，请给出文件路径',
            })

    file_path.parent.mkdir(parents=True,exist_ok=True)    #p.parent是p的父目录,如src\untils\a.py，p.parent返回src\untils,验证目标文件的父目录是否存在，自动创建
    
    logger.info('正在写入文件%s',file_path)
    file_path.write_text(content,encoding='utf-8')
    return json.dumps({
        'ok':True,
        'error':None
    })




# TOOL_SCHEMA=tool_schema(func=edit_file,model=Edit_tool_schema)

















