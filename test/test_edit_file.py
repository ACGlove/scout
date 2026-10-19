import pytest
from src.tool.plugins.edit_file import edit_file
import json
from pathlib import Path

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

