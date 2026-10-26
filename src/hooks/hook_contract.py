
class Hook:
    def __init__(self,func,name):
        self.func = func
        self.name = name






def hook_register(name):
    def wrapper(func):
        return Hook(func = func,name = name)
    return wrapper













