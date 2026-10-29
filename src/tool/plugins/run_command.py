import logging
logger = logging.getLogger(__name__)
import subprocess
import psutil
import json
from pydantic import BaseModel,Field
from ..basetool_get import tool

class RunCommandSchema(BaseModel):
    command:str = Field(description = '要在终端执行的命令')


@tool(args_schema = RunCommandSchema,max_retry = 3)
def run_command(root:str,command:str):
    '''命令行工具,当你写完代码后需要调用此工具跑通代码验证是否会报错,或者自动化测试代码时调用'''
    logger.warning('正在执行run_command工具')
    allowed_command = [                          #命令白名单
        'python','python3','pip','pip3',
        'pytest','git','dir','ls','cat',
        'echo','type','find','grep'
    ]
    accept = False
    for cmd in allowed_command:
        if command.startswith(cmd):
            accept = True
            break
    if not accept:
        logger.warning('命令不在白名单内,执行终止')
        return json.dumps({
            'error': '命令权限不足,请换种策略执行任务'
        })
    logger.warning('正在执行命令:%s',command)
    process = subprocess.Popen(
        command,
        cwd = root,
        shell = True,
        stderr = subprocess.PIPE,    #标准错误接入管道,避免输出到终端,一般是print()的内容
        stdout = subprocess.PIPE,    #标准输出接入管道
        text = True,                 #输出是bytes,解码为字符串
        creationflags = subprocess.CREATE_NO_WINDOW       #windows平台专属:隐藏弹出的黑框
    )
    try:
        #运行到communicate会阻塞直到父进程死掉,把抽取的数据拼好返回
        stdout,stderr = process.communicate(timeout = 10)      #抽取管道中的输出,否则输出塞满管道阻止子进程的输出,导致进程卡死在子进程的print,如果超时抛出错误
        if len(stdout) > 2000:
            stdout = stdout[:1000] + '\n...输出过长已截断...\n' + stdout[-1000:]   #防止token爆炸
        if len(stderr) > 2000:
            stderr = stderr[:1000] + '\n...输出过长已截断...\n' + stderr[-1000:]  
        return json.dumps({
        'success': process.returncode == 0,   #成功退出码为0,否则不为0,比如子进程代码语法错误
        'stdout': stdout,
        'stderr': stderr
                })
    except subprocess.TimeoutExpired:   #超时后杀死进程树,释放资源,关闭管道的写端和读端,写端连子进程,读端连父进程,一个没关管道这块内存就不会释放,PID
        parent = psutil.Process(process.pid)
        #递归获取所有子进程并杀死
        try:
            for child in parent.children(recursive=True):
                child.kill()          #杀掉子进程,变成僵尸进程
        except psutil.NoSuchProcess:  #大坑:如果在杀子进程的过程中刚好子进程自然死亡,找不到子进程会报错,导致后面的子进程没杀成为孤儿进程,所以用except吞掉错误继续运行
            pass        
        except psutil.AccessDenied:   #防权限不足,杀不掉
            pass 
        parent.kill()   #最后杀死父进程,爷爷进程是agent,如果先杀父进程,所有子进程成为孤儿进程再也找不到,在后台吃资源,父进程死亡后,僵尸进程被过继到1号进程处理
        #最关键的一步,强制回收管道和僵尸进程
        #子进程死了,父进程手里的管道还在,必须用communicate关掉
        process.communicate()   #把三个管道的数据读完,然后关掉读端,释放父进程的PID,不管子进程
        #所有子进程的PID在父进程死后被过继到1号进程并被销毁,如果父进程没死,子进程占着PID,达到上限后无法创造新进程
        return json.dumps({
            'success': False,
            'error': f'命令执行超时{10}秒,强制终止'
        })


#正常执行:返回结果
#超时:杀死所有子进程成为僵尸进程,再杀死父进程,子进程过继给1号进程注销PID
#最后爷爷进程通过代码communicate抽取管道剩余数据,关闭读端和写端,注销父进程的PID