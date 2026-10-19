import logging
logger = logging.getLogger(__name__)

class Memory:
    def __init__(self):
        self.messages = []

    def add_system_msg(self,system=''):
        self.messages.append({'role':'system','content':system})

    def add_user_msg(self,user_input:str):
        self.messages.append({'role':'user','content':user_input})

    def add_tool_msg(self,tool_id,tool_result=''):
        
        self.messages.append({'role':'tool','tool_call_id':tool_id,'content':tool_result})
        

    def add_ai_msg(self,ai_reply):   #直接传aimessage.model_dump()
        logger.info('正在填入ai消息')
        self.messages.append(ai_reply.model_dump())
        logger.info('填入成功')






















