# Herdr Key Hints

**[English](README.md)** | [中文](README.zh-CN.md)

Learn your current keybindings by showing the matching shortcut after an action in Herdr. Supports common workspace, tab, and pane actions, whether triggered by mouse, keyboard, or CLI.

![Key hints preview](docs/assets/key-hints-preview.png)

On macOS, a native overlay shows up to three recent hints. Each stays for 2 seconds before fading out; consecutive repeats show `×N`. The overlay is silent, does not take focus, and lets mouse clicks pass through. Linux uses Herdr notifications.

## Install

Requires Herdr ≥ 0.9.0, Python ≥ 3.11, and Git. The first macOS installation also requires the Swift compiler from Xcode Command Line Tools. The Python code uses only the standard library.

Once you trust this repository, run:

```sh
herdr plugin install circusvoid/herdr-key-hints --ref v0.1.0 --yes
herdr plugin action invoke local.key-hints.initialize
herdr plugin action invoke local.key-hints.preview
```

Installation checks dependencies and compiles the macOS overlay automatically. Missing dependencies abort installation. `preview` shows the current shortcut for creating a tab; the native overlay appears only when a supported terminal app is in the foreground. Newly started Herdr servers initialize the plugin automatically.

The plugin ID is `local.key-hints`; it supports installation from GitHub. See the [compatibility notes](docs/compatibility.md) (Chinese) for tested platforms.

## Configure

Run `herdr plugin config-dir local.key-hints` and create `config.toml` in the directory it prints:

```toml
enabled = true
renderer = "auto"
position = "bottom-right"
max_visible = 3
hold_ms = 2000
fade_ms = 200
```

`auto` uses the native overlay on macOS and Herdr notifications on Linux. The overlay supports all four corners plus top and bottom center, on the screen containing the mouse pointer. `max_visible` accepts 1–5. See the [full configuration example](config.example.toml) (Chinese comments) for terminal apps, custom Herdr configuration paths, and other options. Optional Ghostty keybindings are available in [.config](.config/README.md).

On Linux or a remote SSH host, use `renderer = "herdr"` and set this in your Herdr configuration:

```toml
[ui.toast]
delivery = "herdr"
```

If `[ui.toast]` already exists, edit that table, then run `herdr server reload-config`. Notification mode supports only the four corners and is subject to Herdr's notification rate limits and queue.

After changing `renderer`, run `stop` below. Wait until `status` reports paused and the previous process has exited before running `initialize`. Other display settings are read on subsequent actions. Reload Herdr after changing its keybindings too.

## Pause, update, and uninstall

```sh
herdr plugin action invoke local.key-hints.stop
herdr plugin action invoke local.key-hints.status
# Resume in the current session
herdr plugin action invoke local.key-hints.initialize
```

To update, pause hints and wait for the process to exit, run the install command with the desired version, then run `initialize`. To uninstall:

```sh
herdr plugin disable local.key-hints
herdr plugin uninstall local.key-hints
```

For a locally linked copy, use `herdr plugin unlink local.key-hints`; this keeps the source files. Before switching from a local link to a GitHub installation, pause and unlink the plugin. Configuration and state live in separate directories provided by Herdr.

## Limitations

- Hints show an equivalent shortcut from your current configuration, not necessarily the keys you pressed. Explicitly disabled bindings do not fall back to defaults.
- Supported actions include creating, closing, switching, and renaming workspaces and tabs; splitting, closing, and renaming panes; toggling pane zoom; and switching to an adjacent pane when the destination can be inferred unambiguously.
- Complex layout changes may not be recognized, and rapid actions may be merged. Split ratios, pane swaps, the sidebar, copy and paste, and the terminal app's own actions are not covered.
- Foreground detection works at the terminal app level and cannot distinguish session windows within that app. SSH does not automatically launch the native overlay on the client.

## Local development

```sh
git clone https://github.com/circusvoid/herdr-key-hints.git
cd herdr-key-hints
python3 plugin.py prepare
python3 plugin.py doctor
herdr plugin link "$PWD" --enabled
herdr plugin action invoke local.key-hints.initialize
```

Local linking does not run the build. Before moving the source directory, pause the plugin; afterward, link it again and run `initialize`. If you only need notifications on macOS, check dependencies with `prepare --renderer herdr`, then select the same renderer in the plugin configuration.

```sh
python3 -m unittest discover -s tests -v
python3 tests/smoke_herdr.py
python3 tests/smoke_overlay.py
python3 tests/smoke_install.py --ref v0.1.0
herdr plugin log list --plugin local.key-hints --limit 20
```

Integration tests use temporary configuration and isolated Herdr sessions. See the [compatibility notes](docs/compatibility.md) (Chinese) for implementation details and validation limits.

## License

[MIT](LICENSE). The visual structure draws inspiration from [Keyviz](https://github.com/mulaRahul/keyviz); hold and fade timings draw inspiration from [KeyCastr](https://github.com/keycastr/keycastr). No source code or images from either project are bundled.
