"""读取 Herdr 原生配置并选择、格式化等效快捷键。"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Iterable


MODIFIERS = {"command": "cmd", "super": "cmd", "control": "ctrl", "option": "alt", "opt": "alt"}
SYMBOLS = {"cmd": "⌘", "ctrl": "⌃", "alt": "⌥", "shift": "⇧"}
KEY_NAMES = {
    "enter": "Enter", "return": "Enter", "tab": "Tab", "esc": "Esc",
    "escape": "Esc", "space": "Space", "backspace": "⌫", "delete": "Delete",
    "left": "←", "right": "→", "up": "↑", "down": "↓",
    "minus": "-", "comma": ",", "period": ".", "plus": "+",
    "ampersand": "&", "backtick": "`", "slash": "/", "backslash": "\\",
    "semicolon": ";", "quote": "'", "equals": "=",
}


def read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as stream:
        return tomllib.load(stream)


def parse_defaults(text: str) -> dict:
    """从当前 Herdr 二进制的 --default-config 获取默认值，避免写死键位。"""
    result = {}
    in_keys = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_keys = stripped == "[keys]"
            continue
        if not in_keys:
            continue
        candidate = stripped.removeprefix("#").strip()
        if re.match(r'^\w+\s*=\s*("|\[)', candidate):
            try:
                result.update(tomllib.loads(candidate))
            except tomllib.TOMLDecodeError:
                continue
    if "prefix" not in result or "new_tab" not in result:
        raise ValueError("无法从 herdr --default-config 读取默认快捷键。")
    return result


def chords(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return [item for item in value if item.strip()]
    raise ValueError("快捷键必须是字符串或字符串数组。")


def normalize(chord: str) -> str:
    parts = chord.strip().split("+")
    # Herdr 接受大写字母作为 Shift 简写。
    key = parts[-1]
    mods = [MODIFIERS.get(p.lower(), p.lower()) for p in parts[:-1]]
    if len(key) == 1 and key.isupper() and "shift" not in mods:
        mods.append("shift")
    return "+".join(sorted(set(mods)) + [key.lower()])


def format_chord(chord: str, prefix: str) -> str:
    if chord.lower().startswith("prefix+"):
        return format_chord(prefix, "") + " → " + format_chord(chord[7:], "")
    parts = normalize(chord).split("+")
    mods, key = set(parts[:-1]), parts[-1]
    symbols = "".join(SYMBOLS[m] for m in ("ctrl", "alt", "shift", "cmd") if m in mods)
    return symbols + KEY_NAMES.get(key, key.upper())


def preference(chord: str) -> int:
    parts = normalize(chord).split("+")
    if "prefix" in parts[:-1]:
        return 3
    if "cmd" in parts[:-1]:
        return 0
    if "ctrl" in parts[:-1]:
        return 1
    return 2


class Keymap:
    def __init__(self, defaults: dict, config: dict, custom_actions: dict | None = None):
        self.keys = dict(defaults)
        configured = config.get("keys", {})
        if not isinstance(configured, dict):
            raise ValueError("Herdr 配置中的 keys 必须是表。")
        self.keys.update(configured)
        self.prefix = self.keys.get("prefix", "ctrl+b")
        if not isinstance(self.prefix, str) or not self.prefix:
            raise ValueError("Herdr 前缀键无效。")
        self.custom_actions = custom_actions or {}
        # 自定义命令没有统一业务语义，只有用户显式声明时才使用。
        self.command_keys = {
            normalize(item["key"])
            for item in configured.get("command", [])
            if isinstance(item, dict) and isinstance(item.get("key"), str)
        }

    def resolve(self, action: str, index: int | None = None) -> str | None:
        if action == "last_tab":
            value = self.custom_actions.get("last_tab")
            if not isinstance(value, str) or normalize(value) not in self.command_keys:
                return None
            return format_chord(value, self.prefix)
        options = chords(self.keys.get(action, ""))
        if index is not None:
            expanded = []
            if not 1 <= index <= 9:
                return None
            for option in options:
                key = option.rsplit("+", 1)[-1]
                if key == "1..9":
                    expanded.append(option[:-4] + str(index))
                elif key == str(index):
                    expanded.append(option)
            options = expanded
        if not options:
            return None
        return format_chord(min(options, key=preference), self.prefix)

    def choose(self, candidates: Iterable[tuple[str, int | None]]) -> tuple[str, str] | None:
        for action, index in candidates:
            label = self.resolve(action, index)
            if label:
                return action, label
        return None
