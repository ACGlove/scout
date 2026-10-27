import logging
logger = logging.getLogger(__name__)
import tiktoken
import json
class Memory:
    def __init__(self,max_token,model):
        self.messages = []
        self.max_token = max_token
        self.model_name,self.model = model
        

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
        self.messages.append({'role':'user','content':user_input})

    def add_tool_msg(self,tool_messages):
        self.messages += tool_messages
        

    def add_ai_msg(self,ai_reply):   #直接传aimessage.model_dump()
        logger.info('正在填入ai消息')
        self.messages.append(ai_reply.model_dump())
        logger.info('填入成功')

    def count_token(self):
        enc = tiktoken.get_encoding('o200k_base')   #分词器:将字符串切分成模型认识的最小单位:token
        total_token = 0
        token_pre = 4     #每条消息里都会隐式添加一些特殊符号
        for msg in self.messages:
            total_token += token_pre  #每条消息的固定开销
            total_token += len(enc.encode(msg.get('role','')))  #计算role的token
            total_token += len(enc.encode(str(msg.get('content',''))))
            if 'tool_calls' in msg:
                total_token += len(enc.encode(json.dumps(msg['tool_calls'],ensure_ascii=False)))    
            if 'tool_call_id' in msg:
                total_token += len(enc.encode(str(msg['tool_call_id'])))
        total_token += 2 #对话结尾的固定开销
        logger.info('此轮对话消耗token：%s',total_token)
        return total_token

    def split_memory(self):
        self.check_messages()
        token = self.count_token()
        self.add_user_msg('将这些对话消息做成600字以内的摘要,用户偏好如喜欢,感兴趣的信息尽量完整记录')
        #由于之前我将压缩记忆的方法内嵌在add_user_msg方法中,当token一直大于max_token时两个方法相互调用,会无限递归
        if token > self.max_token:
            logger.warning('正在压缩记忆列表')  
            split_messages_index = 0
            for index,message in enumerate(reversed(self.messages),start=1):
                if message['role'] == 'system':
                    split_messages_index = (len(self.messages) - index) + 1
                    break
            logger.warning('正在发送记忆压缩请求')
            logger.warning('不要压缩的消息：%s',self.messages[:split_messages_index+1])
            res = self.model.create(
                model = self.model_name,
                messages = self.messages[split_messages_index:]    #不压缩system消息
            ).choices[0].message.content
            self.messages = self.messages[:split_messages_index+1]
            self.add_system_msg(res)
            logger.warning('压缩后的摘要：%s',res)
            logger.warning('压缩成功')
        else:
            logger.info('此轮无需压缩')


#RecursionError: maximum recursion depth exceeded
#我的压缩记忆方法和add_user_msg方法相互调用,造成栈溢出






#计算token
#ensure_ascii会将中文转义成unicode编码,如'你好'->'\u4f60\u597d'
#unicode编码会导致token量相比中文字符暴增
#正常发送请求,都是utf-8编码的真实中文

#为什么不把整条字典消息json.dumps直接计算token
#模型底层的tokenizer计算时不会把字典消息原样计算,而是转化成一串带有特殊控制符的文本流(大概长这样<|im_start|>user<|im_end|>你好<|im_end|>)
#直接用json字符串计算会因为很多括号,空格被算成额外的token
#键名如role，content是也不会被算成token,大模型通过底层占位符区分内容,角色









