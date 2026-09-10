"""只比较布局与焦点；一次操作产生的多个事件归并为一个等效动作。"""
from __future__ import annotations


def compact(snapshot: dict) -> dict:
    """不保存终端正文、命令行、工作目录或 agent 信息。"""
    return {
        "focused_workspace_id": snapshot.get("focused_workspace_id"),
        "focused_tab_id": snapshot.get("focused_tab_id"),
        "focused_pane_id": snapshot.get("focused_pane_id"),
        "workspaces": [{k: item.get(k) for k in ("workspace_id", "label")} for item in snapshot.get("workspaces", [])],
        "tabs": [{k: item.get(k) for k in ("tab_id", "workspace_id", "label", "number")} for item in snapshot.get("tabs", [])],
        "panes": [{k: item.get(k) for k in ("pane_id", "workspace_id", "tab_id", "label")} for item in snapshot.get("panes", [])],
        "layouts": [{k: item.get(k) for k in ("tab_id", "workspace_id", "zoomed", "area", "panes", "splits")} for item in snapshot.get("layouts", [])],
    }


def index_by(items: list[dict], key: str) -> dict:
    return {item[key]: item for item in items}


def split_action(before: dict, after: dict, pane_id: str) -> str | None:
    previous = index_by(before.get("panes") or [], "pane_id")
    current = index_by(after.get("panes") or [], "pane_id")
    target = current.get(pane_id, {}).get("rect")
    if not target:
        return None
    # 新窗格与被拆分窗格应共同位于原来的矩形中。
    tx, ty = target["x"] + target["width"] / 2, target["y"] + target["height"] / 2
    for source_id, source in previous.items():
        old = source["rect"]
        if not (old["x"] <= tx < old["x"] + old["width"] and old["y"] <= ty < old["y"] + old["height"]):
            continue
        new = current.get(source_id, {}).get("rect")
        if not new:
            continue
        if target["x"] >= new["x"] + new["width"]:
            return "split_vertical"
        if target["y"] >= new["y"] + new["height"]:
            return "split_horizontal"
    return None


def neighbor_action(layout: dict, old_id: str, new_id: str) -> str | None:
    panes = index_by(layout.get("panes") or [], "pane_id")
    if old_id not in panes or new_id not in panes:
        return None
    origin = panes[old_id]["rect"]
    nearest: dict[str, tuple[float, str]] = {}
    for pane_id, pane in panes.items():
        if pane_id == old_id:
            continue
        rect = pane["rect"]
        overlaps_y = max(origin["y"], rect["y"]) < min(origin["y"] + origin["height"], rect["y"] + rect["height"])
        overlaps_x = max(origin["x"], rect["x"]) < min(origin["x"] + origin["width"], rect["x"] + rect["width"])
        directions = []
        if overlaps_y and rect["x"] >= origin["x"] + origin["width"]:
            directions.append(("right", rect["x"] - origin["x"] - origin["width"]))
        if overlaps_y and rect["x"] + rect["width"] <= origin["x"]:
            directions.append(("left", origin["x"] - rect["x"] - rect["width"]))
        if overlaps_x and rect["y"] >= origin["y"] + origin["height"]:
            directions.append(("down", rect["y"] - origin["y"] - origin["height"]))
        if overlaps_x and rect["y"] + rect["height"] <= origin["y"]:
            directions.append(("up", origin["y"] - rect["y"] - rect["height"]))
        for direction, distance in directions:
            # 距离相同时不猜测 Herdr 会选择哪个候选窗格。
            if direction not in nearest or distance < nearest[direction][0]:
                nearest[direction] = (distance, pane_id)
            elif distance == nearest[direction][0]:
                nearest[direction] = (distance, "")
    for direction, (_, pane_id) in nearest.items():
        if pane_id == new_id:
            return "focus_pane_" + direction
    return None


