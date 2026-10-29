"""run_command 工具的测试。

被测对象：src/tool/plugins/run_command.py 里的 run_command.func(root, command)。
返回值是 json 字符串，字段约定：
    正常：{'success': bool, 'stdout': str, 'stderr': str}
    超时：{'success': False, 'error': '命令执行超时10秒,强制终止'}
    非白名单：{'error': '命令权限不足,请换种策略执行任务'}

两个实现细节决定了测试怎么写：
    1. 输出超过 2000 字符时只保留 前1000 + 截断标记 + 后1000，断言直接盯这个标记；
    2. 超时写死 10 秒，测试不能真等 10 秒，所以把 Popen 包一层，只把第一次
       communicate 的超时压到 2 秒——进程、进程树、杀进程仍然是真的。

跑法（在 scout/ 下）：python -m pytest tests/test_run_command.py -v
"""

import json
import os
import subprocess
import time

import psutil
import pytest

import src.tool.plugins.run_command as rc_mod          # 为了 patch 模块里用到的 subprocess.Popen
from src.tool.plugins.run_command import run_command

# run_command 里用了 subprocess.CREATE_NO_WINDOW，这个常量只有 Windows 才有
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='run_command 只支持 Windows')

TRUNC_MARK = '\n...输出过长已截断...\n'   # 和实现里的标记完全一致（含首尾换行共 15 个字符），实现改了标记这个测试就该红
FAKE_TIMEOUT = 2.0                    # 假超时：真等 10 秒太慢，压到 2 秒
_REAL_POPEN = subprocess.Popen        # patch 之前抓住真 Popen，否则替身会自己调自己导致递归


def _run(root, command):
    """调工具并解 json，省得每个用例都写两行。"""
    return json.loads(run_command.func(root=str(root), command=command))


def _write_script(tmp_path, name, body):
    """把子进程要跑的代码写成脚本文件，避开 windows 命令行里层层嵌套的引号。"""
    (tmp_path / name).write_text(body, encoding='utf-8')
    return f'python {name}'


def _wait_gone(pid, timeout=5.0):
    """轮询等 pid 消失：kill 是异步的，杀完立刻断言会偶发失败，给系统一点回收时间。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not psutil.pid_exists(pid):
            return True
        time.sleep(0.05)
    return not psutil.pid_exists(pid)


# 用 sys.stdout.write，不用 print，保证输出里不混进额外的换行符
_LONG_OUTPUT_SCRIPT = """
import sys

stream = sys.stdout if sys.argv[1] == 'stdout' else sys.stderr
stream.write(('a' if sys.argv[1] == 'stdout' else 'b') * int(sys.argv[2]))
"""

# 父进程起两个孙子进程并把 pid 记到文件里，然后自己睡死，模拟一条卡住的命令
_TREE_SCRIPT = """
import subprocess
import sys
import time

