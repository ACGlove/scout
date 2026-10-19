"""让 agent 控制命令行的插件。

生效方式（无需改其它文件）：
  1. 本文件放在 src/tool/plugins/ 下，Plugins_Loader 会 import 它；
  2. @tool 装饰器把 run_command 变成 BaseTool 实例（模块级变量）；
  3. Loader 用 inspect.getmembers 抓到它，Registry 收 schema，
     Tool_Executor 发现签名里有 root，就自动注入工作区根路径。
"""

import json
import locale
import logging
import os
import re
import signal
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel, Field

from ..basetool_get import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- 常量
MAX_COMMAND_CHARS = 2_000  # 单条命令长度上限，防止把整段代码塞进命令行
MAX_OUTPUT_CHARS = 6_000  # 回给模型的输出上限，超出做头尾截断（中间省略）
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
TRUNCATED_MARK = '\n...<输出过长，中间部分已截断>...\n'

# 静态黑名单：命中即拒绝执行，把原因当作 observation 回给模型（不抛异常）
DENY_PATTERNS: list[tuple[str, str]] = [
    (r'\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+(/|/\*|~|\$HOME)\s*$', '不允许递归删除根目录或家目录'),
    (r'\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+\*\s*$', '不允许删除当前目录下所有文件'),
    (r'\bmkfs(\.[a-z0-9]+)?\b', '不允许格式化文件系统'),
    (r'\bdd\b[^|;&]*\bof=/dev/', '不允许直接写块设备'),
    (r'>\s*/dev/(sd|nvme|hd)', '不允许直接写块设备'),
    (r'\b(shutdown|reboot|halt|poweroff)\b', '不允许关机或重启'),
    (r'\bformat\s+[a-zA-Z]:', '不允许格式化磁盘'),
    (r'\bdel\s+(/[a-zA-Z]\s*)*["\']?[a-zA-Z]:(\\)?\*', '不允许删除整个盘符'),
    (r'\b(rd|rmdir)\s+/s\b', '不允许静默递归删除目录'),
    (r':\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:', '不允许 fork 炸弹'),
    (r'\b(curl|wget|iwr|invoke-webrequest)\b[^|;]*\|\s*(sudo\s+)?(ba|z|k)?sh\b',
     '不允许把网络脚本直接管道给 shell'),
    (r'\b(sudo|su|runas)\b', '不允许提权执行'),
    (r'\.env\b', '.env 可能含密钥，禁止通过命令行读写'),
    (r'id_(rsa|ed25519|ecdsa)\b', '禁止触碰 SSH 私钥'),
    (r'\.ssh([/\\]|$)', '禁止触碰 .ssh 目录'),
    (r'\.(pem|key|p12|pfx)\b', '禁止触碰密钥文件'),
    (r'^\s*(vi|vim|nvim|nano|emacs|top|htop|less|more|man)\b',
     '不支持交互式命令（stdin 已关闭，会一直等到超时）'),
    (r'^\s*(python|python3|py|node|bash|sh|cmd|powershell|mysql|psql)\s*$',
     '不支持进入交互式 REPL，请把完整命令写在同一条里'),
]

# 名字像密钥的环境变量不传给子进程，避免 `env`/`printenv` 把密钥漏进上下文
_SECRET_ENV = re.compile(r'(API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|TAVILY|_SK$)',
                         re.IGNORECASE)


class Run_Command_Schema(BaseModel):
    command: str = Field(
        description='要执行的完整命令字符串，如 "python -m pytest -q"、"git status --short"；'
                    '支持管道、重定向、&& ，由系统 shell 解析；不支持交互式命令',
    )
    cwd: str = Field(
        default='',
        description='命令的工作目录，必须是工作区内的相对路径；留空表示工作区根目录',
    )
    timeout: int = Field(
        default=DEFAULT_TIMEOUT,
        ge=1,
        le=MAX_TIMEOUT,
        description=f'超时秒数，1~{MAX_TIMEOUT}，默认 {DEFAULT_TIMEOUT}；超时会杀掉整个进程树',
    )


# ---------------------------------------------------------------- 小工具
def _payload(ok: bool, content: str | None = None, error: object = None, **extra) -> str:
    data: dict = {'ok': ok, 'error': error, 'content': content}
    data.update(extra)
    return json.dumps(data, ensure_ascii=False)


