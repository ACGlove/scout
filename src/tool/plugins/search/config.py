from ...config import get_env

TAVILY_API_KEY = get_env('TAVILY_API_KEY')
if not TAVILY_API_KEY:
    raise RuntimeError('缺少 TAVILY_API_KEY，请在 src/.env 中配置后重启')
