"""Herdr 清单命令入口；短生命周期事件钩子，共享状态由文件锁保护。"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .bindings import Keymap, parse_defaults, read_toml
from .inference import compact, infer
from .delivery import enqueue, deliver


PLUGIN_ID = "local.key-hints"
POSITIONS = {"top-left", "top-right", "bottom-left", "bottom-right", "bottom-center", "top-center"}


class Herdr:
    def __init__(self, env: dict[str, str]):
        self.env = env
        self.binary = env.get("HERDR_BIN_PATH") or shutil.which("herdr")
        if not self.binary:
            raise ValueError("找不到 Herdr；请设置 PATH 或 HERDR_BIN_PATH。")

    def call(self, *args: str, json_output: bool = True):
        completed = subprocess.run(
            [self.binary, *args], env=self.env, capture_output=True, text=True, timeout=5,
        )
        if completed.returncode:
            raise RuntimeError(f"Herdr 命令失败（{' '.join(args[:3])}）：{completed.stderr.strip()[:600]}")
        return json.loads(completed.stdout) if json_output else completed.stdout

    def defaults(self) -> dict:
        return parse_defaults(self.call("--default-config", json_output=False))

    def snapshot(self) -> dict:
        return compact(self.call("api", "snapshot")["result"]["snapshot"])

    def present(self, entries: list[dict], options: dict, now: float) -> dict:
        from .overlay import publish
        return publish(self.env, entries, options, now)

    def notify(self, chord: str, position: str) -> dict:
        return self.call("notification", "show", chord, "--position", position, "--sound", "none")["result"]


def settings(env: dict[str, str]) -> dict:
    directory = env.get("HERDR_PLUGIN_CONFIG_DIR")
    values = read_toml(Path(directory) / "config.toml") if directory else {}
    for name in ("enabled",):
        if name in values and not isinstance(values[name], bool):
            raise ValueError(f"插件配置 {name} 必须是布尔值。")
    values.setdefault("enabled", True)
    renderer = values.setdefault("renderer", "auto")
    if renderer not in ("auto", "overlay", "herdr"):
        raise ValueError("renderer 必须是 auto、overlay 或 herdr。")
    if renderer == "auto":
        values["renderer"] = "overlay" if sys.platform == "darwin" else "herdr"
    if values["renderer"] == "overlay" and sys.platform != "darwin":
        raise ValueError("overlay 显示需要 macOS。")
    values.setdefault("position", "bottom-right")
    apps = values.setdefault("terminal_apps", ["com.mitchellh.ghostty", "com.apple.Terminal",
                            "com.googlecode.iterm2", "com.github.wez.wezterm", "net.kovidgoyal.kitty",
                            "org.alacritty", "dev.warp.Warp-Stable"])
    if not isinstance(apps, list) or not apps or any(not isinstance(x, str) or not x for x in apps):
        raise ValueError("terminal_apps 必须是非空的终端 bundle ID 字符串数组。")
    values.setdefault("settle_ms", 100)
    if values["position"] not in POSITIONS:
        raise ValueError("position 必须是 top/bottom 与 left/center/right 的组合。")
    if values["renderer"] == "herdr" and values["position"].endswith("center"):
        raise ValueError("Herdr 通知不支持 center 位置，请选择四角之一。")
    delay = values["settle_ms"]
    if isinstance(delay, bool) or not isinstance(delay, int) or not 0 <= delay <= 500:
        raise ValueError("settle_ms 必须是 0–500 之间的整数。")
    for name, default, minimum, maximum in (
        ("hold_ms", 2000, 500, 10000), ("fade_ms", 200, 0, 1000), ("max_visible", 3, 1, 5),
        ("display_ms", 3200, 500, 10000), ("retry_ms", 500, 100, 5000),
        ("max_age_ms", 30000, 1000, 120000), ("max_pending", 8, 1, 32),
    ):
        value = values.setdefault(name, default)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} 必须是 {minimum}–{maximum} 之间的整数。")
    custom = values.get("custom_actions", {})
    if not isinstance(custom, dict) or any(key != "last_tab" for key in custom):
        raise ValueError("custom_actions 当前只支持 last_tab。")
    return values


def config_path(env: dict[str, str], options: dict) -> Path:
    override = options.get("herdr_config") or env.get("HERDR_CONFIG_PATH")
    if override:
        if not isinstance(override, str):
            raise ValueError("herdr_config 必须是路径字符串。")
        return Path(override).expanduser()
    return Path(env.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "herdr" / "config.toml"


def binary_stamp(binary: str) -> list:
    path = Path(binary).resolve()
    info = path.stat()
    return [str(path), info.st_size, info.st_mtime_ns]


def socket_stamp(socket_path: str) -> list:
    info = Path(socket_path).stat()
    return [socket_path, info.st_ino, info.st_mtime_ns]


@contextmanager
def state_lock(path: Path, timeout: float = 4):
    with path.open("a+") as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待事件合并锁超时。")
                time.sleep(0.02)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        if isinstance(value, dict) and value.get("version") == 1:
            return value
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}


def write_state(path: Path, value: dict) -> None:
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as stream:
            name = stream.name
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def output(**fields) -> None:
    # Herdr 插件日志可直接查看实际选择的动作、按键和通知结果。
    print(json.dumps(fields, ensure_ascii=False))


def run_hook(mode: str, env: dict[str, str], options: dict, client: Herdr) -> None:
    started = time.monotonic()
    socket_path = env.get("HERDR_SOCKET_PATH")
    state_dir = env.get("HERDR_PLUGIN_STATE_DIR")
    if not socket_path or not state_dir:
        raise ValueError("缺少 Herdr 插件上下文；请通过 herdr plugin action invoke 或原生事件钩子运行。")
    if not options["enabled"]:
        output(status="disabled")
        return
    directory = Path(state_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    session_key = hashlib.sha256(socket_path.encode()).hexdigest()[:24]
    path = directory / (session_key + ".json")
    event = {}
    if mode == "event":
        raw_event = env.get("HERDR_PLUGIN_EVENT_JSON", "{}")
        if len(raw_event) > 1_000_000:
            raise ValueError("事件数据过大。")
        event = json.loads(raw_event)
        if not isinstance(event, dict):
            raise ValueError("事件数据必须是 JSON 对象。")
    with state_lock(directory / (session_key + ".lock")):
        stored = read_state(path)
        stamp = socket_stamp(socket_path)
        if stored.get("socket") != stamp:
            stored = {}
        if mode == "flush":
            delivery = stored.get("delivery", {})
            if options.get("renderer") == "overlay":
                return  # 浮层自行按绝对截止时间淡出，不轮询回放历史帧。
            if not delivery.get("pending") or time.monotonic() < delivery.get("next_at", 0):
                return
            result = deliver(delivery, client, time.monotonic(), options)
            write_state(path, stored)
            if result:
                output(**result)
            return
        executable = binary_stamp(client.binary)
        defaults = stored.get("defaults") if stored.get("binary") == executable else None
        if not defaults:
            defaults = client.defaults()
        herdr_config = read_toml(config_path(env, options))
        keymap = Keymap(defaults, herdr_config, options.get("custom_actions"))
        if mode == "event":
            # 已在锁外等待过的钩子不再额外休眠，避免一批事件逐个累积延迟。
            remaining = options["settle_ms"] / 1000 - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
        current = client.snapshot()
        previous = stored.get("snapshot")
        if mode in ("poll", "event") and previous == current:
            return
        if mode == "initialize":
            candidates = []
        elif mode == "preview":
            candidates = [("new_tab", None)]
        else:
            candidates = infer(previous, current, event)
        picked = keymap.choose(candidates)
        renderer = options.get("renderer", "herdr")
        delivery = {} if mode == "initialize" or stored.get("renderer") != renderer else stored.get("delivery", {})
        stored = {"renderer": renderer, "delivery": delivery, "version": 1, "socket": stamp, "binary": executable, "defaults": defaults, "snapshot": current}
        # 先保存快照与待发提示；通知限流不再丢失已识别的操作。
        if picked:
            queued = enqueue(delivery, picked, time.monotonic(), options)
            output(status=queued, action=picked[0], queued_shortcut=picked[1])
        write_state(path, stored)
        if mode == "initialize":
            from .overlay import clear
            clear(env)
            output(status="initialized")
        else:
            result = deliver(delivery, client, time.monotonic(), options)
            write_state(path, stored)
            if result:
                output(**result)



def doctor(env: dict[str, str], options: dict, client: Herdr) -> None:
    from .checks import check_environment
    environment = check_environment(client, options["renderer"])
    path = config_path(env, options)
    config = read_toml(path)
    keymap = Keymap(client.defaults(), config, options.get("custom_actions"))
    ui = config.get("ui", {})
    delivery = ui.get("toast", {}).get("delivery", "off")
    output(
        status="ok", environment=environment, herdr_config=str(path), renderer=options["renderer"], notification_delivery=delivery,
        shortcuts={action: keymap.resolve(action) for action in ("new_tab", "split_vertical", "split_horizontal", "zoom", "close_pane")},
        note="通知需要设置 [ui.toast] delivery = \"herdr\" 并重载 Herdr 配置。" if options["renderer"] == "herdr" and delivery != "herdr" else "",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Herdr 操作后快捷键提示插件")
    parser.add_argument("command", choices=("event", "initialize", "preview", "doctor", "watch", "stop", "status", "prepare"))
    parser.add_argument("--renderer", choices=("overlay", "herdr"), help="仅用于 prepare/doctor 的后端选择")
    args = parser.parse_args(argv)
    try:
        env = dict(os.environ)
        options = settings(env)
        if args.renderer:
            if args.command not in ("prepare", "doctor"):
                raise ValueError("--renderer 只适用于 prepare 或 doctor。")
            options["renderer"] = args.renderer
        client = Herdr(env)
        if args.command == "prepare":
            from .checks import check_environment
            environment = check_environment(client, options["renderer"])
            if options["renderer"] == "overlay":
                from .overlay import prepare
                environment["native_binary"] = str(prepare())
            output(status="prepared", **environment)
        elif args.command == "doctor":
            doctor(env, options, client)
        else:
            from . import watcher
            if args.command == "watch":
                watcher.watch(env)
            elif args.command == "stop":
                watcher.stop(env)
            elif args.command == "status":
                watcher.status(env)
            elif args.command == "initialize":
                run_hook("initialize", env, options, client)
                watcher.ensure_running(env, resume=True)
            elif not watcher.paused(env):
                if options["enabled"]:
                    watcher.ensure_running(env)
                run_hook(args.command, env, options, client)
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"快捷键提示：{error}", file=sys.stderr)
        return 1
