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

from .deps import OpenAIClient


async def build_agent(mcp_loader):
    system = await asyncio.to_thread(input, '设定角色：')   #先问角色,有输出提示,不会让人以为"没反应"
    config_context=ConfigContext()
    LLM = OpenAIClient()
    memory=Memory(max_token = 640000,
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
        system = system,
        model = LLM,
        memory = memory,
        executor = executor
    )
    return agent


async def main():          #定义在模块层,测试才能 import 进来;写在 if __name__ 里面就永远测不到
    mcp_loader = McpLoader()
    await mcp_loader.setup()   #启动mcp服务
    try:                       #必须放在 try/finally 里:mcp 子进程没关掉时 asyncio.run 收尾会一直等,异常信息也不会打印出来
        agent = await build_agent(mcp_loader)
        result = await agent('查查哔站最近最火的番,写一份报告,要求有标题,有小结,有结论,尽量快点完成,不要重复调用搜索工具太多次')
        print(result)
    finally:
        await mcp_loader.stack.aclose()  #关闭mcp服务


if __name__=='__main__':
    asyncio.run(main())   #不管 main() 是正常结束还是抛异常，都先执行收尾——>退出前把所有后台任务停掉、等它们真正结束
    #收尾卡在了子进程没结束,因为没有用try,finally让stack.aclose()正常关闭管道,子进程
        
    
    

    
   