"""验证快捷键解析和实际状态变化，不依赖运行中的用户会话。"""
import copy
import unittest

from key_hints.bindings import Keymap, format_chord, parse_defaults
from key_hints.inference import compact, infer, neighbor_action


DEFAULTS = {
    'prefix': 'ctrl+b', 'new_tab': 'prefix+c', 'close_tab': 'prefix+shift+x',
    'split_vertical': 'prefix+v', 'split_horizontal': 'prefix+minus',
    'close_pane': 'prefix+x', 'zoom': 'prefix+z', 'switch_tab': 'prefix+1..9',
    'next_tab': 'prefix+n', 'previous_tab': 'prefix+p',
}


def rect(x=0, y=0, width=100, height=40):
    return dict(x=x, y=y, width=width, height=height)


def initial():
    return compact({
        'focused_workspace_id': 'w1', 'focused_tab_id': 't1', 'focused_pane_id': 'p1',
        'workspaces': [dict(workspace_id='w1', label='工作区')],
        'tabs': [dict(workspace_id='w1', tab_id='t1', label='1', number=1)],
        'panes': [dict(workspace_id='w1', tab_id='t1', pane_id='p1', label=None)],
        'layouts': [dict(workspace_id='w1', tab_id='t1', zoomed=False, area=rect(),
                         panes=[dict(pane_id='p1', rect=rect())], splits=[])],
    })


def split(state, down=False):
    result = copy.deepcopy(state)
    result['panes'].append(dict(workspace_id='w1', tab_id='t1', pane_id='p2', label=None))
    result['focused_pane_id'] = 'p2'
    result['layouts'][0]['panes'] = [
        dict(pane_id='p1', rect=rect(height=20) if down else rect(width=50)),
        dict(pane_id='p2', rect=rect(y=20, height=20) if down else rect(x=50, width=50)),
    ]
    return result


def add_tab(state):
    result = copy.deepcopy(state)
    result['tabs'].append(dict(workspace_id='w1', tab_id='t2', label='2', number=2))
    result['panes'].append(dict(workspace_id='w1', tab_id='t2', pane_id='p3', label=None))
    result['layouts'].append(dict(workspace_id='w1', tab_id='t2', zoomed=False, area=rect(),
                                  panes=[dict(pane_id='p3', rect=rect())], splits=[]))
    result['focused_tab_id'], result['focused_pane_id'] = 't2', 'p3'
    return result


class BindingTests(unittest.TestCase):
    def test_current_binary_defaults_are_parsed_without_other_sections(self):
        defaults = parse_defaults('[keys]\n# prefix = "ctrl+a"\n# new_tab = "prefix+c"\n[ui]\n# name = "ignore"')
        self.assertEqual(defaults, {'prefix': 'ctrl+a', 'new_tab': 'prefix+c'})

    def test_prefer_cmd_alias_and_fallback_to_prefix(self):
        km = Keymap(DEFAULTS, {'keys': {'new_tab': ['prefix+c', 'ctrl+alt+c', 'cmd+t']}})
        self.assertEqual(km.resolve('new_tab'), '⌘T')
        self.assertEqual(km.resolve('zoom'), '⌃B → Z')

    def test_explicitly_disabled_binding_never_falls_back(self):
        self.assertIsNone(Keymap(DEFAULTS, {'keys': {'new_tab': ''}}).resolve('new_tab'))

    def test_index_uses_position_and_never_creates_unsupported_binding(self):
        km = Keymap(DEFAULTS, {'keys': {'switch_tab': ['prefix+1..9', 'cmd+1', 'cmd+2']}})
        self.assertEqual(km.resolve('switch_tab', 2), '⌘2')
        self.assertEqual(km.resolve('switch_tab', 3), '⌃B → 3')
        self.assertIsNone(km.resolve('switch_tab', 10))

    def test_prefix_and_punctuation(self):
        self.assertEqual(format_chord('prefix+shift+minus', 'ctrl+a'), '⌃A → ⇧-')
        self.assertEqual(format_chord('super+option+left', ''), '⌥⌘←')
        self.assertEqual(format_chord('D', ''), '⇧D')

    def test_custom_last_tab_requires_explicit_semantics_and_registered_key(self):
        cfg = {'keys': {'command': [{'key': 'cmd+9', 'command': 'anything'}]}}
        self.assertIsNone(Keymap(DEFAULTS, cfg).resolve('last_tab'))
        self.assertEqual(Keymap(DEFAULTS, cfg, {'last_tab': 'super+9'}).resolve('last_tab'), '⌘9')
        self.assertIsNone(Keymap(DEFAULTS, {}, {'last_tab': 'cmd+9'}).resolve('last_tab'))


