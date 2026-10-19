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
    'src.tool.plugins.write_file':    logging.INFO,     
    'src.tool.plugins.read_file':     logging.INFO,
    'src.tool.plugins.get_filepath':    logging.INFO
}
for name, lv in LEVELS.items():
    logging.getLogger(name).setLevel(lv)



from .agent.agent import Agent


def llm_call():
    ag = Agent(system='你是一个代码助手,需要完成我给你的代码任务')
    result = ag(query='帮我查看read_file文件里工具函数的逻辑对不对')
    print(result)



if __name__=='__main__':
    llm_call()


    
   