def _fail(message: str, code: str = 'error', hint: str = '', content: str | None = None,
          **extra) -> str:
    logger.warning('run_command 拒绝/失败 [%s] %s', code, message)
    return _payload(False, content=content,
                    error={'code': code, 'message': message, 'hint': hint}, **extra)


def _resolve_in_root(root: str, sub: str) -> Path:
    """把 cwd 解析成绝对路径，并保证落在 root 内（软链接逃逸也会被 resolve 出来）。"""
    base = Path(root or '.').expanduser().resolve()
    target = (base / sub).resolve() if sub and sub.strip() else base
    if target != base and base not in target.parents:
        raise ValueError(f'cwd 越界：{sub} 不在工作区 {base} 内')
    return target


def _decode(raw: bytes) -> str:
    """Windows 上 cmd 输出常是 GBK，逐级尝试解码，别用 errors='replace' 早早把中文糊掉。"""
    candidates = ['utf-8', locale.getpreferredencoding(False), 'gbk']
    tried: set[str] = set()
    for enc in candidates:
        if not enc or enc.lower() in tried:
            continue
        tried.add(enc.lower())
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('utf-8', errors='replace')


def _clip(text: str) -> tuple[str, bool]:
    """超长输出保留头尾，中间省略，避免一次工具调用把上下文撑爆。"""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    head = int(MAX_OUTPUT_CHARS * 0.66)
    tail = MAX_OUTPUT_CHARS - head
    return text[:head] + TRUNCATED_MARK + text[-tail:], True


def _format_output(code: int | None, stdout: str, stderr: str, timed_out: bool,
                   duration_ms: int) -> str:
    parts = [f'exit_code: {code}', f'timed_out: {timed_out}', f'duration_ms: {duration_ms}']
    parts.append('--- stdout ---')
    parts.append(stdout.rstrip() or '<empty>')
    if stderr.strip():
        parts.append('--- stderr ---')
        parts.append(stderr.rstrip())
    return '\n'.join(parts)


def _child_env() -> tuple[dict[str, str], int]:
    """复制父进程环境变量但剔掉疑似密钥的项；强制子进程 Python 用 utf-8 输出。"""
    env: dict[str, str] = {}
    dropped = 0
    for key, value in os.environ.items():
        if _SECRET_ENV.search(key):
            dropped += 1
            continue
        env[key] = value
    env['PYTHONIOENCODING'] = 'utf-8'
    return env, dropped


def _kill_tree(proc: subprocess.Popen) -> None:
    """杀掉整棵进程树，避免 shell=True 只死壳、子进程继续占着管道。"""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except OSError:  # 进程已退出 / 没权限
        proc.kill()


