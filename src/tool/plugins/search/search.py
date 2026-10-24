import logging
logger = logging.getLogger(__name__)

from pydantic import BaseModel,Field

import json
from tavily.exceptions import TimeoutError
from ...basetool_get import tool



class Search_Schema(BaseModel):
    '''联网搜索的工具'''
    query:str = Field(description='搜索的关键词,越详细越好')


@tool(args_schema=Search_Schema,max_retry=2)
def search(query:str,tavily_client):
    '''用于联网搜索的工具，当问题涉及时间或者编程时调用'''
    tavily=tavily_client    #外部注入客户端,方便测试
    logger.info('正在调用search工具,搜索问题：%s',query)
    try:
        response = tavily.search(
                query,
                max_results=5,
                search_depth="advanced"
            )['results']
    except TimeoutError as f:
        logger.error('search超时错误')
        return json.dumps({
            'ok':False,
            'error':f'超时错误,错误信息为{f},请重新调用工具',
            'content':None
            })
    
    #join传可迭代对象,下面传的是生成器,join的拼接逻辑是'\n'插入迭代对象的中间
    res = '\n'.join(f'标题:{i['title']},链接:{i['url']},内容:{i['content']}' for i in response)
    return json.dumps({
        'ok':True,
        'error':None,
        'content':res
    })


