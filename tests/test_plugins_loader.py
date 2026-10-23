from src.tool.plugins_loader import PluginsLoader
from src.tool.contract import BaseTool


def test_plugins_loader():
    loader=PluginsLoader()
    tools=loader.load_plugins()

    assert tools #断言非空
    assert {'read_file','edit_file','get_filepath','run_command'} <= {tool.name for tool in tools}   #<=在集合里用相当于包含关系
    assert all(isinstance(tool,BaseTool) for tool in tools)  #判断全是BaseTool


    

