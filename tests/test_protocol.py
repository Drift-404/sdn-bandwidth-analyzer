
import unittest

from app.protocol import (
    HEADER_SIZE,
    create_packet,
    create_summary_packet,
    parse_packet,
)


class TestProtocol(unittest.TestCase):

    def test_data_packet_round_trip(self):
        packet = create_packet("h1", 1, 1024)
        metadata = parse_packet(packet)

        self.assertEqual(len(packet), 1024)
        self.assertEqual(metadata["type"], "data")
        self.assertEqual(metadata["sender_id"], "h1")
        self.assertEqual(metadata["sequence_number"], 1)
        self.assertEqual(metadata["payload_size"], 1024)

    def test_summary_packet_round_trip(self):
        packet = create_summary_packet("h1", 100, 102400)
        metadata = parse_packet(packet)

        self.assertEqual(len(packet), HEADER_SIZE)
        self.assertEqual(metadata["type"], "summary")
        self.assertEqual(metadata["sender_id"], "h1")
        self.assertEqual(metadata["packets_sent"], 100)
        self.assertEqual(metadata["bytes_sent"], 102400)

    def test_packet_too_small_is_rejected(self):
        with self.assertRaises(ValueError):
            create_packet("h1", 1, HEADER_SIZE - 1)

    def test_packet_too_large_is_rejected(self):
        with self.assertRaises(ValueError):
            create_packet("h1", 1, 1401)

    def test_invalid_sender_id_is_rejected(self):
        with self.assertRaises(ValueError):
            create_packet("this_sender_id_is_too_long", 1, 1024)

    def test_truncated_packet_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_packet(b"\x01\x02")

    def test_unknown_packet_type_is_rejected(self):
        packet = bytearray(create_packet("h1", 1, 1024))
        packet[0] = 99

        with self.assertRaises(ValueError):
            parse_packet(bytes(packet))


if __name__ == "__main__":
    unittest.main()
