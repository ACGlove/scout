from pydantic import BaseModel
from .contract import BaseTool
from typing import Type

#ai写的，用于自动生成json_schema
def _strip_titles(node):
    """删掉 pydantic 自动生成的 title（和字段名重复，只占 token）"""
    if isinstance(node, dict):
        return {k: _strip_titles(v) for k, v in node.items() if k != 'title'}
    if isinstance(node, list):
        return [_strip_titles(v) for v in node]
    return node


def _inline_refs(node, defs):
    """把 $ref 就地展开成定义，兼容不认 $defs 的厂商"""
    if isinstance(node, dict):
        if '$ref' in node:
            target = _inline_refs(defs[node['$ref'].rsplit('/', 1)[-1]], defs)
            target.update({k: v for k, v in node.items() if k != '$ref'})
            return target
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def to_tool_schema(args_schema: Type[BaseModel], *, name: str, description: str = '') -> dict:
    """pydantic 模型 -> OpenAI tools 数组里的一项，不依赖任何厂商 SDK"""
    schema = args_schema.model_json_schema()
    schema = _inline_refs(schema, schema.get('$defs', {}))
    schema.pop('$defs', None)
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': (description or '').strip(),
            'parameters': _strip_titles(schema),
        },
    }


def tool(args_schema: Type[BaseModel], max_retry: int):
    def get_obj(func):

        schema = to_tool_schema(args_schema, name=func.__name__, description=func.__doc__)

        return BaseTool(func=func, json_schema=schema, name=func.__name__, max_retry=max_retry)       #装饰函数返回BaseTool对象，被注册表扫描加载
    return get_obj