def infer(before: dict | None, after: dict, event: dict | None = None) -> list[tuple[str, int | None]]:
    """返回按优先级排列的等效动作；无法确定时不提示。"""
    workspace = after.get("focused_workspace_id")
    tab_id = after.get("focused_tab_id")
    pane_id = after.get("focused_pane_id")
    if before is None:
        # 新安装插件没有旧布局时，只处理无需历史即可判断的创建事件。
        data = (event or {}).get("data", {})
        kind = (event or {}).get("event", "").replace(".", "_")
        if kind == "tab_created" and data.get("tab", {}).get("tab_id") == tab_id:
            return [("new_tab", None)]
        if kind == "workspace_created" and data.get("workspace", {}).get("workspace_id") == workspace:
            return [("new_workspace", None)]
        return []

    old_ws = index_by(before["workspaces"], "workspace_id")
    new_ws = index_by(after["workspaces"], "workspace_id")
    old_tabs = index_by(before["tabs"], "tab_id")
    new_tabs = index_by(after["tabs"], "tab_id")
    old_panes = index_by(before["panes"], "pane_id")
    new_panes = index_by(after["panes"], "pane_id")
    old_tab_id, old_pane_id = before.get("focused_tab_id"), before.get("focused_pane_id")
    old_workspace = before.get("focused_workspace_id")

    if workspace in new_ws.keys() - old_ws.keys():
        return [("new_workspace", None)]
    if old_workspace in old_ws.keys() - new_ws.keys():
        return [("close_workspace", None)]
    if tab_id in new_tabs.keys() - old_tabs.keys():
        return [("new_tab", None)]
    if old_tab_id in old_tabs.keys() - new_tabs.keys():
        return [("close_tab", None)]

    old_layouts = index_by(before["layouts"], "tab_id")
    new_layouts = index_by(after["layouts"], "tab_id")
    old_layout, new_layout = old_layouts.get(tab_id), new_layouts.get(tab_id)
    added = [pid for pid in new_panes.keys() - old_panes.keys() if new_panes[pid]["tab_id"] == tab_id]
    removed = [pid for pid in old_panes.keys() - new_panes.keys() if old_panes[pid]["tab_id"] == tab_id]
    if len(added) == 1 and old_layout and new_layout:
        action = split_action(old_layout, new_layout, added[0])
        return [(action, None)] if action else []
    if removed and tab_id == old_tab_id:
        return [("close_pane", None)]
    if old_workspace != workspace:
        workspaces = list(new_ws)
        if old_workspace in workspaces and workspace in workspaces:
            old_index, new_index = workspaces.index(old_workspace), workspaces.index(workspace)
            options = [("switch_workspace", new_index + 1)]
            if new_index == (old_index + 1) % len(workspaces):
                options.append(("next_workspace", None))
            if new_index == (old_index - 1) % len(workspaces):
                options.append(("previous_workspace", None))
            return options
        return []
    if old_tab_id != tab_id:
        tabs = [item for item in after["tabs"] if item["workspace_id"] == workspace]
        ids = [item["tab_id"] for item in tabs]
        if tab_id not in ids:
            return []
        new_index = ids.index(tab_id)
        # 优先提示目标标签页的序号，最后一个标签页的快捷键仅作备选。
        options = [("switch_tab", new_index + 1)]
        if new_index == len(ids) - 1:
            options.append(("last_tab", None))
        if old_tab_id in ids:
            old_index = ids.index(old_tab_id)
            if new_index == (old_index + 1) % len(ids):
                options.append(("next_tab", None))
            if new_index == (old_index - 1) % len(ids):
                options.append(("previous_tab", None))
        return options
    if old_layout and new_layout and old_layout["zoomed"] != new_layout["zoomed"]:
        return [("zoom", None)]
    if old_pane_id != pane_id and new_layout and not new_layout.get("zoomed"):
        action = neighbor_action(new_layout, old_pane_id, pane_id)
        return [(action, None)] if action else []
    for old, new, selected, field, action in (
        (old_ws, new_ws, workspace, "label", "rename_workspace"),
        (old_tabs, new_tabs, tab_id, "label", "rename_tab"),
        (old_panes, new_panes, pane_id, "label", "rename_pane"),
    ):
        if selected in old and selected in new and old[selected].get(field) != new[selected].get(field):
            return [(action, None)]
    return []
