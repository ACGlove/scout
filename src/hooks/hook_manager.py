import logging
logger = logging.getLogger(__name__)
import importlib
import inspect
from .hook_contract import Hook

class HookManager:
    def __init__(self):
        self.hooks = {}


    def register(self):
        module = importlib.import_module('.hooks',__package__)    #Python 模块导入不需要 .py 后缀

        for name,obj in inspect.getmembers(module):  
            if isinstance(obj,Hook):
                self.hooks[obj.name] = obj.func

    def trigger(self,name,*args,**kwargs):
        try:
            result = self.hooks[name](*args,**kwargs)
            return result
        except KeyError:
            logger.error('钩子%s未注册',name)