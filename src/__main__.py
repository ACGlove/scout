import logging          #配置在业务import之前，不然导入文件时运行的代码没法记录日志
logging.basicConfig(
                    format='%(asctime)s %(levelname)s %(name)s: %(message)s',     #分别为时间，级别,名字，信息
                    filename='src\\record.log',
                    encoding='utf-8',
                    filemode='w')  #覆盖式
logger = logging.getLogger(__name__)  #起名字，直接用文件名
# logging.getLogger('mutiagent.deps').setLevel(logging.DEBUG)   #给某个特定模块降级日志
LEVELS = {                                                
    'src.tool.plugins.search':        logging.DEBUG,        
    'src.agent.agent':     logging.DEBUG,
    'src.agent.tool_executor':      logging.INFO,         
    'src.tool.plugins.edit_file':    logging.INFO,     
    'src.tool.plugins.read_file':     logging.INFO,
    'src.tool.plugins.get_filepath':    logging.INFO
}
for name, lv in LEVELS.items():
    logging.getLogger(name).setLevel(lv)


from .tool.plugins_loader import PluginsLoader
from .agent.agent import Agent
from .agent.plugins_manager import ToolManager
from .agent.tool_executor import ToolExecutor
from .memory.memory import Memory
from .agent.config_context import ConfigContext


from .deps import get_model


def build_agent():
    config_context=ConfigContext()
    memory=Memory()
    plugins_loader=PluginsLoader()

    tool_manager=ToolManager(plugins_loader=plugins_loader)
    executor=ToolExecutor(tools=tool_manager.get_tools(),
                          config=config_context
                          )

    agent=Agent(
        system=input('设定角色：'),
        model=get_model(),
        memory=memory,
        executor=executor
    )
    return agent


if __name__=='__main__':
    agent=build_agent()
    result=agent('查看下memory目录下的memory文件,告诉我那段检查消息列表格式的逻辑对不对')
    
    

    
   