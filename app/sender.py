
import argparse
import socket
import time

from app.protocol import (
    create_packet,
    create_summary_packet,
    HEADER_SIZE,
)


def send_traffic(host, port, sender_id, packet_size, rate, duration):
    """Generate UDP traffic and send a final transmission summary."""

    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")

    if not HEADER_SIZE <= packet_size <= 1400:
        raise ValueError(
            f"packet_size must be between {HEADER_SIZE} and 1400 bytes"
        )

    if rate <= 0:
        raise ValueError("rate must be greater than zero")

    if duration <= 0:
        raise ValueError("duration must be greater than zero")

    destination = (host, port)
    interval = 1.0 / rate

    packets_sent = 0
    bytes_sent = 0

    start_time = time.monotonic()
    end_time = start_time + duration
    next_send_time = start_time
    interrupted = False

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            while time.monotonic() < end_time:
                now = time.monotonic()

                if now < next_send_time:
                    time.sleep(next_send_time - now)

                if time.monotonic() >= end_time:
                    break

                packet = create_packet(
                    sender_id,
                    packets_sent,
                    packet_size,
                )

                sent = sock.sendto(packet, destination)

                packets_sent += 1
                bytes_sent += sent
                next_send_time += interval

                # Do not accumulate an unbounded catch-up backlog.
                if next_send_time < time.monotonic():
                    next_send_time = time.monotonic()

        except KeyboardInterrupt:
            interrupted = True
            print("\nTransmission interrupted.")

        # Send the summary several times because UDP does not guarantee
        # delivery. These are control packets, not measured data packets.
        summary = create_summary_packet(
            sender_id,
            packets_sent,
            bytes_sent,
        )

        for attempt in range(3):
            try:
                sock.sendto(summary, destination)
            except OSError as error:
                print(f"Could not send summary: {error}")
                break

            if attempt < 2:
                time.sleep(0.1)

    elapsed = time.monotonic() - start_time

    print("\n--- UDP Sender Statistics ---")
    print(f"Destination:          {host}:{port}")
    print(f"Sender ID:            {sender_id}")
    print(f"Configured packet:    {packet_size} bytes")
    print(f"Configured rate:      {rate} packets/s")
    print(f"Configured duration:  {duration:.2f} seconds")
    print(f"Packets transmitted:  {packets_sent}")
    print(f"Application bytes:    {bytes_sent}")
    print(f"Actual elapsed time:  {elapsed:.3f} seconds")

    if elapsed > 0:
        print(f"Actual packet rate:   {packets_sent / elapsed:.2f} packets/s")
        print(
            "Application throughput: "
            f"{bytes_sent * 8 / elapsed:.2f} bits/s"
        )

    print("Summary packets sent: up to 3")
    if interrupted:
        print("Status: interrupted")


def main():
    parser = argparse.ArgumentParser(
        description="Generate configurable UDP traffic for SDN experiments."
    )

    parser.add_argument("--host", required=True, help="Receiver IP address")
    parser.add_argument("--port", type=int, default=5001, help="Receiver UDP port")
    parser.add_argument("--sender-id", default="h1", help="Sender identifier")
    parser.add_argument(
        "--packet-size",
        type=int,
        default=1024,
        help="Total data datagram size in bytes",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=100,
        help="Target packets per second",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10,
        help="Duration in seconds",
    )

    args = parser.parse_args()

    try:
        send_traffic(
            args.host,
            args.port,
            args.sender_id,
            args.packet_size,
            args.rate,
            args.duration,
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
