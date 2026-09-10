# 仅包装交互式启动；查询、更新等 CLI 命令保持原样。
function herdr() {
  local herdr_launch=0 herdr_terminal_id='' herdr_exit_code=0 herdr_marker=''
  case "${1-}" in
    ''|--session|--remote|--handoff) herdr_launch=1 ;;
    session) [[ "${2-}" == attach ]] && herdr_launch=1 ;;
  esac
  if [[ $herdr_launch == 1 && $TERM_PROGRAM == ghostty && -t 0 && -t 1 && ${HERDR_ENV:-0} != 1 ]]; then
    herdr_marker="herdr-key-table-$$-$RANDOM-$RANDOM"
    printf '\033]2;%s\007' "$herdr_marker" > /dev/tty
    herdr_terminal_id=$(/usr/bin/osascript "$HOME/.config/herdr/ghostty-key-table.applescript" enter "$herdr_marker")
    if [[ -z $herdr_terminal_id ]]; then
      print -u2 'Herdr 快捷键接管未启用：请在当前窗格按 Ctrl+Option+Shift+Enter 恢复；若刚修改过 Ghostty 配置，先按 Cmd+Shift+, 重载，再按恢复键。'
    fi
  fi
  {
    command herdr "$@"
    herdr_exit_code=$?
  } always {
    if [[ -n $herdr_terminal_id ]]; then
      /usr/bin/osascript "$HOME/.config/herdr/ghostty-key-table.applescript" leave "$herdr_terminal_id" >/dev/null 2>&1
    fi
  }
  return $herdr_exit_code
}
