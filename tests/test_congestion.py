
import unittest

from app.congestion import CongestionPolicy


class TestCongestionPolicy(unittest.TestCase):

    def setUp(self):
        self.policy = CongestionPolicy()

    def test_no_activation_below_threshold(self):
        result = self.policy.evaluate(100, timestamp=0)

        self.assertIsNone(result)
        self.assertFalse(self.policy.meter_active)

    def test_requires_consecutive_high_samples(self):
        self.assertIsNone(
            self.policy.evaluate(160, timestamp=0)
        )
        self.assertIsNone(
            self.policy.evaluate(100, timestamp=5)
        )
        self.assertIsNone(
            self.policy.evaluate(160, timestamp=10)
        )

        self.assertEqual(
            self.policy.evaluate(170, timestamp=15),
            "activate",
        )

        self.assertTrue(self.policy.meter_active)

    def test_meter_rate_configuration(self):
        self.assertEqual(
            self.policy.meter_rate_kbps,
            500,
        )

    def test_minimum_hold_time_prevents_early_recovery(self):
        self.policy.evaluate(160, timestamp=0)
        self.policy.evaluate(160, timestamp=5)

        self.assertTrue(self.policy.meter_active)

        # Low samples during the hold period must not deactivate it.
        self.assertIsNone(
            self.policy.evaluate(50, timestamp=10)
        )
        self.assertIsNone(
            self.policy.evaluate(50, timestamp=14)
        )

        self.assertTrue(self.policy.meter_active)

    def test_recovery_after_hold_time(self):
        self.policy.evaluate(160, timestamp=0)
        self.policy.evaluate(160, timestamp=5)

        # Hold period ends at timestamp 20.
        self.assertIsNone(
            self.policy.evaluate(100, timestamp=20)
        )

        self.assertEqual(
            self.policy.evaluate(100, timestamp=25),
            "deactivate",
        )

        self.assertFalse(self.policy.meter_active)

    def test_recovery_requires_consecutive_low_samples(self):
        self.policy.evaluate(160, timestamp=0)
        self.policy.evaluate(160, timestamp=5)

        self.assertIsNone(
            self.policy.evaluate(100, timestamp=20)
        )
        self.assertIsNone(
            self.policy.evaluate(130, timestamp=25)
        )
        self.assertIsNone(
            self.policy.evaluate(100, timestamp=30)
        )

        self.assertEqual(
            self.policy.evaluate(100, timestamp=35),
            "deactivate",
        )

    def test_no_repeated_activation(self):
        self.policy.evaluate(160, timestamp=0)
        self.policy.evaluate(160, timestamp=5)

        self.assertIsNone(
            self.policy.evaluate(200, timestamp=10)
        )

        self.assertTrue(self.policy.meter_active)

    def test_no_repeated_deactivation(self):
        self.policy.evaluate(160, timestamp=0)
        self.policy.evaluate(160, timestamp=5)

        self.policy.evaluate(100, timestamp=20)
        self.assertEqual(
            self.policy.evaluate(100, timestamp=25),
            "deactivate",
        )

        self.assertIsNone(
            self.policy.evaluate(100, timestamp=30)
        )

    def test_invalid_negative_throughput(self):
        with self.assertRaises(ValueError):
            self.policy.evaluate(-10, timestamp=0)

    def test_invalid_threshold_configuration(self):
        with self.assertRaises(ValueError):
            CongestionPolicy(
                high_threshold_kbps=100,
                low_threshold_kbps=150,
            )

    def test_invalid_hold_time(self):
        with self.assertRaises(ValueError):
            CongestionPolicy(min_hold_seconds=-1)


if __name__ == "__main__":
    unittest.main()
