"""连续操作必须即时呈现，且保留实际发生顺序。"""
import unittest
from test_delivery import DeliveryFixture


class OverlayDeliveryTests(DeliveryFixture, unittest.TestCase):
    # 复用运行时夹具，不继承旧通知后端的行为断言。
    def setUp(self):
        super().setUp()
        self.options.update(renderer='overlay', hold_ms=1600, fade_ms=200, max_visible=3)
        self.frames = []
        self.client.present = lambda entries, options, now: self.frames.append(
            [dict(item) for item in entries]) or {'shown': True, 'reason': 'shown'}

    def test_native_burst_is_immediate(self):
        self.run_mode('preview')
        self.now += .2
        self.client.current['focused_workspace_id'] = 'w2'
        self.run_mode('event')
        self.now += .2
        self.client.current['focused_workspace_id'] = 'w1'
        self.run_mode('event')
        self.assertEqual([[item['chord'] for item in f] for f in self.frames],
                         [['⌃B → C'], ['⌃B → C', '⌃2'], ['⌃B → C', '⌃2', '⌃1']])

    def test_native_only_consecutive_duplicates_merge(self):
        for focus in ['w2', 'w1', 'w2']:
            self.client.current['focused_workspace_id'] = focus
            self.run_mode('event')
            self.now += .2
        self.assertEqual([i['chord'] for i in self.frames[-1]], ['⌃2', '⌃1', '⌃2'])
        self.run_mode('preview')
        self.now += .2
        self.run_mode('preview')
        self.assertEqual(self.frames[-1][-1]['count'], 2)
        self.assertEqual(len(self.frames[-1]), 3)

    def test_native_expired_history_never_replays(self):
        self.run_mode('preview')
        self.now += 2
        self.client.current['focused_workspace_id'] = 'w2'
        self.run_mode('event')
        self.assertEqual([i['chord'] for i in self.frames[-1]], ['⌃2'])

    def test_native_repeat_renews_expiry(self):
        self.run_mode('preview')
        self.now += 1
        self.run_mode('preview')
        self.assertAlmostEqual(self.frames[-1][-1]['expires'], 102.8)


if __name__ == '__main__':
    unittest.main()