pids = []
for _ in range(2):
    pids.append(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']).pid)

with open(sys.argv[1], 'w', encoding='utf-8') as f:
    f.write('\\n'.join(str(pid) for pid in pids))

time.sleep(120)
"""


# ---------------------------------------------------------------- 1. 正常执行


def test_normal_command_returns_stdout(tmp_path):
    """正常执行：退出码 0，stdout 拿到子进程打印的内容，stderr 为空。"""
    result = _run(tmp_path, 'python -c "print(123)"')

    assert result['success'] is True           # 退出码 0 才算成功
    assert result['stdout'].strip() == '123'   # 子进程的标准输出要被原样带回来
    assert result['stderr'] == ''              # 没往 stderr 写东西，应该是空串


def test_command_runs_in_root_directory(tmp_path):
    """cwd 必须切到 root，否则相对路径的命令会跑在 agent 自己的目录里。"""
    (tmp_path / 'hi.txt').write_text('hello-root', encoding='utf-8')

    result = _run(tmp_path, 'type hi.txt')

    assert result['success'] is True           # type 读到了文件，退出码为 0
    assert 'hello-root' in result['stdout']    # 读到的正是 root 下的文件，说明 cwd 生效了


def test_nonzero_exit_code_reports_failure(tmp_path):
    """子进程非 0 退出：success 要为 False，但 stdout/stderr 照样得带回来。"""
    result = _run(tmp_path, 'python -c "import sys; sys.exit(3)"')

    assert result['success'] is False          # 非 0 退出码一律算执行失败
    assert result['stdout'] == ''              # 这个脚本不打印任何东西
    assert result['stderr'] == ''              # 也不往 stderr 写东西


# ------------------------------------------------- 2. stdout / stderr 超长截断


def test_long_stdout_is_truncated(tmp_path):
    """stdout 超过 2000 字符：只留前 1000 + 标记 + 后 1000，防止 token 爆炸。"""
    cmd = _write_script(tmp_path, 'long_output.py', _LONG_OUTPUT_SCRIPT) + ' stdout 3000'

    result = _run(tmp_path, cmd)

    stdout = result['stdout']
    assert result['success'] is True                     # 截断只改内容，不影响成功判定
    assert TRUNC_MARK in stdout                          # 截断标记出现了
    assert len(stdout) == 1000 + len(TRUNC_MARK) + 1000  # 长度正好是头 1000 + 标记 + 尾 1000
    assert stdout.startswith('a' * 1000)                 # 头部 1000 个字符原样保留
    assert stdout.endswith('a' * 1000)                   # 尾部 1000 个字符原样保留


def test_long_stderr_is_truncated(tmp_path):
    """stderr 同样有 2000 字符上限，别让报错日志把上下文塞满。"""
    cmd = _write_script(tmp_path, 'long_output.py', _LONG_OUTPUT_SCRIPT) + ' stderr 3000'

    result = _run(tmp_path, cmd)

    stderr = result['stderr']
    assert result['success'] is True                     # 截断只改内容，不影响成功判定
    assert TRUNC_MARK in stderr                          # 错误输出也被截断了
    assert len(stderr) == 1000 + len(TRUNC_MARK) + 1000  # 同样是头 1000 + 标记 + 尾 1000
    assert stderr.startswith('b' * 1000)                 # 错误输出的头部 1000 个字符保留
    assert stderr.endswith('b' * 1000)                   # 错误输出的尾部 1000 个字符保留
    assert result['stdout'] == ''                        # 全写 stderr 了，stdout 应为空


def test_output_at_limit_is_not_truncated(tmp_path):
    """边界：正好 2000 字符不截断（实现是 len > 2000 才动手）。"""
    cmd = _write_script(tmp_path, 'long_output.py', _LONG_OUTPUT_SCRIPT) + ' stdout 2000'

    result = _run(tmp_path, cmd)

    assert TRUNC_MARK not in result['stdout']  # 刚好卡在上限，不该出现截断标记
    assert len(result['stdout']) == 2000       # 2000 个字符一个不少


# ------------------------------------------------------------------ 3. 超时


def _make_short_timeout_popen(created):
    """Popen 替身：真起进程、真杀进程，只把第一次 communicate 的 timeout 压短。"""

    class ShortTimeoutPopen:
        def __init__(self, *args, **kwargs):
            self._proc = _REAL_POPEN(*args, **kwargs)   # 用真 Popen 起真进程树
            self._first = True
            created.append(self)                        # 记下来，测试要拿它的 pid

        def __getattr__(self, name):
            # pid / returncode / poll 等属性全部透传给真进程
            return getattr(self._proc, name)

        def communicate(self, timeout=None):
            if self._first:
                self._first = False
                return self._proc.communicate(timeout=FAKE_TIMEOUT)   # 第一次调用立刻超时
            # 超时分支里工具会再调一次无参的 communicate()，此时进程已死，用来收掉管道；
            # 这里加超时是为了万一有孙子进程漏杀，测试报错而不是把整个测试套件挂死
            return self._proc.communicate(timeout=10)

    return ShortTimeoutPopen


def test_timeout_kills_whole_process_tree(tmp_path, monkeypatch):
    """超时：返回值是失败 + error，且父进程和所有孙子进程都要被杀干净。"""
    _write_script(tmp_path, 'tree.py', _TREE_SCRIPT)

    created = []
    monkeypatch.setattr(rc_mod.subprocess, 'Popen', _make_short_timeout_popen(created))

    result = _run(tmp_path, 'python tree.py pids.txt')

    assert result['success'] is False       # 超时无条件算执行失败
    assert '超时' in result['error']        # error 里要说明是超时导致的
    assert '强制终止' in result['error']    # 并且说明已经强制终止，而不是干等着
    assert 'stdout' not in result           # 超时走 error 分支，不返回半截输出
    assert len(created) == 1                # 确认替身真被用上了，否则下面的断言是白测

    pids_file = tmp_path / 'pids.txt'
    assert pids_file.exists()               # 前置条件：子进程树确实建起来了
    grandchild_pids = [int(x) for x in pids_file.read_text(encoding='utf-8').split()]
    assert len(grandchild_pids) == 2        # 前置条件：两个孙子进程的 pid 都记下来了

    for pid in grandchild_pids:
        assert _wait_gone(pid)              # 每个孙子进程都被递归杀掉，没留下孤儿进程

    assert _wait_gone(created[0].pid)       # 父进程（cmd.exe）最后也被杀掉了
