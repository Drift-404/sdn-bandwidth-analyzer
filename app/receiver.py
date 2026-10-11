
import argparse
import socket
import time
from collections import defaultdict

from app.protocol import parse_packet


def receive_traffic(host, port, duration, summary_wait):
    """Receive UDP traffic and report per-sender statistics."""

    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")

    if duration <= 0:
        raise ValueError("duration must be greater than zero")

    if summary_wait <= 0:
        raise ValueError("summary_wait must be greater than zero")

    packets_received = defaultdict(int)
    bytes_received = defaultdict(int)
    sequences_seen = defaultdict(set)
    summaries = {}
    malformed_packets = 0

    first_packet_time = None
    data_deadline = None
    final_deadline = None

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        print(f"Listening on {host}:{port}...")
        print(f"Data measurement duration: {duration:.1f} seconds")

        while True:
            now = time.monotonic()

            # Before traffic starts, wait indefinitely for the first
            # valid datagram. After it starts, use a bounded time window.
            if first_packet_time is None:
                sock.settimeout(None)
            else:
                deadline = final_deadline
                remaining = deadline - now

                if remaining <= 0:
                    break

                sock.settimeout(remaining)

            try:
                packet, address = sock.recvfrom(65535)
            except socket.timeout:
                break
            except KeyboardInterrupt:
                print("\nReceiver interrupted.")
                break

            try:
                metadata = parse_packet(packet)
            except (ValueError, UnicodeDecodeError):
                malformed_packets += 1
                continue

            sender_id = metadata["sender_id"]

            if metadata["type"] == "summary":
                # Keep the summary with the highest reported packet count.
                previous = summaries.get(sender_id)

                if (
                    previous is None
                    or metadata["packets_sent"] >= previous["packets_sent"]
                ):
                    summaries[sender_id] = metadata

                # A summary is control traffic, not measured data.
                continue

            # Ignore data packets arriving after the measurement window.
            now = time.monotonic()

            if first_packet_time is None:
                first_packet_time = now
                data_deadline = first_packet_time + duration
                final_deadline = data_deadline + summary_wait
                print(f"Traffic detected from {sender_id} at {address}")

            if now > data_deadline:
                continue

            sequence = metadata["sequence_number"]
            packets_received[sender_id] += 1
            bytes_received[sender_id] += len(packet)
            sequences_seen[sender_id].add(sequence)

    if first_packet_time is None:
        print("\nNo valid traffic was received.")
        print(f"Malformed packets: {malformed_packets}")
        return

    elapsed = time.monotonic() - first_packet_time
    total_packets = sum(packets_received.values())
    total_bytes = sum(bytes_received.values())

    print("\n--- UDP Receiver Statistics ---")
    print(f"Listening address:  {host}:{port}")
    print(f"Measurement window: {duration:.3f} seconds")
    print(f"Elapsed time:       {elapsed:.3f} seconds")
    print(f"Packets received:   {total_packets}")
    print(f"Bytes received:     {total_bytes}")
    print(f"Malformed packets:  {malformed_packets}")

    if duration > 0:
        print(
            "Receive throughput: "
            f"{total_bytes * 8 / duration:.2f} bits/s"
        )

    for sender_id in sorted(
        set(packets_received) | set(summaries)
    ):
        received_count = packets_received[sender_id]
        unique_sequences = sequences_seen[sender_id]
        summary = summaries.get(sender_id)

        print(f"\nSender: {sender_id}")
        print(f"  Data datagrams received: {received_count}")
        print(f"  Unique sequences:        {len(unique_sequences)}")
        print(f"  Data bytes received:     {bytes_received[sender_id]}")

        if summary is None:
            print("  Final sender summary:    NOT RECEIVED")
            print("  Packet loss:             UNKNOWN")
            continue

        sent_count = summary["packets_sent"]
        sent_bytes = summary["bytes_sent"]

        # Sequence numbers start at zero. Unique sequence counting
        # avoids counting duplicate datagrams as additional deliveries.
        lost_count = max(0, sent_count - len(unique_sequences))

        if sent_count > 0:
            loss_percent = lost_count / sent_count * 100
        else:
            loss_percent = 0.0

        print(f"  Packets reported sent:   {sent_count}")
        print(f"  Bytes reported sent:     {sent_bytes}")
        print(f"  Estimated packets lost:  {lost_count}")
        print(f"  Estimated packet loss:   {loss_percent:.2f}%")

        if sent_bytes > 0:
            received_byte_ratio = bytes_received[sender_id] / sent_bytes
            print(f"  Received/sent byte ratio: {received_byte_ratio:.4f}")


def main():
    parser = argparse.ArgumentParser(
        description="Receive UDP traffic for SDN experiments."
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Local IPv4 address to bind",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5001,
        help="UDP listening port",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10,
        help="Data measurement duration after first valid data packet",
    )
    parser.add_argument(
        "--summary-wait",
        type=float,
        default=2,
        help="Additional seconds to wait for final summaries",
    )

    args = parser.parse_args()

    try:
        receive_traffic(
            args.host,
            args.port,
            args.duration,
            args.summary_wait,
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
