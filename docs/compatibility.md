# 兼容性与验收范围

本文件区分实际验证与计划支持，避免将一次本地成功当成跨平台保证。

| 环境或场景 | 状态 |
| --- | --- |
| macOS 15.7.3、Apple Silicon、Herdr 0.9.0 | 已通过本地 Python 回归、Swift 编译和两套隔离集成测试 |
| 新目录和含空格路径 | 已验证本地链接、编译、真实事件交付和进程退出 |
| GitHub 公开安装 | 已禁用 Git 凭据，在独立 XDG 环境通过匿名安装、安装期构建、doctor 与原生生命周期测试 |
| GitHub Actions macOS/Linux | 已通过 macOS 15 / Ubuntu 24.04 的 Python 3.11 回归测试，以及 macOS Swift 编译检查（不包含真实桌面验收） |
| Intel Mac、其他 macOS 版本 | 未完成真实桌面验收 |
| Linux 通知模式 | 有兼容实现；CI 基础测试不等同于真实终端验收 |
| Ghostty 原生浮层外观、动画、多屏 | 已检查同一绘制代码导出的 PNG；未完成真实窗口视觉验收 |
| SSH 远端 | 仅声明支持 Herdr 通知方式，不支持在远端客户端自动启动原生浮层 |

## 实现说明

插件通过标准 Herdr 清单与 CLI/Socket API 工作，自行管理 AppKit 显示程序；Herdr v1 不提供原生 GUI 扩展接口。每个会话最多一个 Python 订阅进程和一个原生子进程，禁用插件或会话断开后清理，原生子进程也会在父进程退出后结束。

配置放在 `HERDR_PLUGIN_CONFIG_DIR`，状态放在 `HERDR_PLUGIN_STATE_DIR`。安装期构建产物位于源码目录的 `.build/`，同架构、同源码时可复用，不提交 Git。插件无需网络服务，不保存终端正文、工作目录或 agent 信息，也不会自动安装系统工具或申请录屏、输入监控、辅助功能权限。

快捷键读取 `herdr --default-config` 与用户配置；优先使用 Cmd 直达键，其次其他直达键，最后前缀键。`⌃B → C` 表示先按 Ctrl+B，再按 C。Herdr 配置路径依次取插件的 `herdr_config`、`HERDR_CONFIG_PATH`、XDG 配置路径或 `~/.config/herdr/config.toml`。

切换标签页时优先提示序号快捷键；若目标是最后一个标签页且没有可用的序号快捷键，再尝试已配置的 `last_tab`，最后尝试前后切换键。

客户端部分焦点切换每 250 毫秒核对一次。原生交付日志的 `reason = "published"` 仅表示帧已写入，不保证当时前台可见。CI 不包含真实桌面验收，自动化检查不能替代窗口和多屏视觉检查。
