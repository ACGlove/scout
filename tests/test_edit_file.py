import pytest
from src.tool.plugins.edit_file import edit_file
import json
from pathlib import Path

#两种运行测试脚本的命令区别
#找包时看sys.path,按列表里的路径寻找包，依次去每个文件夹查看有没有包
#python -m pytest tests/ -v     cwd:scout/     当作包运行,自动把tests所在当前目录scout/加入sys.path,此时能定位到src
#python pytest tests tests/ -v   cwd:scout     sys.path里没有scout/，定位不到src







def test_edit_file(tmp_path):
    #tmp_path是pytest内置的临时目录，会自动删除
    test_file='hello.txt'
    test_content='hihhihihihicsdc'


    #调用函数
    result_json=edit_file.func(path=test_file,content=test_content,root=tmp_path)
    result=json.loads(result_json)

    assert result['ok'] is True
    assert result['error'] is None


    expected_file_path=tmp_path / test_file
    assert expected_file_path.exists()
    assert expected_file_path.read_text(encoding='utf-8') == test_content

    result=json.loads(edit_file.func(path='../a.txt',content='',root=tmp_path))
    assert result['ok'] is False                                                     #测越权路径能不能拦住
    assert result['error'] == 'path不在用户指定的工作区内，请重新调用工具生成你知道的路径'

    _result = json.loads(edit_file.func(path=tmp_path,content='',root=tmp_path))
    assert _result['ok'] is False
    assert 'path 指向的是目录' in _result['error']    #用固定字段判断输出,忽略动态变量