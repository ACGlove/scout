import pytest
from unittest.mock import patch
import requests
from src.tool.plugins.search import search



class FakeTavily:
    def __init__(self,api_key):
        self.api_key=api_key

    def search(query,max_result,search_depth):
        return {
            'result':[{
                'title':'标题',
                'url':'网址',
                'content':'内容'
            },{
                'title':'标题',
                'url':'网址',
                'content':'内容'
            }]
        }




#patch里填导入路径(模块路径.类名.方法名 | 模块路径.变量名)
def test_serach_timeout():
    #拦截底层api调用，一旦调用抛出特定错误
    with patch('src.tool.plugins.search.search.func') as mock_search:
        mock_search.side_effect = TimeoutError('connection timeout')

        result=search.func.search('')
















