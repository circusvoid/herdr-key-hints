#!/usr/bin/env python3
"""在隔离目录中禁用 Git 凭据，验证公开仓库的安装与运行。"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='circusvoid/herdr-key-hints')
    parser.add_argument('--ref', required=True, help='待验收的版本标签或 commit SHA')
    args = parser.parse_args()
    original = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix='kh-install-', dir='/tmp') as temp:
        root = Path(temp)
        env = {k: v for k, v in original.items()
               if not k.startswith(('HERDR_', 'GIT_', 'GH_', 'GITHUB_'))
               and k not in ('SSH_ASKPASS',)}
        env.update(XDG_CONFIG_HOME=str(root/'c'), XDG_STATE_HOME=str(root/'s'),
                   XDG_CACHE_HOME=str(root/'cache'), GIT_CONFIG_NOSYSTEM='1',
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
                   GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='credential.helper',
                   GIT_CONFIG_VALUE_0='', GIT_ASKPASS='/usr/bin/false')

        def cli(*parts):
            result = subprocess.run(['herdr', *parts], env=env, cwd=root,
                                    capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise RuntimeError(f'Herdr {parts[:2]} 失败：{result.stderr[-2000:]}')
            return json.loads(result.stdout) if result.stdout.lstrip().startswith('{') else result.stdout

        cli('plugin', 'install', args.repo, '--ref', args.ref, '--yes')
        plugins = cli('plugin', 'list', '--json')['result']['plugins']
        plugin = next(p for p in plugins if p['plugin_id'] == 'local.key-hints')
        assert plugin['source']['kind'] == 'github', plugin['source']['kind']
        assert not plugin.get('warnings'), plugin.get('warnings')
        installed = next(root.rglob('herdr-plugin.toml')).parent
        if sys.platform == 'darwin':
            assert list((installed/'.build').glob('key-hints-*')), '安装期没有生成原生程序'
        subprocess.run([sys.executable, str(installed/'plugin.py'), 'doctor'],
                       env=env, cwd=installed, check=True, capture_output=True, text=True, timeout=20)
        smoke = 'smoke_overlay.py' if sys.platform == 'darwin' else 'smoke_herdr.py'
        subprocess.run([sys.executable, str(installed/'tests'/smoke)],
                       env=env, cwd=installed, check=True, timeout=100)
        print(json.dumps({'anonymous': True, 'repository': args.repo,
                          'version': plugin['version'], 'ref': args.ref,
                          'source': 'github', 'install_build_and_runtime': 'passed'}, ensure_ascii=False))
        cli('plugin', 'uninstall', 'local.key-hints')


if __name__ == '__main__':
    run()
