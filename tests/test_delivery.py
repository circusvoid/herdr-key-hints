"""通知失败、合并与排队的运行时回归测试。"""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from key_hints.runtime import run_hook
from key_hints.delivery import display_chord
from test_key_hints import DEFAULTS, initial


class Client:
    binary = sys.executable

    def __init__(self):
        self.current = initial()
        self.current['workspaces'].append({'workspace_id': 'w2', 'label': 'Space 2'})
        self.calls = []
        self.results = []

    def defaults(self):
        return dict(DEFAULTS, switch_workspace='ctrl+1..9')

    def snapshot(self):
        return copy.deepcopy(self.current)

    def notify(self, chord, position):
        self.calls.append(chord)
        return self.results.pop(0) if self.results else {'shown': True, 'reason': 'shown'}


class DeliveryFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'socket').touch()
        self.env = dict(os.environ, HERDR_SOCKET_PATH=str(root / 'socket'),
                        HERDR_PLUGIN_STATE_DIR=str(root), HERDR_CONFIG_PATH=str(root / 'config.toml'))
        self.options = dict(enabled=True, position='bottom-right', settle_ms=0,
                            display_ms=3000, retry_ms=500, max_age_ms=15000, max_pending=8)
        self.client = Client()
        self.now = 100.
        self.clock = patch('key_hints.runtime.time.monotonic', side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.output = patch('key_hints.runtime.output')
        self.output.start()
        self.addCleanup(self.output.stop)
        self.run_mode('initialize')

    def run_mode(self, mode):
        run_hook(mode, self.env, self.options, self.client)


class DeliveryTests(DeliveryFixture, unittest.TestCase):
    def test_rate_limited_space_hint_is_retried_without_new_event(self):
        self.client.results = [{'shown': False, 'reason': 'rate_limited'}]
        self.client.current['focused_workspace_id'] = 'w2'
        self.run_mode('event')
        self.now += .6
        self.run_mode('flush')
        self.assertEqual(len(self.client.calls), 2)
        self.assertIn('2', self.client.calls[-1])

    def test_different_hints_wait_in_fifo_order(self):
        self.run_mode('preview')
        self.client.current['focused_workspace_id'] = 'w2'
        self.run_mode('event')
        self.assertEqual(len(self.client.calls), 1)
        self.now += 3.1
        self.run_mode('flush')
        self.assertEqual(len(self.client.calls), 2)
        self.assertIn('2', self.client.calls[-1])

    def test_repeated_hint_is_merged_while_visible(self):
        self.run_mode('preview')
        self.run_mode('preview')
        self.assertEqual(len(self.client.calls), 1)

    def test_no_foreground_does_not_replay_old_hints(self):
        self.client.results = [{'shown': False, 'reason': 'no_foreground_client'}]
        self.run_mode('preview')
        self.now += 5
        self.run_mode('flush')
        self.assertEqual(len(self.client.calls), 1)

    def test_pending_duplicates_merge_and_keep_other_hints_in_order(self):
        self.run_mode('preview')
        self.client.current['focused_workspace_id'] = 'w2'
        self.run_mode('event')
        self.client.current['focused_workspace_id'] = 'w1'
        self.run_mode('event')
        self.client.current['focused_workspace_id'] = 'w2'
        self.run_mode('event')
        self.now += 3.1
        self.run_mode('flush')
        self.assertEqual(self.client.calls[-1], '⌃ 2  ×2')
        self.now += 3.1
        self.run_mode('flush')
        self.assertEqual(self.client.calls[-1], '⌃ 1')

    def test_poll_detects_focus_change_without_event(self):
        self.client.current['focused_workspace_id'] = 'w2'
        self.run_mode('poll')
        self.assertEqual(self.client.calls, ['⌃ 2'])
        self.run_mode('poll')
        self.assertEqual(len(self.client.calls), 1)

    def test_initialize_clears_pending_hints(self):
        self.client.results = [{'shown': False, 'reason': 'busy'}]
        self.run_mode('preview')
        self.run_mode('initialize')
        self.now += 3
        self.run_mode('flush')
        self.assertEqual(len(self.client.calls), 1)

    def test_queue_limit_keeps_recent_operations(self):
        self.options['max_pending'] = 1
        self.run_mode('preview')
        self.client.current['focused_workspace_id'] = 'w2'
        self.run_mode('event')
        self.client.current['focused_workspace_id'] = 'w1'
        self.run_mode('event')
        self.now += 3.1
        self.run_mode('flush')
        self.assertEqual(self.client.calls[-1], '⌃ 1')
        self.now += 3.1
        self.run_mode('flush')
        self.assertEqual(len(self.client.calls), 2)

    def test_chords_have_consistent_spacing(self):
        self.assertEqual(display_chord('⇧⌘D'), '⇧ ⌘ D')
        self.assertEqual(display_chord('⌃B → ⇧N'), '⌃ B → ⇧ N')

    def test_busy_retry_expires(self):
        self.client.results = [{'shown': False, 'reason': 'busy'}]
        self.run_mode('preview')
        self.now += 16
        self.run_mode('flush')
        self.assertEqual(len(self.client.calls), 1)


if __name__ == '__main__':
    unittest.main()
