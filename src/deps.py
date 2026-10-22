from openai import OpenAI

from .config import get_env,get_env_int

def get_model():
    client = OpenAI(
    base_url=get_env('BASE_URL'),
    api_key=get_env('API_KEY'),
    timeout=get_env_int('LLM_TIMEOUT'),
    max_retries=get_env_int('LLM_MAX_RETRIES')
        )
    name=get_env('MODEL')
    return name,client.chat.completions













