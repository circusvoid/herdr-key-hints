"""补充订阅清单钩子未开放的布局事件；每个会话最多一个订阅进程。"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

from .runtime import Herdr, PLUGIN_ID, output, run_hook, settings, socket_stamp, write_state


def files(env: dict[str, str]) -> tuple[Path, Path, Path, Path]:
    endpoint = env.get("HERDR_SOCKET_PATH")
    state = env.get("HERDR_PLUGIN_STATE_DIR")
    if not endpoint or not state:
        raise ValueError("缺少 Herdr 插件会话上下文。")
    directory = Path(state)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(endpoint.encode()).hexdigest()[:24]
    return tuple(directory / (key + suffix) for suffix in (".watch.lock", ".ready.json", ".paused.json", ".watch.log"))


def paused(env: dict[str, str]) -> bool:
    path = files(env)[2]
    try:
        return json.loads(path.read_text()).get("socket") == socket_stamp(env["HERDR_SOCKET_PATH"])
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def running(lock: Path) -> bool:
    with lock.open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(stream, fcntl.LOCK_UN)
        return False


def ensure_running(env: dict[str, str], resume: bool = False) -> None:
    lock, ready, pause, log = files(env)
    if resume:
        pause.unlink(missing_ok=True)
    if paused(env) or running(lock):
        return
    if settings(env)["renderer"] == "overlay":
        from .overlay import prepare
        prepare(env)
    plugin = Path(__file__).resolve().parents[1] / "plugin.py"
    with log.open("ab") as output_file:
        child = subprocess.Popen(
            [sys.executable, str(plugin), "watch"], env=env, cwd=plugin.parent,
            stdin=subprocess.DEVNULL, stdout=output_file, stderr=output_file,
            start_new_session=True, close_fds=True,
        )
    deadline = time.monotonic() + 3
    expected = socket_stamp(env["HERDR_SOCKET_PATH"])
    while time.monotonic() < deadline:
        try:
            data = json.loads(ready.read_text())
            if data.get("socket") == expected and running(lock):
                return
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        if child.poll() is not None:
            if child.returncode == 0 and running(lock):
                return  # 另一个并发钩子已经建立订阅。
            raise RuntimeError(f"布局事件订阅启动失败，详情见 {log}")
        time.sleep(.03)
    raise TimeoutError(f"布局事件订阅未就绪，详情见 {log}")


def stop(env: dict[str, str]) -> None:
    from .overlay import clear
    clear(env)
    write_state(files(env)[2], {"socket": socket_stamp(env["HERDR_SOCKET_PATH"])})
    output(status="paused", note="仅暂停当前会话；initialize 动作恢复提示。")


def status(env: dict[str, str]) -> None:
    lock, ready, _, log = files(env)
    try:
        info = json.loads(ready.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        info = {}
    output(renderer=info.get("renderer"), overlay_pid=info.get("overlay_pid"), status="paused" if paused(env) else "running" if running(lock) else "stopped", watcher_log=str(log))


def rpc(endpoint: str, method: str) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect(endpoint)
        connection.sendall(json.dumps({"id": "key-hints-check", "method": method, "params": {}}).encode() + b"\n")
        with connection.makefile("rb") as reader:
            data = reader.readline(8 * 1024 * 1024)
        result = json.loads(data)
        if "error" in result:
            raise RuntimeError(str(result["error"]))
        return result["result"]


def plugin_enabled(endpoint: str) -> bool:
    return any(item["plugin_id"] == PLUGIN_ID and item["enabled"] for item in rpc(endpoint, "plugin.list")["plugins"])


def watch(env: dict[str, str]) -> None:
    lock, ready, _, log = files(env)
    sys.stdout.reconfigure(line_buffering=True)
    endpoint = env["HERDR_SOCKET_PATH"]
    with lock.open("a+") as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        presenter = None
        try:
            if paused(env) or not plugin_enabled(endpoint):
                return
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(3)
                connection.connect(endpoint)
                connection.sendall(json.dumps({
                    "id": "key-hints-layouts", "method": "events.subscribe", "params": {
                        "subscriptions": [{"type": kind} for kind in (
                            "layout.updated", "pane.updated", "workspace.focused", "tab.focused", "pane.focused",
                        )],
                    },
                }).encode() + b"\n")
                buffer = b""
                while b"\n" not in buffer:
                    data = connection.recv(65536)
                    if not data:
                        raise RuntimeError("Herdr 在订阅确认前断开连接。")
                    buffer += data
                    if len(buffer) > 8 * 1024 * 1024:
                        raise ValueError("订阅确认数据过大。")
                line, buffer = buffer.split(b"\n", 1)
                acknowledgement = json.loads(line)
                if "error" in acknowledgement:
                    raise RuntimeError(str(acknowledgement["error"]))
                if settings(env)["renderer"] == "overlay":
                    from .overlay import start
                    presenter = start(env)
                write_state(ready, {"socket": socket_stamp(endpoint), "pid": os.getpid(),
                                    "renderer": settings(env)["renderer"],
                                    "overlay_pid": presenter.pid if presenter is not None else None})
                client = Herdr(env)
                pending = None
                due = 0.0
                next_check = 0.0
                next_delivery = 0.0
                next_snapshot = time.monotonic() + .25
                while True:
                    now = time.monotonic()
                    if now >= next_check:
                        if paused(env) or not settings(env)["enabled"] or not plugin_enabled(endpoint):
                            return
                        if presenter is not None and presenter.poll() is not None:
                            raise RuntimeError("原生浮层进程意外退出，请检查日志并重新 initialize。")
                        next_check = now + 1
                        if log.exists() and log.stat().st_size > 1_000_000:
                            # stdout 以追加模式打开；截断后继续写入，限制本地日志体积。
                            with log.open("w"):
                                pass
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        message = json.loads(line)
                        if message.get("event", "").replace(".", "_") in (
                            "layout_updated", "pane_updated", "workspace_focused", "tab_focused", "pane_focused",
                        ):
                            pending = message
                            if not due:
                                due = time.monotonic() + settings(env)["settle_ms"] / 1000
                    now = time.monotonic()
                    if pending is not None and now >= due:
                        event_env = dict(env, HERDR_PLUGIN_EVENT_JSON=json.dumps(pending))
                        options = settings(env)
                        # 已在订阅循环内合并过事件，不再二次延迟。
                        options["settle_ms"] = 0
                        run_hook("event", event_env, options, client)
                        pending, due = None, 0.0
                    now = time.monotonic()
                    if now >= next_snapshot:
                        # 0.9.0 的客户端键盘焦点切换不发插件/订阅事件。
                        # 定期核对实际快照，覆盖 Space、标签页和窗格切换。
                        run_hook("poll", env, settings(env), client)
                        next_snapshot = time.monotonic() + .25
                    if now >= next_delivery:
                        run_hook("flush", env, settings(env), client)
                        next_delivery = now + .1
                    timeout = max(0, min(next_check - time.monotonic(), next_delivery - time.monotonic(),
                                         next_snapshot - time.monotonic(),
                                         due - time.monotonic() if due else 1))
                    readable, _, _ = select.select([connection], [], [], timeout)
                    if readable:
                        data = connection.recv(65536)
                        if not data:
                            return
                        buffer += data
                        if len(buffer) > 8 * 1024 * 1024:
                            raise ValueError("Herdr 事件帧过大。")
        except (ConnectionError, FileNotFoundError):
            return  # 会话退出后正常结束；后续事件钩子会按需重新建立订阅。
        finally:
            from .overlay import clear
            clear(env)
            if presenter is not None and presenter.poll() is None:
                presenter.terminate()
                try:
                    presenter.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    presenter.kill()
                    presenter.wait()
            ready.unlink(missing_ok=True)
