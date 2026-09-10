-- 通过启动 shell 写入的唯一标题识别窗格，避免新窗口启动时的焦点竞争。
on run argv
    tell application "Ghostty"
        if item 1 of argv is "enter" then
            set marker to item 2 of argv
            repeat 20 times
                repeat with targetTerminal in terminals
                    if name of targetTerminal is marker then
                        set didActivate to perform action "activate_key_table:herdr" on targetTerminal
                        if didActivate then return id of targetTerminal
                        return ""
                    end if
                end repeat
                delay 0.025
            end repeat
            return ""
        else if item 1 of argv is "leave" then
            set terminalID to item 2 of argv
            repeat with targetTerminal in terminals
                if id of targetTerminal is terminalID then
                    perform action "deactivate_key_table" on targetTerminal
                    exit repeat
                end if
            end repeat
        end if
    end tell
end run
