#!/usr/bin/env python3
"""隔离 XDG 配置与状态，验证原生插件清单、事件钩子和通知调用。"""
import json
import os
import pty
import fcntl
import struct
import termios
import threading
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = 'local.key-hints'


def run():
    binary = shutil.which('herdr')
    if not binary:
        raise RuntimeError('集成测试需要安装 Herdr 0.9.0 或更高版本。')
    # Unix socket 路径有长度限制；macOS 的默认临时目录通常较长。
    with tempfile.TemporaryDirectory(prefix='kh-', dir='/tmp') as tmp:
        root = Path(tmp)
        env = {key: value for key, value in os.environ.items() if not key.startswith('HERDR_')}
        env.update(XDG_CONFIG_HOME=str(root / 'c'), XDG_STATE_HOME=str(root / 's'), XDG_CACHE_HOME=str(root / 'cache'))
        conf = root / 'c/herdr'
        conf.mkdir(parents=True)
        plugin_conf = conf / 'plugins/config/local.key-hints'
        plugin_conf.mkdir(parents=True)
        (plugin_conf / 'config.toml').write_text('renderer = "herdr"\n')
        (conf / 'config.toml').write_text('''onboarding = false
[terminal]
default_shell = "/bin/sh"
shell_mode = "non_login"
[keys]
new_tab = ["prefix+c", "cmd+t"]
split_vertical = ["prefix+v", "cmd+d"]
split_horizontal = ["prefix+minus", "cmd+shift+d"]
zoom = ["prefix+z", "cmd+enter"]
close_pane = ["prefix+x", "cmd+w"]
switch_tab = ["prefix+1..9", "cmd+1..9"]
switch_workspace = "ctrl+1..9"
[ui.toast]
delivery = "herdr"
''')

        def cli(*args):
            p = subprocess.run([binary, *args], env=env, cwd=root, capture_output=True, text=True, timeout=8)
            if p.returncode:
                raise RuntimeError(f'{args}: {p.stderr}')
            return json.loads(p.stdout) if p.stdout.strip().startswith('{') else p.stdout.strip()

        def logs():
            value = cli('plugin', 'log', 'list', '--plugin', PLUGIN_ID, '--limit', '200')['result']
            if 'logs' not in value:
                raise RuntimeError('未知日志响应：' + repr(value))
            return value['logs']

        def wait_for(predicate, label):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                value = predicate()
                if value:
                    return value
                time.sleep(.08)
            raise AssertionError(label + '\n' + repr(logs()) + '\n' + repr(cli('api', 'snapshot')))

        def hints():
            rows = []
            for entry in logs():
                if entry.get('status') == 'failed':
                    raise AssertionError('插件钩子失败：' + repr(entry))
                for line in (entry.get('stdout') or '').splitlines():
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if 'shortcut' in item:
                        rows.append((entry['log_id'], item))
            for path in root.rglob('*.watch.log'):
                for number, line in enumerate(path.read_text().splitlines()):
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if 'shortcut' in item:
                        rows.append((f'watch:{path.name}:{number}', item))
            return rows

        def verify(action, shortcut, mutation):
            seen = {row[0] for row in hints()}
            mutation()
            result = wait_for(lambda: [item for log_id, item in hints() if log_id not in seen and item['action'] == action], action + ' 没有触发')
            assert result[0]['shortcut'] == shortcut, result
            assert result[0]['notification'].get('reason') == 'no_foreground_client', result
            # 等待同一次操作的其余钩子完成，确认不会重复显示创建/焦点提示。
            wait_for(lambda: all(item.get('status') != 'running' for item in logs()), '钩子未完成')
            generated = [item for log_id, item in hints() if log_id not in seen]
            assert len(generated) == 1, generated
            print(f'{action}: {shortcut}，原生事件与通知请求通过')

        registration = cli('plugin', 'link', str(ROOT), '--enabled')
        assert not registration['result']['plugin'].get('warnings'), registration
        server = None
        with (root / 'server.log').open('w+') as log:
            try:
                server = subprocess.Popen([binary, 'server'], env=env, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)

                def ready():
                    if server.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        return cli('api', 'snapshot')['result']['snapshot']
                    except RuntimeError:
                        return None

                snapshot = wait_for(ready, '测试服务器没有启动')
                wait_for(lambda: any('initialized' in (item.get('stdout') or '') for item in logs()), 'startup 钩子未初始化')
                cli('workspace', 'create', '--label', '测试工作区', '--cwd', str(root))
                wait_for(lambda: all(item.get('status') != 'running' for item in logs()), '工作区初始化未完成')
                cli('plugin', 'action', 'invoke', PLUGIN_ID + '.initialize')
                wait_for(lambda: all(item.get('status') != 'running' for item in logs()), '基线初始化未完成')
                snapshot = cli('api', 'snapshot')['result']['snapshot']
                workspace = snapshot['focused_workspace_id']
                original_tab = snapshot['focused_tab_id']
                holder = {}

                def create_tab():
                    holder.update(cli('tab', 'create', '--workspace', workspace, '--focus')['result'])

                second = cli('workspace', 'create', '--label', '第二个 Space', '--cwd', str(root))['result']['workspace']['workspace_id']
                wait_for(lambda: all(item.get('status') != 'running' for item in logs()), '创建第二个工作区尚未完成')
                verify('switch_workspace', '⌃2', lambda: cli('workspace', 'focus', second))
                verify('switch_workspace', '⌃1', lambda: cli('workspace', 'focus', workspace))
                verify('new_tab', '⌘T', create_tab)
                tab_id = holder['tab']['tab_id']
                pane_id = holder['root_pane']['pane_id']
                verify('split_vertical', '⌘D', lambda: cli('pane', 'split', pane_id, '--direction', 'right', '--focus'))
                current = cli('api', 'snapshot')['result']['snapshot']['focused_pane_id']
                verify('split_horizontal', '⇧⌘D', lambda: cli('pane', 'split', current, '--direction', 'down', '--focus'))
                current = cli('api', 'snapshot')['result']['snapshot']['focused_pane_id']
                verify('zoom', '⌘Enter', lambda: cli('pane', 'zoom', current, '--on'))
                verify('zoom', '⌘Enter', lambda: cli('pane', 'zoom', current, '--off'))
                verify('switch_tab', '⌘1', lambda: cli('tab', 'focus', original_tab))
                verify('switch_tab', '⌘2', lambda: cli('tab', 'focus', tab_id))
                verify('close_pane', '⌘W', lambda: cli('pane', 'close', current))
                config_file = conf / 'config.toml'
                config_file.write_text(config_file.read_text().replace('"cmd+t"', '"cmd+shift+t"'))
                cli('server', 'reload-config')
                verify('new_tab', '⇧⌘T', create_tab)
                # 暂停只针对测试会话，不杀进程，不改变 Herdr 配置。
                cli('plugin', 'action', 'invoke', PLUGIN_ID + '.stop')
                wait_for(lambda: not list(root.rglob('*.ready.json')), '暂停后订阅没有退出')
                count = len(hints())
                create_tab()
                time.sleep(.5)
                assert len(hints()) == count, '暂停后仍然产生提示'
                cli('plugin', 'action', 'invoke', PLUGIN_ID + '.initialize')
                wait_for(lambda: bool(list(root.rglob('*.ready.json'))), '恢复后没有重新订阅')
                wait_for(lambda: all(item.get('status') != 'running' for item in logs()), '恢复尚未完成')
                verify('new_tab', '⇧⌘T', create_tab)
                # 附着真实终端客户端，发送 Kitty 协议的 Control+2。
                master, slave = pty.openpty()
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 120, 0, 0))
                attached = subprocess.Popen([binary], env=dict(env, TERM='xterm-256color'), cwd=root,
                                            stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
                os.close(slave)
                def drain():
                    try:
                        while os.read(master, 65536):
                            pass
                    except OSError:
                        pass
                reader = threading.Thread(target=drain, daemon=True)
                reader.start()
                try:
                    time.sleep(1)
                    seen = {row[0] for row in hints()}
                    os.write(master, b'\x1b[50;5u')
                    wait_for(lambda: cli('api', 'snapshot')['result']['snapshot']['focused_workspace_id'] == second,
                             'Control+2 没有切换 Space')
                    result = wait_for(lambda: [item for log_id, item in hints() if log_id not in seen
                                                and item['action'] == 'switch_workspace'], 'Control+2 没有提示')
                    assert result[0]['shortcut'] == '⌃2', result
                    assert result[0]['notification']['shown'], result
                    print('真实终端 Control+2：Space 切换与提示显示通过')
                    seen = {row[0] for row in hints()}
                    os.write(master, b'\x1b[49;5u')
                    wait_for(lambda: cli('api', 'snapshot')['result']['snapshot']['focused_workspace_id'] == workspace,
                             'Control+1 没有切换 Space')
                    # 等待动作入队，再连续请求相同预览，验证合并与 FIFO。
                    def pending_space():
                        for state_file in root.rglob('*.json'):
                            try:
                                state = json.loads(state_file.read_text())
                            except (ValueError, OSError):
                                continue
                            if isinstance(state, dict) and any(item.get('chord') == '⌃1'
                                    for item in state.get('delivery', {}).get('pending', [])):
                                return True
                        return False
                    wait_for(pending_space, 'Control+1 没有进入提示队列')
                    cli('plugin', 'action', 'invoke', PLUGIN_ID + '.preview')
                    cli('plugin', 'action', 'invoke', PLUGIN_ID + '.preview')
                    def shown_hints():
                        return [item for log_id, item in hints() if log_id not in seen
                                and item['notification'].get('shown')]
                    shown = wait_for(lambda: shown_hints() if len(shown_hints()) >= 2 else None,
                                     '队列没有依次显示两条提示')
                    assert [item['shortcut'] for item in shown] == ['⌃1', '⇧⌘T'], shown
                    assert shown[1]['count'] == 2, shown
                    print('真实终端提示队列：不同提示按顺序显示、相同提示合并计数通过')
                finally:
                    attached.terminate()
                    attached.wait(timeout=5)
                    os.close(master)
                cli('plugin', 'disable', PLUGIN_ID)
                wait_for(lambda: not list(root.rglob('*.ready.json')), '禁用插件后订阅没有退出')
                print('配置热读取、暂停/恢复、禁用后退出：通过')
                print('真实 Herdr 隔离集成测试通过；没有改动用户插件注册表或会话。')
            finally:
                if server is not None and server.poll() is None:
                    try:
                        cli('server', 'stop')
                        server.wait(timeout=5)
                    except (RuntimeError, subprocess.TimeoutExpired):
                        server.terminate()
                        server.wait(timeout=5)


if __name__ == '__main__':
    run()
