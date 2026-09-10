# Ghostty 与 Herdr 配置示例

这组可选配置将 Ghostty 的常用 Cmd 快捷键传给 Herdr。基于 macOS、Ghostty 1.3.1 和 Herdr 0.9.0 整理；安装[快捷键提示插件](../README.md)无需复制这些文件。

## 使用

先备份本机配置，再按需合并或复制：

| 仓库内文件 | 本机位置 |
| --- | --- |
| `ghostty/config` | `~/Library/Application Support/com.mitchellh.ghostty/config` |
| `herdr/config.toml` | `~/.config/herdr/config.toml` |
| `herdr/ghostty.zsh` | `~/.config/herdr/ghostty.zsh` |
| `herdr/ghostty-key-table.applescript` | `~/.config/herdr/ghostty-key-table.applescript` |
| `herdr/last-tab.py` | `~/.config/herdr/last-tab.py` |
| `herdr/plugins/config/local.key-hints/config.toml` | `herdr plugin config-dir local.key-hints` 输出目录中的 `config.toml` |

Ghostty 配置包含 Catppuccin Macchiato 主题，以及 JetBrains Mono、Symbols Nerd Font Mono 字体设置。可按本机字体调整。

在启动 Herdr 的外层 zsh 的 `~/.zshrc` 中加入：

```zsh
source "$HOME/.config/herdr/ghostty.zsh"
```

该脚本在启动和退出 Herdr 时，通过 AppleScript 切换对应 Ghostty 窗格的按键表。`last-tab.py` 需要 Python 3，并通过 `HERDR_BIN_PATH` 或 `PATH` 查找 Herdr。

修改后执行 `herdr config check` 和 `herdr server reload-config`，在 Ghostty 按 ⌘⇧, 重载配置。若按键接管未启用，在目标窗格按 Control+Option+Shift+Enter；按 Control+Option+Shift+Esc 可退出接管。

## 快捷键

| 操作 | 快捷键 |
| --- | --- |
| 切换 Space / Tab | ⌘⌥ + 1–9 / ⌘ + 1–8 |
| 切换到最后一个 Tab | ⌘9 |
| 新建 Space / Tab | ⌘N / ⌘T |
| 向右 / 向下分屏 | ⌘D / ⌘⇧D |
| 关闭当前窗格 / Tab | ⌘W / ⌘⌥W |
| 放大或还原窗格 | ⌘Enter |
| 切换相邻窗格 | ⌘⌥ + 方向键 |

配置保留 Herdr 的 Control+B 前缀快捷键。Space 组合键已通过 Herdr 隔离测试，Ghostty 真实窗口的按键效果仍待验证。仓库配置与本机配置不会自动同步。
