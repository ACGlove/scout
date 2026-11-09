
    






# def to_openai_tool(t) -> dict:
#     return {
#         "type": "function",
#         "function": {
#             "name": t.name,
#             "description": (t.description or "").strip(),
#             "parameters": t.inputSchema or {"type": "object", "properties": {}},
#         },
#     }
# openai_tools = [to_openai_tool(t) for t in (await session.list_tools()).tools]