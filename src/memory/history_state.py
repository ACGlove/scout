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
        return self.history[-1]