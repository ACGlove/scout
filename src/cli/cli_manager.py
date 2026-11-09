import logging
logger = logging.getLogger(__name__)
from prompt_toolkit import PromptSession
from ..protocol import AgentStateProtocol

class CliManager:
    def __init__(self,agent,agentstate:AgentStateProtocol):
        self.agent = agent
        self.agentstate = agentstate
        self.session = PromptSession()

    
    async def run_task(self):
        system = await self.session.prompt_async('请输入prompt--> ')
        self.agentstate.save_history(self.agent.memory.messages)   #记录初始system
        while True:
            try:
                user_input = await self.session.prompt_async('请输入指令--> ')
            except (KeyboardInterrupt,EOFError):
                break
            if user_input == 'exit':
                break
            if user_input == 'roleback':
                if len(self.agentstate.history) > 1:
                    self.agent.memory.messages = self.agentstate.load_history()
                    continue
                print('无法回溯')
                continue
            await self.agent(query = user_input,system = system)   #串行:这一轮跑完才回到下一次输入
            self.agentstate.save_history(self.agent.memory.messages)

#串行执行:不创建后台任务,所以不存在"输入循环结束了但任务还在跑"的收尾问题
#之前用 asyncio.TaskGroup 同时跑 user_input 和 task_call:任务正常返回不会结束 TaskGroup,
#task_call 会一直卡在 queue.get(),输入 exit 之后进程退不出去