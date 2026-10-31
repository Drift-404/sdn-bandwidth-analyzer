import unittest
from types import SimpleNamespace

from app.flow_stats import FlowStatsTracker


class TestFlowStatsTracker(unittest.TestCase):

    def setUp(self):
        self.tracker = FlowStatsTracker()

    def make_stat(self, packets, bytes_count):
        return SimpleNamespace(
            table_id=0,
            priority=10,
            match={
                "in_port": 1,
                "eth_dst": "00:00:00:00:00:02",
            },
            packet_count=packets,
            byte_count=bytes_count,
        )

    def test_first_sample_returns_none(self):
        result = self.tracker.update(
            1, self.make_stat(100, 100000), timestamp=10
        )

        self.assertIsNone(result)

    def test_calculates_packet_rate(self):
        self.tracker.update(
            1, self.make_stat(100, 100000), timestamp=10
        )

        result = self.tracker.update(
            1, self.make_stat(225, 350000), timestamp=15
        )

        self.assertEqual(result["packet_delta"], 125)
        self.assertAlmostEqual(result["packet_rate_pps"], 25)

    def test_calculates_throughput(self):
        self.tracker.update(
            1, self.make_stat(100, 100000), timestamp=10
        )

        result = self.tracker.update(
            1, self.make_stat(225, 350000), timestamp=15
        )

        self.assertEqual(result["byte_delta"], 250000)
        self.assertAlmostEqual(result["throughput_bps"], 400000)

    def test_counter_reset(self):
        self.tracker.update(
            1, self.make_stat(100, 100000), timestamp=10
        )

        result = self.tracker.update(
            1, self.make_stat(10, 5000), timestamp=15
        )

        self.assertIsNone(result)

    def test_zero_elapsed_time(self):
        self.tracker.update(
            1, self.make_stat(100, 100000), timestamp=10
        )

        result = self.tracker.update(
            1, self.make_stat(200, 200000), timestamp=10
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
