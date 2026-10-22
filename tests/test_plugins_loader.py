from src.tool.plugins_loader import Plugins_Loader
from src.tool.contract import BaseTool


def test_plugins_loader():
    loader=Plugins_Loader()
    tools=loader.load_plugins()

    assert tools #断言非空
    assert all(isinstance(tool,BaseTool) for tool in tools)  #判断全是BaseTool


    

