import inspect
import logging

from src.tool.contract import BaseTool
logger=logging.getLogger(__name__)


import importlib
from pathlib import Path


class PluginsLoader:
    def __init__(self):
        self.tools=[]

    def load_plugins(self) -> list[BaseTool]:
        # p=Path(__file__).parent / 'plugin'   #获取目录路径 src\tool\plugin
        p=Path(__file__).parent / 'plugins'
        file_plugin=list(p.glob('*.py'))       #获取单文件插件
        dir_plugin=[d for d in p.iterdir() if d.is_dir() and (d/'__init__.py').exists()]  #获取带init的插件


        for file_path in sorted(file_plugin+dir_plugin):
            if file_path.name.startswith('_'):
                continue
            module_name=file_path.stem   #获取模块名
            logger.warning('正在加载%s',module_name)
            try:                                      #__package__返回当前文件所在包名
                module=importlib.import_module(f'.plugins.{module_name}',package=__package__)   #当前文件位于的包为tool,刚好作为锚点
                if not module:
                    logger.error('插件%s加载失败',module_name)
            except Exception as e:
                logger.error('加载失败:%s',e)
                continue        #跳过这一个工具的加载

            for name,obj in inspect.getmembers(module):  #抓取实例BaseTool,文件夹工具需要在__init__.py里显示定义工具并导入BaseTool
                if isinstance(obj,BaseTool):
                     self.tools.append(obj)
        if not self.tools:
            logger.error('无插件加载')
            raise RuntimeError('没有工具加载成功,检查依赖和plugins/目录')     #工具加载失败直接抛出错误，静默处理难排查
        logger.info('加载完成:工具目录：%s',[tool.name for tool in self.tools])
        return self.tools





