def _run(command: str, cwd: Path, timeout: int,
         env: dict[str, str]) -> tuple[int | None, str, str, bool]:
    """执行命令，返回 (退出码, stdout, stderr, 是否超时)。"""
    kwargs: dict = {}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    proc = subprocess.Popen(
        command,
        shell=True,                      # 需要管道/重定向，交给系统 shell 解析
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,        # 关键：否则子进程抢父进程 stdin，交互式命令直接挂死
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        **kwargs,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, _decode(out), _decode(err), False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:  # 极少见：进程树没回收干净
            out, err = b'', b''
            logger.error('命令超时且进程树未回收 pid=%s', proc.pid)
        return None, _decode(out), _decode(err), True


# ---------------------------------------------------------------- 工具本体
@tool(args_schema=Run_Command_Schema,max_retry=2)
def run_command(command: str, cwd: str = '', timeout: int = DEFAULT_TIMEOUT, root: str = '') -> str:
    """在工作区里执行一条命令行命令并返回退出码/stdout/stderr。

    什么时候用：
      - 需要项目的真实运行结果，而不是靠读代码猜：跑测试（pytest -q）、跑 linter、
        跑构建、`git status` / `git diff` / `git log`、`python -c` 做一次小验证、
        查看目录结构（Windows 用 `dir /b /s`，Unix 用 `find`）。
      - read_file 只能看到静态文本，而你要知道「这段代码到底跑不跑得起来」的时候。

    什么时候不要用：
      - 只是读文件内容/列文件名 -> 用 read_file / get_filepath（更省 token，也免去 shell 差异）；
      - 需要交互输入的命令（vim、python 裸 REPL、top、more）——stdin 是关闭的，只会等到超时；
      - 需要管理员权限、关机、改系统配置、删盘、往网络下载脚本再执行——会被安全策略直接拒绝；
      - 想改文件内容 -> 用 edit_file，别用 echo 重定向（引号/换行在 shell 里极易出错）。

    参数含义：
      - command：完整命令字符串，会交给系统 shell 执行（支持 | 、> 、&& ），单条 <=2000 字符；
      - cwd：工作目录，必须是工作区内的相对路径，留空即工作区根目录；越界会被拒绝；
      - timeout：超时秒数，1~120，默认 30；超时会杀掉整棵进程树并返回 code=timeout。

    返回：JSON 字符串 {ok, error, content, exit_code, truncated, duration_ms, cwd}
      - ok=False 且 error.code 为 blocked/sandbox/timeout/exit_code/...，请按 error.hint 调整；
      - 命令退出码非 0 也是 ok=False，但 content 里仍有 stdout/stderr 供你分析；
      - content 超过 6000 字符会截断（truncated=true），请改用更精准的命令而不是重跑。
    """
    logger.info('正在调用命令行工具')
    started = time.perf_counter()
    command = (command or '').strip()

    # 1) 参数校验：一律返回 observation，不抛异常
    if not command:
        return _fail('command 为空', code='invalid_arg', hint='把要执行的完整命令写进 command')
    if len(command) > MAX_COMMAND_CHARS:
        return _fail(f'command 超过 {MAX_COMMAND_CHARS} 字符', code='invalid_arg',
                     hint='拆成几条短命令，或先把内容写成脚本文件再执行')

    # 2) 安全策略：命中黑名单直接拒绝，绝不下发到 shell
    for pattern, reason in DENY_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            logger.warning('命令被安全策略拒绝: %s', command)
            return _fail(reason, code='blocked', command=command,
                         hint='改用只读、可逆、限定在 cwd 内的做法；确需执行请让用户在终端里手动跑')

    # 3) 工作目录沙箱
    try:
        workdir = _resolve_in_root(root, cwd)
    except ValueError as exc:
        logger.warning('cwd 越界 root=%s cwd=%s', root, cwd)
        return _fail(str(exc), code='sandbox',
                     hint='cwd 只能是工作区内的相对路径，留空表示工作区根目录')
    if not workdir.is_dir():
        return _fail(f'目录不存在：{workdir}', code='not_found',
                     hint='先用 get_filepath 看看有哪些目录，再传 cwd')

    # 4) 超时参数夹到合法区间
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    timeout = max(1, min(timeout, MAX_TIMEOUT))

    env, dropped = _child_env()
    logger.info('执行命令 cwd=%s timeout=%s dropped_env_vars=%s cmd=%s',
                workdir, timeout, dropped, command)

    # 5) 执行
    try:
        code, stdout, stderr, timed_out = _run(command, workdir, timeout, env)
    except OSError as exc:
        logger.exception('命令启动失败')
        return _fail(f'命令启动失败：{exc}', code='os_error',
                     hint='检查命令拼写、shell 是否存在、工作目录是否可访问')

    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info('命令结束 exit_code=%s timed_out=%s duration_ms=%s cmd=%s',
                code, timed_out, duration_ms, command)

    content, truncated = _clip(_format_output(code, stdout, stderr, timed_out, duration_ms))
    extra = {'exit_code': code, 'truncated': truncated, 'duration_ms': duration_ms,
             'cwd': str(workdir)}

    if timed_out:
        return _fail(f'命令超时（{timeout}s），已杀掉进程树', code='timeout',
                     content=content, **extra,
                     hint='换更快的命令，或显式传更大的 timeout（上限 120）')
    if code != 0:
        return _fail(f'命令退出码 {code}', code='exit_code', content=content, **extra,
                     hint='读 stderr 定位问题，修好后重跑；不要原样重复同一条失败命令')
    return _payload(True, content=content, error=None, **extra)
