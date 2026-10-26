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
        #单文件插件和包内模块一视同仁:只要文件里有 BaseTool 实例就算插件
        for file_path in sorted(p.rglob('*.py')):    #rglob返回以p为根的完整相对路径
            if file_path.name.startswith('_'):     #含 __init__.py,包内模块会被直接扫到,不需要靠 __init__ 转导
                continue
            #relative_to去掉绝对前缀,rglob返回E://.../module,去掉后返回search/search
            #with_suffix替换最后一个点和后面的部分,传入''就是去掉
            #Path.parts将名字拆成元组,(search,search),最后用.连接
            module_name='.'.join(file_path.relative_to(p).with_suffix('').parts)   #search/search.py -> search.search
            logger.debug('正在加载%s',module_name)
            try:                                      #__package__返回当前文件所在包名
                module=importlib.import_module(f'.plugins.{module_name}',package=__package__)   #当前文件位于的包为tool,刚好作为锚点
            except Exception as e:
                logger.error('加载失败:%s',e)
                continue        #跳过这一个工具的加载

            for name,obj in inspect.getmembers(module):  #抓取 BaseTool 实例
                if isinstance(obj,BaseTool):
                     self.tools.append(obj)
        if not self.tools:
            logger.error('无插件加载')
            raise RuntimeError('没有工具加载成功,检查依赖和plugins/目录')     #工具加载失败直接抛出错误，静默处理难排查
        logger.info('加载完成:工具目录：%s',[tool.name for tool in self.tools])
        return self.tools





















