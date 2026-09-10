"""将 Cmd+9 对齐为当前 Herdr 工作区的最后一个标签页。"""
import json
import os
import subprocess

binary = os.environ.get("HERDR_BIN_PATH", "herdr")
workspace = os.environ.get("HERDR_ACTIVE_WORKSPACE_ID") or os.environ.get("HERDR_WORKSPACE_ID")
if workspace:
    result = subprocess.run([binary, "tab", "list", "--workspace", workspace], check=True, capture_output=True, text=True)
    tabs = json.loads(result.stdout)["result"]["tabs"]
    if tabs:
        subprocess.run([binary, "tab", "focus", tabs[-1]["tab_id"]], check=True, stdout=subprocess.DEVNULL)
