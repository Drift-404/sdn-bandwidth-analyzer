import unittest

from app.congestion import CongestionPolicy


class TestCongestionPolicy(unittest.TestCase):

    def setUp(self):
        self.policy = CongestionPolicy()

    def test_no_activation_below_threshold(self):
        result = self.policy.evaluate(100)

        self.assertIsNone(result)
        self.assertFalse(self.policy.meter_active)

    def test_requires_consecutive_high_samples(self):
        self.assertIsNone(self.policy.evaluate(160))
        self.assertIsNone(self.policy.evaluate(100))

        self.assertIsNone(self.policy.evaluate(160))
        self.assertEqual(
            self.policy.evaluate(170),
            "activate",
        )

        self.assertTrue(self.policy.meter_active)

    def test_recovery_requires_consecutive_low_samples(self):
        self.policy.evaluate(160)
        self.policy.evaluate(160)

        self.assertTrue(self.policy.meter_active)

        self.assertIsNone(self.policy.evaluate(110))
        self.assertIsNone(self.policy.evaluate(130))

        self.assertIsNone(self.policy.evaluate(110))
        self.assertEqual(
            self.policy.evaluate(100),
            "deactivate",
        )

        self.assertFalse(self.policy.meter_active)

    def test_no_repeated_activation(self):
        self.policy.evaluate(160)
        self.policy.evaluate(160)

        self.assertIsNone(self.policy.evaluate(200))
        self.assertTrue(self.policy.meter_active)

    def test_invalid_negative_throughput(self):
        with self.assertRaises(ValueError):
            self.policy.evaluate(-10)

    def test_invalid_threshold_configuration(self):
        with self.assertRaises(ValueError):
            CongestionPolicy(
                high_threshold_kbps=100,
                low_threshold_kbps=150,
            )


if __name__ == "__main__":
    unittest.main()