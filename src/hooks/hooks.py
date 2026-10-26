import logging
logger = logging.getLogger(__name__)

from .hook_contract import hook_register
import json


#钩子机制的价值是解耦低频的、可变的策略点
#钩子可以读状态（入参把当前状态传进去），但不应该直接改状态

@hook_register(name = 'retry_error')
def retry_error(e:Exception,tool_call):
    match e:
        case json.JSONDecodeError():
            logger.error('json格式参数错误解析，重新传回给大模型')
            return {'role':'tool','tool_call_id':tool_call.id,'content':f'arguments的json解析失败:{e},请更换参数传入或者换个策略'}
        case TypeError():
             logger.error('参数错误，重新传回给大模型')
             return {'role':'tool','tool_call_id':tool_call.id,'content':f'参数错误:{e},请更换参数传入或者换个策略'}
        case _:
            logger.error('工具调用错误,回传重试信息')
            return {'role':'tool','tool_call_id':tool_call.id,'content':f'工具调用失败:{e},请重新调用工具尝试'}


@hook_register(name = 'tool_name_error')
def tool_name_error(tool_id):
    logger.error('工具名不存在，重新传回给大模型')
    return {'role':'tool','tool_call_id':tool_id,'content':'工具名不存在，请重新生成正确的工具名'}


@hook_register(name = 'retry_limit')
def retry_limit(tool_call):
    logger.error('工具%s重试次数达到上限,不允许调用',tool_call.function.name)
    return {'role':'tool','tool_call_id':tool_call.id,'content':'重试次数达到上限，不要再调用此工具，将错误如实告诉用户'}




