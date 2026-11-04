from openai import OpenAI

from .config import get_env,get_env_int

class OpenAIClient:
    def __init__(self):
        self.client = OpenAI(
            base_url=get_env('BASE_URL'),
            api_key=get_env('API_KEY'),
            timeout=get_env_int('LLM_TIMEOUT'),
            max_retries=get_env_int('LLM_MAX_RETRIES')
        )
        self.model_name = get_env('MODEL')

    async def chat(self, messages:list[dict], tools:list[dict] = []) -> dict:
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            tools=tools
        ).choices[0].message



        













