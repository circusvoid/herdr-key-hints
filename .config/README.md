# Ghostty and Herdr configuration examples

**[English](README.md)** | [中文](README.zh-CN.md)

These optional settings forward common Ghostty Cmd shortcuts to Herdr. They were prepared for macOS, Ghostty 1.3.1, and Herdr 0.9.0. You do not need to copy them to install the [key hints plugin](../README.md).

## Setup

Back up your local configuration, then merge or copy the files you need:

| Repository file | Local destination |
| --- | --- |
| `ghostty/config` | `~/Library/Application Support/com.mitchellh.ghostty/config` |
| `herdr/config.toml` | `~/.config/herdr/config.toml` |
| `herdr/ghostty.zsh` | `~/.config/herdr/ghostty.zsh` |
| `herdr/ghostty-key-table.applescript` | `~/.config/herdr/ghostty-key-table.applescript` |
| `herdr/last-tab.py` | `~/.config/herdr/last-tab.py` |
| `herdr/plugins/config/local.key-hints/config.toml` | `config.toml` in the directory printed by `herdr plugin config-dir local.key-hints` |

The Ghostty configuration uses the Catppuccin Macchiato theme and the JetBrains Mono and Symbols Nerd Font Mono fonts. Adjust the fonts to match your system.

Add this to the `~/.zshrc` of the outer zsh shell that launches Herdr:

```zsh
source "$HOME/.config/herdr/ghostty.zsh"
```

The script uses AppleScript to switch the corresponding Ghostty pane's key table when Herdr starts and exits. `last-tab.py` requires Python 3 and locates Herdr through `HERDR_BIN_PATH` or `PATH`.

After making changes, run `herdr config check` and `herdr server reload-config`, then press ⌘⇧, in Ghostty to reload its configuration. If key forwarding is inactive, press Control+Option+Shift+Enter in the target pane. Press Control+Option+Shift+Esc to disable it.

## Shortcuts

| Action | Shortcut |
| --- | --- |
| Switch Space / Tab | ⌘⌥ + 1–9 / ⌘ + 1–8 |
| Switch to the last Tab | ⌘9 |
| Create Space / Tab | ⌘N / ⌘T |
| Split right / down | ⌘D / ⌘⇧D |
| Close current pane / Tab | ⌘W / ⌘⌥W |
| Toggle pane zoom | ⌘Enter |
| Switch to an adjacent pane | ⌘⌥ + arrow key |

The configuration retains Herdr's Control+B prefix shortcuts. Space shortcuts have passed isolated Herdr tests; their behavior in a real Ghostty window still needs validation. Repository files and local settings do not sync automatically.
