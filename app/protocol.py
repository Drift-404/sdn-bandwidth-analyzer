import struct
import time

# Packet header fields:
# sender_id:       16 bytes
# sequence_number:  4 bytes
# timestamp:        8 bytes
# payload_size:     4 bytes

HEADER_FORMAT = "!16sIdI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def create_packet(sender_id, sequence_number, payload_size):
    """Create a UDP packet containing a header and payload."""

    sender_bytes = sender_id.encode("utf-8")

    if not sender_bytes or len(sender_bytes) > 16:
        raise ValueError("sender_id must contain 1-16 UTF-8 bytes")

    if not 0 <= sequence_number <= 0xFFFFFFFF:
        raise ValueError("sequence_number must fit in an unsigned 32-bit integer")

    if payload_size < HEADER_SIZE:
        raise ValueError(f"payload_size must be at least {HEADER_SIZE} bytes")

    timestamp = time.time()

    header = struct.pack(
        HEADER_FORMAT,
        sender_bytes.ljust(16, b"\0"),
        sequence_number,
        timestamp,
        payload_size,
    )

    payload = b"\0" * (payload_size - HEADER_SIZE)

    return header + payload


def parse_packet(packet):
    """Decode a received packet and return its metadata."""

    if len(packet) < HEADER_SIZE:
        raise ValueError("Packet is smaller than the protocol header")

    sender_bytes, sequence_number, timestamp, payload_size = (
        struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])
    )

    sender_id = sender_bytes.rstrip(b"\0").decode("utf-8")

    if payload_size != len(packet):
        raise ValueError("Declared packet size does not match received size")

    return {
        "sender_id": sender_id,
        "sequence_number": sequence_number,
        "timestamp": timestamp,
        "payload_size": payload_size,
    }