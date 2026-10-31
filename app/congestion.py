class CongestionPolicy:
    """
    Detect sustained congestion and recovery using throughput measurements.
    """

    def __init__(
        self,
        high_threshold_kbps=150.0,
        low_threshold_kbps=120.0,
        consecutive_samples=2,
        meter_rate_kbps=100,
    ):
        if high_threshold_kbps <= low_threshold_kbps:
            raise ValueError(
                "High threshold must exceed low threshold"
            )

        if low_threshold_kbps < 0:
            raise ValueError("Low threshold cannot be negative")

        if consecutive_samples < 1:
            raise ValueError("consecutive_samples must be positive")

        if meter_rate_kbps <= 0:
            raise ValueError("Meter rate must be positive")

        self.high_threshold_kbps = high_threshold_kbps
        self.low_threshold_kbps = low_threshold_kbps
        self.consecutive_samples = consecutive_samples
        self.meter_rate_kbps = meter_rate_kbps

        self.meter_active = False
        self.high_count = 0
        self.low_count = 0

    def evaluate(self, throughput_kbps):
        """
        Evaluate a throughput measurement.

        Returns:
            "activate"   when sustained congestion is detected
            "deactivate" when sustained recovery is detected
            None         when no policy change is required
        """

        if throughput_kbps < 0:
            raise ValueError("Throughput cannot be negative")

        if not self.meter_active:

            if throughput_kbps >= self.high_threshold_kbps:
                self.high_count += 1
            else:
                self.high_count = 0

            if self.high_count >= self.consecutive_samples:
                self.meter_active = True
                self.high_count = 0
                self.low_count = 0
                return "activate"

        else:

            if throughput_kbps <= self.low_threshold_kbps:
                self.low_count += 1
            else:
                self.low_count = 0

            if self.low_count >= self.consecutive_samples:
                self.meter_active = False
                self.low_count = 0
                self.high_count = 0
                return "deactivate"

        return None