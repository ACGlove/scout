from dotenv import load_dotenv
import os
load_dotenv()


def get_env(value):
    return os.getenv(value)



def get_env_int(value):      #获取数字env字段，正常getenv只能获取字符串
    return int(os.getenv(value))

















