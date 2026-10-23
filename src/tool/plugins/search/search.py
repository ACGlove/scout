import logging
logger = logging.getLogger(__name__)

from pydantic import BaseModel,Field

import json
from tavily import TavilyClient
from ...basetool_get import tool



class Search_Schema(BaseModel):
    '''联网搜索的工具'''
    query:str = Field(description='搜索的关键词,越详细越好')


@tool(args_schema=Search_Schema,max_retry=2)
def search(query:str,tavily_api_key):
    '''用于联网搜索的工具，当问题涉及时间或者编程时调用'''
    tavily=TavilyClient(api_key=tavily_api_key)
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
    res = '\n'
    for i in response:
        res += f'标题:{i['title']},链接:{i['url']},内容:{i['content']}'
    return json.dumps({
        'ok':True,
        'error':None,
        'content':res
    })


