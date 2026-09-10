"""在安装或诊断阶段检查依赖；不安装工具，也不修改系统设置。"""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def swift_compiler() -> str:
    compiler = shutil.which('swiftc')
    if not compiler:
        raise ValueError('缺少 Swift 工具链；请先安装 Xcode Command Line Tools，或选择 herdr 通知模式。')
    if compiler == '/usr/bin/swiftc':
        selected = subprocess.run(['/usr/bin/xcode-select', '-p'], capture_output=True, text=True, timeout=5)
        if selected.returncode:
            raise ValueError('未配置 Xcode Command Line Tools；请完成工具链安装后重试。')
    result = subprocess.run([compiler, '--version'], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError('Swift 编译器不可用：' + result.stderr.strip()[:500])
    return compiler


def check_environment(client, renderer: str) -> dict:
    if sys.version_info < (3, 11):
        raise ValueError('需要 Python 3.11 或更高版本。')
    version = client.call('--version', json_output=False).strip()
    match = re.search(r'\b(\d+)\.(\d+)\.(\d+)\b', version)
    if not match or tuple(map(int, match.groups())) < (0, 9, 0):
        raise ValueError('需要 Herdr 0.9.0 或更高版本；当前版本：' + version)
    result = dict(python=platform.python_version(), herdr=version, renderer=renderer,
                  platform=sys.platform, architecture=platform.machine())
    if renderer == 'overlay':
        if sys.platform != 'darwin':
            raise ValueError('原生浮层仅支持 macOS；请设置 renderer = "herdr"。')
        from .overlay import build_path
        cached = build_path(Path(__file__).resolve().parents[1] / '.build')
        if cached.is_file() and cached.stat().st_mode & 0o111:
            result['native_binary'] = str(cached)
        else:
            result['swiftc'] = swift_compiler()
    return result
