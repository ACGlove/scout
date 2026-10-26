import logging
logger = logging.getLogger(__name__)

class Memory:
    def __init__(self):
        self.messages = []

    def check_messages(self):  #用集合,每个tool_call都有对应的id，tool message会回传这个id
        new_messges=[]
        tool_call_ids=[]
        for message in self.messages:
            if message['role'] == 'assistant':
                if tool_call_ids:
                    for id in tool_call_ids:
                        new_messges.append({'role':'tool','tool_call_id':id,'content':'此工具调用中断,重新调用'})
                if message.get('tool_calls'):
                    for tool_call in message['tool_calls']:
                        tool_call_ids.append(tool_call['id'])
            new_messges.append(message)
            if message['role'] == 'tool':
                if message['tool_call_id'] in tool_call_ids:
                    tool_call_ids.remove( message['tool_call_id'])
        self.messages = new_messges
            
  

    def add_system_msg(self,system=''):
        self.messages.append({'role':'system','content':system})

    def add_user_msg(self,user_input:str):
        self.check_messages()
        self.messages.append({'role':'user','content':user_input})

    def add_tool_msg(self,tool_id,tool_result=''):
        
        self.messages.append({'role':'tool','tool_call_id':tool_id,'content':tool_result})
        

    def add_ai_msg(self,ai_reply):   #直接传aimessage.model_dump()
        logger.info('正在填入ai消息')
        self.messages.append(ai_reply.model_dump())
        logger.info('填入成功')






















