import logging          #配置在业务import之前，不然导入文件时运行的代码没法记录日志
logging.basicConfig(
                    format='%(asctime)s %(levelname)s %(name)s: %(message)s',     #分别为时间，级别,名字，信息
                    filename='src/record.log',
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
    'src.tool.plugins.get_filepath':    logging.INFO,
    'src.tool.plugins.run_command':     logging.INFO
}
for name, lv in LEVELS.items():
    logging.getLogger(name).setLevel(lv)

import asyncio
from .tool.plugins_loader import PluginsLoader
from .agent.agent import Agent
from .agent.plugins_manager import ToolManager
from .agent.tool_executor import ToolExecutor
from .memory.memory import Memory
from .agent.config_context import ConfigContext
from .hooks.hook_manager import HookManager
from .tool.mcp_tool.mcp_manager import McpLoader
from .cli.cli_manager import CliManager
from .deps import OpenAIClient
from .memory.history_state import AgentState
from .agent.converter import OpenaiConverter

async def build_agent(mcp_loader):
    config_context=ConfigContext()
    converter = OpenaiConverter()
    LLM = OpenAIClient()
    memory=Memory(max_token = 60000,
                  model = LLM
    )
    plugins_loader=PluginsLoader()
    hooks = HookManager()
    hooks.register()

    tool_manager=ToolManager(plugins_loader = plugins_loader,
                             mcp_loader = mcp_loader)
    executor=ToolExecutor(tools = await tool_manager.get_tools(),   #get_tools 里要 await mcp 的 load_tools,所以它也是协程
                          config = config_context,
                          hooks = hooks
                          )
    agent=Agent(
        model = LLM,
        memory = memory,
        executor = executor,
        converter = converter
    )
    return agent


async def main():          #定义在模块层,测试才能 import 进来;写在 if __name__ 里面就永远测不到
    mcp_loader = McpLoader()
    
    try:                       #必须放在 try/finally 里:mcp 子进程没关掉时 asyncio.run 收尾会一直等,异常信息也不会打印出来
        await mcp_loader.setup()
        agentstate = AgentState()
        agent = await build_agent(mcp_loader)
        cli_manager = CliManager(agent,agentstate)
        await cli_manager.run_task()
    finally:
        await mcp_loader.stack.aclose()  #关闭mcp服务


if __name__=='__main__':
    asyncio.run(main())   #不管 main() 是正常结束还是抛异常，都先执行收尾——>退出前把所有后台任务停掉、等它们真正结束
    #收尾卡在了子进程没结束,因为没有用try,finally让stack.aclose()正常关闭管道,子进程
        
    
    
# task = asyncio.create_task(mcp_loader.setup())   #create_task创建了新的任务：启动mcp
#但是外部资源的打开和关闭必须在同一个任务下,所以报了以下错误,且setup和build_agent必须串行等待
#RuntimeError: Attempted to exit cancel scope in a different task than it was entered in
#await func()不算创建新任务,直接在当前协程执行
# gather和create_task一定会创建新任务    
   