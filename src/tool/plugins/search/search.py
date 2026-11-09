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
            }, ensure_ascii=False)
    
    #join传可迭代对象,下面传的是生成器,join的拼接逻辑是'\n'插入迭代对象的中间
    #split()会把\n \t 连续空格都当分隔符吃掉,再用单空格拼回去 -> 一条结果只占一行
    def _flat(text: str) -> str:
        return ' '.join(text.split())

    res = '\n'.join(f'标题:{i["title"]},链接:{i["url"]},内容:{_flat(i["content"])}' for i in response)
    logger.info('search工具调用成功,搜索结果为:%s',res.replace('\n', ' ⏎ ')) #搜索结果换行符太多,日志可读性差
    return json.dumps({
        'ok':True,
        'error':None,
        'content':res
    }, ensure_ascii=False) 


#没加ensure_ascii=False的话,中文会被转义成ASCII的形式,token量大大增加,这是json转义的写法
#ASCII编码是英文字符的编码,中文字符在ASCII中没有对应的编码,所以会被转义成\uXXXX的形式,这样会增加token量,不利于模型理解
#中文无法用 ASCII 表示，所以 json.dumps 把它换成 Unicode 码点的十六进制文本；这串文本恰好全是 ASCII 字符，因此能安全传输，再由 json.loads 查表还原。ASCII 负责搬运编号，Unicode 表负责解释编号——两者缺一不可