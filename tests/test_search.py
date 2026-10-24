from src.tool.plugins.search.search import search
import json
import tavily

class FakeTavily:
    def __init__(self,error:bool):
        self.error=error

    def search(self,query,max_results,search_depth): #之前忘了填self,调用函数时会把实例作为第一个参数传递进去
        if self.error:
            raise tavily.exceptions.TimeoutError('connection timeout')
        return {
            'results':[{
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
def test_search_timeout():
    #拦截底层api调用，一旦调用抛出特定错误
    
    func_search=search.func
    result=json.loads(func_search(query='ad',tavily_client=FakeTavily(error=True)))
    assert '超时错误' in result['error']

#标题:{i['title']},链接:{i['url']},内容:{i['content']}
def test_search_return():
    func_search=search.func
    result=json.loads(func_search(query='ad',tavily_client=FakeTavily(error=False)))
    assert result['ok'] is True
    assert result['content'] == '标题:标题,链接:网址,内容:内容\n标题:标题,链接:网址,内容:内容'