class InferenceTests(unittest.TestCase):
    def test_new_tab_absorbs_pane_creation_and_focus_events(self):
        before = initial()
        after = add_tab(before)
        self.assertEqual(infer(before, after), [('new_tab', None)])
        self.assertEqual(infer(after, after, {'event': 'pane_created'}), [])

    def test_split_directions(self):
        before = initial()
        self.assertEqual(infer(before, split(before)), [('split_vertical', None)])
        self.assertEqual(infer(before, split(before, down=True)), [('split_horizontal', None)])

    def test_close_pane_not_focus_hint(self):
        self.assertEqual(infer(split(initial()), initial()), [('close_pane', None)])

    def test_close_tab_not_pane_hint(self):
        self.assertEqual(infer(add_tab(initial()), initial()), [('close_tab', None)])

    def test_toggle_zoom(self):
        before = split(initial())
        after = copy.deepcopy(before)
        after['layouts'][0]['zoomed'] = True
        self.assertEqual(infer(before, after), [('zoom', None)])
        self.assertEqual(infer(after, before), [('zoom', None)])

    def test_focus_tab_offers_index_then_equivalent_navigation(self):
        before = add_tab(initial())
        after = copy.deepcopy(before)
        after['focused_tab_id'], after['focused_pane_id'] = 't1', 'p1'
        self.assertEqual(infer(before, after)[0], ('switch_tab', 1))
        self.assertIn(('previous_tab', None), infer(before, after))

    def test_last_tab_prefers_its_number_when_both_shortcuts_work(self):
        after = add_tab(initial())
        before = copy.deepcopy(after)
        before['focused_tab_id'], before['focused_pane_id'] = 't1', 'p1'
        config = {'keys': {'switch_tab': ['prefix+1..9', 'cmd+1', 'cmd+2'],
                           'command': [{'key': 'cmd+9', 'command': 'last-tab'}]}}
        keymap = Keymap(DEFAULTS, config, {'last_tab': 'cmd+9'})
        self.assertEqual(keymap.resolve('last_tab'), '⌘9')
        self.assertEqual(keymap.choose(infer(before, after)), ('switch_tab', '⌘2'))

    def test_last_tab_falls_back_when_number_binding_is_disabled(self):
        after = add_tab(initial())
        before = copy.deepcopy(after)
        before['focused_tab_id'], before['focused_pane_id'] = 't1', 'p1'
        config = {'keys': {'switch_tab': '',
                           'command': [{'key': 'cmd+9', 'command': 'last-tab'}]}}
        keymap = Keymap(DEFAULTS, config, {'last_tab': 'cmd+9'})
        self.assertEqual(keymap.choose(infer(before, after)), ('last_tab', '⌘9'))

    def test_unregistered_last_tab_uses_equivalent_navigation(self):
        after = add_tab(initial())
        before = copy.deepcopy(after)
        before['focused_tab_id'], before['focused_pane_id'] = 't1', 'p1'
        keymap = Keymap(DEFAULTS, {'keys': {'switch_tab': ''}}, {'last_tab': 'cmd+9'})
        self.assertEqual(keymap.choose(infer(before, after)), ('next_tab', '⌃B → N'))

    def test_focus_neighbor(self):
        before = split(initial())
        after = copy.deepcopy(before)
        after['focused_pane_id'] = 'p1'
        self.assertEqual(infer(before, after), [('focus_pane_left', None)])

    def test_ambiguous_neighbors_are_not_guessed(self):
        layout = {'panes': [dict(pane_id='a', rect=rect(width=50)),
                            dict(pane_id='b', rect=rect(x=50, width=50, height=20)),
                            dict(pane_id='c', rect=rect(x=50, y=20, width=50, height=20))]}
        self.assertIsNone(neighbor_action(layout, 'a', 'b'))

    def test_background_changes_do_not_generate_foreground_hint(self):
        before = add_tab(initial())
        after = copy.deepcopy(before)
        after['tabs'][0]['label'] = '后台重命名'
        self.assertEqual(infer(before, after), [])

    def test_window_resize_is_not_a_pane_resize_operation(self):
        before = initial()
        after = copy.deepcopy(before)
        after['layouts'][0]['area'] = rect(width=120)
        after['layouts'][0]['panes'][0]['rect'] = rect(width=120)
        self.assertEqual(infer(before, after), [])

    def test_no_baseline_only_uses_unambiguous_creation_event(self):
        current = initial()
        self.assertEqual(infer(None, current, {'event': 'tab_created', 'data': {'tab': {'tab_id': 't1'}}}), [('new_tab', None)])
        self.assertEqual(infer(None, current, {'event': 'layout_updated'}), [])

    def test_compact_state_drops_terminal_content_and_cwd(self):
        raw = initial()
        raw['panes'][0].update(cwd='/private', terminal_title='private command', text='secret')
        saved = compact(raw)
        self.assertNotIn('private', str(saved))
        self.assertNotIn('secret', str(saved))


if __name__ == '__main__':
    unittest.main()
