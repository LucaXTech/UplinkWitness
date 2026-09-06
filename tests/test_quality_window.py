import unittest

import monitor


class QualityWindowTests(unittest.TestCase):
    def test_quality_window_uses_every_live_probe(self):
        loss, jitter = monitor.quality_window_stats(
            [
                (1.0, 1, 10.0),
                (2.0, 1, 14.0),
                (3.0, 0, None),
                (4.0, 1, 12.0),
            ]
        )
        self.assertEqual(loss, 25.0)
        self.assertEqual(jitter, 4.0)

    def test_quality_window_averages_adjacent_successful_deltas(self):
        loss, jitter = monitor.quality_window_stats(
            [
                (1.0, 1, 10.0),
                (2.0, 1, 14.0),
                (3.0, 1, 12.0),
            ]
        )
        self.assertEqual(loss, 0.0)
        self.assertEqual(jitter, 3.0)

    def test_quality_window_handles_empty_and_all_failed(self):
        self.assertEqual(monitor.quality_window_stats([]), (None, None))
        self.assertEqual(
            monitor.quality_window_stats([(1.0, 0, None), (2.0, 0, None)]),
            (100.0, None),
        )


if __name__ == "__main__":
    unittest.main()
