import pytest
from src.tool.plugins.read_file import read_file
import json




def test_path_wrong(tmp_path):
    p = ['../fakepath','/fakepath']    #测试路径越权
    for path in p:
        result = json.loads(read_file.func(path = path,offset = 0,root = tmp_path,encoding = 'utf-8'))
        
        assert '路径越界' in result['error']


def test_path_exist_return(tmp_path):
    p = 'fakepath'       
    result = json.loads(read_file.func(path = p,offset = 0,root = tmp_path,encoding = 'utf-8'))
    assert '文件不存在' in result['error']



def test_offset_return(tmp_path):
    p = 'a.txt'
    path = tmp_path / p
    path.write_text('\n'.join([str(i) for i in range(400)]))         #自动创建文件
    result = json.loads(read_file.func(path = p,offset = 0,root = tmp_path,encoding = 'utf-8'))
    assert result['truncated']
    assert result['next_offset'] == 201


def test_no_offset_return(tmp_path):
    p = 'a.txt'
    path = tmp_path / p
    path.write_text('\n'.join([str(i) for i in range(100)]))         #自动创建文件
    result = json.loads(read_file.func(path = p,offset = 0,root = tmp_path,encoding = 'utf-8'))
    assert result['next_offset'] is None


#/和\在windows下行为相同,在linux上和mac上不同

#path里加/或\如/fakepath是绝对路径,所以用/fakepath会算作路径越权,抛弃root的绝对路径,拼接后直接采用/fakepath

#绝对路径的path最后都会从盘符开始找

#相对路径：直接写文件名，带子目录data/test.py, ../tests.py退回上级

#windows里的绝对路径不能用/来判断,因为可能以盘符开头

#windows中\path和/path代表在盘符下的绝对路径,resolve后会生成E:/path，这是根相对路径

#决定路径resolve结果的是运行代码的cwd，仅限于相对路径

#特殊情况:\path和/path,会直接无视cwd，生成盘符下的路径

#总结:只要传入的路径不以(/,\,C:/,\\)开头就不会越权
