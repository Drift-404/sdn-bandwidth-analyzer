
import struct
import time

# Packet header:
# packet_type:      1 byte (1 = data, 2 = summary)
# sender_id:       16 bytes
# sequence_number:  4 bytes
# timestamp:        8 bytes
# value:             4 bytes
#
# For data packets, value is the total datagram size.
# For summary packets, value is the total number of data packets sent.

HEADER_FORMAT = "!B16sIdI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

DATA_PACKET = 1
SUMMARY_PACKET = 2


def _encode_sender(sender_id):
    sender_bytes = sender_id.encode("utf-8")

    if not sender_bytes or len(sender_bytes) > 16:
        raise ValueError("sender_id must contain 1-16 UTF-8 bytes")

    return sender_bytes.ljust(16, b"\0")


def create_packet(sender_id, sequence_number, payload_size):
    """Create a data packet of the requested total size."""

    if not 0 <= sequence_number <= 0xFFFFFFFF:
        raise ValueError("sequence_number must fit in an unsigned 32-bit integer")

    if not HEADER_SIZE <= payload_size <= 1400:
        raise ValueError(f"payload_size must be between {HEADER_SIZE} and 1400")

    header = struct.pack(
        HEADER_FORMAT,
        DATA_PACKET,
        _encode_sender(sender_id),
        sequence_number,
        time.time(),
        payload_size,
    )

    return header + b"\0" * (payload_size - HEADER_SIZE)


def create_summary_packet(sender_id, packets_sent, bytes_sent):
    """Create a control packet describing the completed transmission."""

    if not 0 <= packets_sent <= 0xFFFFFFFF:
        raise ValueError("packets_sent must fit in an unsigned 32-bit integer")

    if not 0 <= bytes_sent <= 0xFFFFFFFF:
        raise ValueError("bytes_sent must fit in an unsigned 32-bit integer")

    header = struct.pack(
        HEADER_FORMAT,
        SUMMARY_PACKET,
        _encode_sender(sender_id),
        packets_sent,
        time.time(),
        bytes_sent,
    )

    return header


def parse_packet(packet):
    """Decode a data or summary packet."""

    if len(packet) < HEADER_SIZE:
        raise ValueError("Packet is smaller than the protocol header")

    packet_type, sender_bytes, sequence_number, timestamp, value = (
        struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
    )

    sender_id = sender_bytes.rstrip(b"\0").decode("utf-8")

    if packet_type == DATA_PACKET:
        if value != len(packet):
            raise ValueError("Declared packet size does not match received size")

        return {
            "type": "data",
            "sender_id": sender_id,
            "sequence_number": sequence_number,
            "timestamp": timestamp,
            "payload_size": value,
        }

    if packet_type == SUMMARY_PACKET:
        if len(packet) != HEADER_SIZE:
            raise ValueError("Summary packet has an invalid size")

        return {
            "type": "summary",
            "sender_id": sender_id,
            "packets_sent": sequence_number,
            "timestamp": timestamp,
            "bytes_sent": value,
        }

    raise ValueError("Unknown packet type")
