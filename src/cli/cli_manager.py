import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from ..protocol import AgentStateProtocol

class CliManager:
    def __init__(self,agent,agentstate:AgentStateProtocol):
        self.agent = agent
        self.agentstate = agentstate
        self.session = PromptSession()


    async def run_loop(self):
        with patch_stdout():
            system = await self.session.prompt_async('请输入prompt--> ')
            self.agentstate.save_history(self.agent.memory.messages)   #记录初始system
            while True:
                try:
                    user_input = await self.session.prompt_async('请输入指令--> ')
                    if user_input == 'exit':
                        break
                    if user_input == 'roleback':
                        if len(self.agentstate.history) > 1:
                            self.agent.memory.messages = self.agentstate.load_history()
                            continue
                        else:
                            print('无法回溯')
                            continue
                        
                    await self.agent(query = user_input,system = system)
                    self.agentstate.save_history(self.agent.memory.messages)
                except (KeyboardInterrupt,EOFError):
                    break