#!/usr/bin/env python3
"""隔离 Herdr 会话，验证原生进程生命周期与真实事件到帧文件的交付。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run():
    if sys.platform != 'darwin':
        print('原生浮层集成测试仅支持 macOS。')
        return
    binary = shutil.which('herdr')
    with tempfile.TemporaryDirectory(prefix='kh-native-', dir='/tmp') as temp:
        root = Path(temp)
        env = {k: v for k, v in os.environ.items() if not k.startswith('HERDR_')}
        env.update(XDG_CONFIG_HOME=str(root/'c'), XDG_STATE_HOME=str(root/'s'), XDG_CACHE_HOME=str(root/'cache'))
        config = root/'c/herdr'
        plugin_config = config/'plugins/config/local.key-hints'
        plugin_config.mkdir(parents=True)
        (config/'config.toml').write_text('''onboarding = false
[terminal]
default_shell = "/bin/sh"
shell_mode = "non_login"
[keys]
new_tab = "cmd+t"
switch_workspace = "ctrl+1..9"
''')
        # 测试只检验窗口自身属性与帧交付，不在用户的前台应用弹出测试操作。
        (plugin_config/'config.toml').write_text('''renderer = "overlay"
hold_ms = 5000
terminal_apps = ["test.key-hints.no-foreground"]
''')

        def cli(*args):
            p = subprocess.run([binary, *args], env=env, cwd=root, capture_output=True, text=True, timeout=15)
            if p.returncode:
                raise RuntimeError(f'{args}: {p.stderr}')
            return json.loads(p.stdout) if p.stdout.lstrip().startswith('{') else p.stdout.strip()

        def wait_for(check, label, timeout=15):
            deadline = time.monotonic()+timeout
            while time.monotonic() < deadline:
                value = check()
                if value:
                    return value
                time.sleep(.04)
            raise AssertionError(label)

        def ready_info():
            for p in root.rglob('*.ready.json'):
                try:
                    return json.loads(p.read_text())
                except (OSError, ValueError):
                    pass

        def frame():
            for p in root.rglob('*.overlay.json'):
                try:
                    return json.loads(p.read_text())
                except (OSError, ValueError):
                    pass

        def alive(pid):
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False

        def invoke(action):
            cli('plugin', 'action', 'invoke', 'local.key-hints.'+action)

        cli('plugin', 'link', str(ROOT), '--enabled')
        with (root/'server.log').open('w') as log:
            server = subprocess.Popen([binary, 'server'], env=env, cwd=root, stdin=subprocess.DEVNULL,
                                      stdout=log, stderr=log, start_new_session=True)
            try:
                info = wait_for(ready_info, '原生订阅进程没有启动', timeout=60)
                assert info['renderer'] == 'overlay' and alive(info['overlay_pid']), info
                sys.path.insert(0, str(ROOT))
                from key_hints.overlay import build_path
                native = build_path(ROOT / '.build')
                if not native.exists():
                    native = next(root.rglob('key-hints-*'))
                subprocess.run([str(native), '--self-test'], check=True, timeout=10)
                cli('workspace', 'create', '--label', '测试工作区', '--cwd', str(root))
                cli('workspace', 'create', '--label', '第二工作区', '--cwd', str(root))
                time.sleep(.3)
                snap = cli('api', 'snapshot')['result']['snapshot']
                workspaces = [w['workspace_id'] for w in snap['workspaces']]
                cli('workspace', 'focus', workspaces[0])
                time.sleep(.3)
                invoke('initialize')
                wait_for(lambda: frame() is None, '初始化没有清理历史')
                for index in [1, 0, 1]:
                    last = (frame() or {}).get('generated', 0)
                    cli('workspace', 'focus', workspaces[index])
                    wait_for(lambda: frame() if frame() and frame()['generated'] > last else None, '焦点操作没有即时交付')
                data = frame()
                assert [i['chord'] for i in data['entries']] == ['⌃2', '⌃1', '⌃2'], data
                assert data['entries'][-1]['updated'] - data['entries'][0]['updated'] < 3, data
                for count in [1, 2]:
                    invoke('preview')
                    wait_for(lambda: frame() and frame()['entries'][-1]['chord'] == '⌘T'
                             and frame()['entries'][-1]['count'] == count, '连续重复计数没有更新')
                assert len(frame()['entries']) == 3
                print('真实事件即时交付：A→B→A 保留顺序、三组上限、连续重复更新 ×2，通过')
                pid = info['overlay_pid']
                invoke('stop')
                wait_for(lambda: ready_info() is None and not alive(pid), '暂停后原生进程未退出')
                assert frame() is None
                invoke('initialize')
                info = wait_for(ready_info, '恢复失败')
                assert alive(info['overlay_pid']) and frame() is None
                cli('plugin', 'disable', 'local.key-hints')
                wait_for(lambda: ready_info() is None and not alive(info['overlay_pid']), '禁用后原生进程未退出')
                print('原生进程启动、暂停清理、恢复不回放、禁用退出，通过')
            finally:
                if server.poll() is None:
                    cli('server', 'stop')
                    server.wait(timeout=8)
                for path in root.rglob('*.watch.log'):
                    log_text = path.read_text()
                    if 'Traceback' in log_text:
                        raise AssertionError(log_text)
        print('原生浮层隔离集成测试通过；未修改用户会话或插件配置。')


if __name__ == '__main__':
    run()
