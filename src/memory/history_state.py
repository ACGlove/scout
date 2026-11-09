import logging
logger = logging.getLogger(__name__)
from copy import deepcopy

class AgentState:
    def __init__(self):
        self.history = []

    def save_history(self,messages:list[dict]):
        if messages:
            history = deepcopy(messages)
            self.history.append(history)
            logger.warning('记录历史:%s',[message['role'] for message in messages])

    def load_history(self):
        self.history.pop()
        logger.warning('返回的历史:%s',[message['role'] for message in self.history[-1]])
        return deepcopy(self.history[-1])             #这里如果不用deepcopy,多次回滚会出问题
    #[h1,h2,h3]   当回滚后删掉h3,拿到h2,此时因为不是deepcopy,h2与memory.messages共享数据,当一轮对话结束后,h2与messages一起改变,此时加入的h3与h2是相同的