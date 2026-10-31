import time


class FlowStatsTracker:
    """Calculate traffic rates using consecutive OpenFlow counter samples."""

    def __init__(self):
        self.previous_samples = {}

    @staticmethod
    def _get_flow_key(dpid, stat):
        """Identify a flow using its switch, table, priority and match."""

        match_fields = tuple(
            sorted(
                (str(key), repr(value))
                for key, value in stat.match.items()
            )
        )

        return (
            dpid,
            stat.table_id,
            stat.priority,
            match_fields,
        )

    def update(self, dpid, stat, timestamp=None):
        """
        Process a flow-statistics sample.

        Returns calculated rates after a valid previous sample exists.
        Returns None for the first sample or invalid counter intervals.
        """

        if timestamp is None:
            timestamp = time.monotonic()

        key = self._get_flow_key(dpid, stat)

        current_packets = stat.packet_count
        current_bytes = stat.byte_count

        previous = self.previous_samples.get(key)

        # Save the first sample as the baseline.
        if previous is None:
            self.previous_samples[key] = (
                current_packets,
                current_bytes,
                timestamp,
            )
            return None

        previous_packets, previous_bytes, previous_time = previous

        # Always update the baseline to the latest sample.
        self.previous_samples[key] = (
            current_packets,
            current_bytes,
            timestamp,
        )

        elapsed = timestamp - previous_time

        if elapsed <= 0:
            return None

        packet_delta = current_packets - previous_packets
        byte_delta = current_bytes - previous_bytes

        # Counters may reset when a flow is removed or reinstalled.
        if packet_delta < 0 or byte_delta < 0:
            return None

        packet_rate = packet_delta / elapsed
        throughput_bps = (byte_delta * 8) / elapsed

        return {
            "switch_id": dpid,
            "priority": stat.priority,
            "match": str(stat.match),
            "packet_delta": packet_delta,
            "byte_delta": byte_delta,
            "elapsed_seconds": elapsed,
            "packet_rate_pps": packet_rate,
            "throughput_bps": throughput_bps,
            "throughput_kbps": throughput_bps / 1000,
        }
