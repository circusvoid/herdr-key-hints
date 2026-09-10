"""原生浮层即时更新最近动作；Herdr 通知保留兼容队列。"""
from __future__ import annotations

import re


def display_chord(chord: str, count: int = 1) -> str:
    # 分开修饰键和主键，保留前缀键的两步关系，不增加说明文案。
    title = re.sub(r'([⌃⌥⇧⌘])', r'\1 ', chord).strip()
    return title + (f'  ×{count}' if count > 1 else '')


def enqueue(state: dict, picked: tuple[str, str], now: float, options: dict) -> str:
    if options.get('renderer') == 'overlay':
        history = state.setdefault('history', [])
        history[:] = [item for item in history if now < item['expires']]
        action, chord = picked
        expires = now + (options.get('hold_ms', 2000) + options.get('fade_ms', 200)) / 1000
        if history and history[-1]['chord'] == chord and history[-1]['action'] == action:
            history[-1].update(count=history[-1]['count'] + 1, updated=now, expires=expires)
            result = 'merged'
        else:
            serial = state.get('serial', 0) + 1
            state['serial'] = serial
            history.append(dict(id=serial, action=action, chord=chord, count=1,
                                updated=now, expires=expires))
            result = 'queued'
        history[:] = history[-options.get('max_visible', 3):]
        state['dirty'] = True
        return result
    queue = state.setdefault('pending', [])
    action, chord = picked
    active = state.get('active')
    if active and active['chord'] == chord and now < state.get('next_at', 0):
        active['count'] += 1
        return 'merged'
    for item in queue:
        if item['chord'] == chord:
            item['count'] += 1
            return 'merged'
    if len(queue) >= options.get('max_pending', 8):
        queue.pop(0)  # 长时间积压时保留较新的操作，避免提示落后太久。
    queue.append(dict(action=action, chord=chord, count=1, created=now))
    return 'queued'


def deliver(state: dict, client, now: float, options: dict) -> dict | None:
    if options.get('renderer') == 'overlay':
        if not state.pop('dirty', False):
            return None
        history = state.setdefault('history', [])
        history[:] = [item for item in history if now < item['expires']]
        result = client.present(history, options, now)
        item = history[-1] if history else {}
        return dict(action=item.get('action'), shortcut=item.get('chord'),
                    count=item.get('count', 0), notification=result)
    queue = state.setdefault('pending', [])
    max_age = options.get('max_age_ms', 30000) / 1000
    queue[:] = [item for item in queue if 0 <= now - item['created'] < max_age]
    if now < state.get('next_at', 0) or not queue:
        return None
    item = queue[0]
    result = client.notify(display_chord(item['chord'], item['count']), options['position'])
    reason = result.get('reason')
    if result.get('shown'):
        queue.pop(0)
        state['active'] = item
        state['next_at'] = now + options.get('display_ms', 3200) / 1000
    elif reason in ('rate_limited', 'busy'):
        state.pop('active', None)
        state['next_at'] = now + options.get('retry_ms', 500) / 1000
    else:
        # 没有前台或通知已关闭时丢弃积压，重新附着后不回放旧操作。
        queue.clear()
        state.pop('active', None)
        state['next_at'] = 0
    return dict(action=item['action'], shortcut=item['chord'], count=item['count'], notification=result)
