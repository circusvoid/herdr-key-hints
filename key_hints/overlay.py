"""macOS 浮层进程与原子帧文件；不捕获键盘，也不读取终端内容。"""
from __future__ import annotations

import hashlib
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def frame_path(env: dict) -> Path:
    key = hashlib.sha256(env['HERDR_SOCKET_PATH'].encode()).hexdigest()[:24]
    return Path(env['HERDR_PLUGIN_STATE_DIR']) / (key + '.overlay.json')


def build_path(directory: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / 'native' / 'KeyHints.swift'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    return directory / ('key-hints-' + platform.machine() + '-' + digest)


def prepare(env: dict | None = None) -> Path:
    from .runtime import state_lock
    from .checks import swift_compiler
    if sys.platform != 'darwin':
        raise ValueError('overlay 显示需要 macOS；其他平台请使用 renderer = "herdr"。')
    root = Path(__file__).resolve().parents[1]
    installed = build_path(root / '.build')
    if installed.is_file() and os.access(installed, os.X_OK):
        return installed
    directory = Path(env['HERDR_PLUGIN_STATE_DIR']) / 'bin' if env else root / '.build'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    binary = build_path(directory)
    if binary.is_file() and os.access(binary, os.X_OK):
        return binary
    with state_lock(directory / 'build.lock', timeout=90):
        if binary.is_file() and os.access(binary, os.X_OK):
            return binary
        compiler = swift_compiler()
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            target = Path(temp) / 'key-hints'
            result = subprocess.run([compiler, '-O', str(root / 'native' / 'KeyHints.swift'), '-o', str(target)],
                                    capture_output=True, text=True, timeout=90)
            if result.returncode:
                raise RuntimeError('原生浮层编译失败：' + result.stderr[-3000:])
            os.replace(target, binary)
    return binary


def start(env: dict) -> subprocess.Popen:
    binary = prepare(env)
    return subprocess.Popen([str(binary), str(frame_path(env)), str(os.getpid())],
                            stdin=subprocess.DEVNULL, close_fds=True)


def clear(env: dict) -> None:
    frame_path(env).unlink(missing_ok=True)


def publish(env: dict, entries: list[dict], options: dict, now: float) -> dict:
    from .runtime import write_state
    epoch = time.time()
    payload = dict(generated=epoch, position=options['position'],
                   fade_ms=options.get('fade_ms', 200), max_visible=options.get('max_visible', 3),
                   terminal_apps=options.get('terminal_apps', []),
                   entries=[dict(id=item['id'], chord=item['chord'], count=item['count'],
                                 updated=epoch + item['updated'] - now,
                                 expires=epoch + item['expires'] - now) for item in entries])
    write_state(frame_path(env), payload)
    # 只代表帧已交付，是否可见由浮层的前台应用检查决定。
    return {'published': True, 'reason': 'published', 'renderer': 'overlay'}
