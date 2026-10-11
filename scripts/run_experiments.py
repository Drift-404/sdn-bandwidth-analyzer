
#!/usr/bin/env python3

import argparse
import csv
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from topology.topology import create_topology


RESULTS = ROOT / "results"
RAW = RESULTS / "raw"
CSV_FILE = RESULTS / "experiment_results.csv"

PORT = 5001
PACKET_SIZE = 1024
SENDER_DURATION = 3
RECEIVER_DURATION = 5
SUMMARY_WAIT = 2


def flow_counters():
    """Read the OpenFlow counters for the h1 -> h2 forwarding rule."""
    result = subprocess.run(
        ["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "s1"],
        check=True,
        capture_output=True,
        text=True,
    )

    matches = []

    for line in result.stdout.splitlines():
        incoming = (
            'in_port="s1-eth1"' in line
            or re.search(r"\bin_port=1(?:,|\s)", line)
        )
        destination = (
            "dl_dst=00:00:00:00:00:02" in line
            or "eth_dst=00:00:00:00:00:02" in line
        )
        outgoing = (
            'actions=output:"s1-eth2"' in line
            or re.search(r"\bactions=output:2(?:,|\s|$)", line)
        )

        if not (incoming and destination and outgoing):
            continue

        packets = re.search(r"\bn_packets=(\d+)", line)
        byte_count = re.search(r"\bn_bytes=(\d+)", line)

        if packets and byte_count:
            matches.append({
                "packets": int(packets.group(1)),
                "bytes": int(byte_count.group(1)),
            })

    if len(matches) != 1:
        raise RuntimeError(
            "Expected one h1 -> h2 OpenFlow rule; "
            f"found {len(matches)}. Check the controller and switch flows."
        )

    return matches[0]


def extract(pattern, text, cast=float):
    match = re.search(pattern, text)
    return cast(match.group(1)) if match else None


def parse_logs(sender_text, receiver_text):
    """Extract measurements from the existing sender and receiver output."""
    return {
        "packets_sent": extract(
            r"Packets transmitted:\s*(\d+)", sender_text, int
        ),
        "sender_bytes": extract(
            r"Application bytes:\s*(\d+)", sender_text, int
        ),
        "actual_packet_rate_pps": extract(
            r"Actual packet rate:\s*([\d.]+)", sender_text
        ),
        "sender_throughput_bps": extract(
            r"Application throughput:\s*([\d.]+)", sender_text
        ),
        "packets_received": extract(
            r"Packets received:\s*(\d+)", receiver_text, int
        ),
        "receiver_bytes": extract(
            r"Bytes received:\s*(\d+)", receiver_text, int
        ),
        "receiver_throughput_window_bps": extract(
            r"Receive throughput \(configured window\):\s*([\d.]+)",
            receiver_text,
        ),
        "receiver_throughput_interval_bps": extract(
            r"Receive throughput \(packet arrival interval\):\s*([\d.]+)",
            receiver_text,
        ),
        "packet_loss_pct": extract(
            r"Estimated packet loss:\s*([\d.]+)%",
            receiver_text,
        ),
        "malformed_packets": extract(
            r"Malformed packets:\s*(\d+)", receiver_text, int
        ),
    }


def run_trial(net, rate, trial):
    """Run one receiver/sender experiment and return its measurements."""
    h1 = net.get("h1")
    h2 = net.get("h2")

    stem = f"rate_{rate}_trial_{trial}"
    sender_log = RAW / f"{stem}_sender.log"
    receiver_log = RAW / f"{stem}_receiver.log"

    # Baseline must be captured immediately before the traffic run.
    before = flow_counters()

    with receiver_log.open("w") as receiver_file:
        receiver = h2.popen(
            [
                "python3", "-m", "app.receiver",
                "--host", "10.0.0.2",
                "--port", str(PORT),
                "--duration", str(RECEIVER_DURATION),
                "--summary-wait", str(SUMMARY_WAIT),
            ],
            cwd=str(ROOT),
            stdout=receiver_file,
            stderr=subprocess.STDOUT,
        )

        # Allow the receiver to bind its UDP socket before sending.
        time.sleep(0.5)

        try:
            with sender_log.open("w") as sender_file:
                sender = h1.popen(
                    [
                        "python3", "-m", "app.sender",
                        "--host", "10.0.0.2",
                        "--port", str(PORT),
                        "--sender-id", "h1",
                        "--packet-size", str(PACKET_SIZE),
                        "--rate", str(rate),
                        "--duration", str(SENDER_DURATION),
                    ],
                    cwd=str(ROOT),
                    stdout=sender_file,
                    stderr=subprocess.STDOUT,
                )

                sender_status = sender.wait(timeout=SENDER_DURATION + 15)

                if sender_status != 0:
                    raise RuntimeError(
                        f"Sender failed; inspect {sender_log}"
                    )

            receiver_status = receiver.wait(
                timeout=RECEIVER_DURATION + SUMMARY_WAIT + 15
            )

            if receiver_status != 0:
                raise RuntimeError(
                    f"Receiver failed; inspect {receiver_log}"
                )

        finally:
            if receiver.poll() is None:
                receiver.terminate()
                try:
                    receiver.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    receiver.kill()
                    receiver.wait()

    after = flow_counters()

    sender_text = sender_log.read_text(errors="replace")
    receiver_text = receiver_log.read_text(errors="replace")
    metrics = parse_logs(sender_text, receiver_text)

    required = (
        "packets_sent",
        "sender_bytes",
        "packets_received",
        "receiver_bytes",
    )

    missing = [key for key in required if metrics[key] is None]

    if missing:
        raise RuntimeError(
            f"Missing measurements {missing}; inspect {sender_log} "
            f"and {receiver_log}"
        )

    if after["packets"] < before["packets"]:
        raise RuntimeError("OpenFlow packet counter reset during trial")

    if after["bytes"] < before["bytes"]:
        raise RuntimeError("OpenFlow byte counter reset during trial")

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "rate_pps": rate,
        "trial": trial,
        "packet_size_bytes": PACKET_SIZE,
        "sender_duration_s": SENDER_DURATION,
        "receiver_window_s": RECEIVER_DURATION,
        **metrics,
        "openflow_packet_delta": after["packets"] - before["packets"],
        "openflow_byte_delta": after["bytes"] - before["bytes"],
        "sender_log": str(sender_log.relative_to(ROOT)),
        "receiver_log": str(receiver_log.relative_to(ROOT)),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Run SDN UDP traffic experiments and export CSV results."
    )
    parser.add_argument(
        "--rates",
        nargs="+",
        type=int,
        default=[25, 50, 100],
        help="Traffic rates in packets/s",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=3,
        help="Number of trials per traffic rate",
    )
    args = parser.parse_args()

    if args.trials < 1 or any(rate < 1 for rate in args.rates):
        parser.error("Rates and trials must be positive integers")

    RESULTS.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "timestamp_utc",
        "rate_pps",
        "trial",
        "packet_size_bytes",
        "sender_duration_s",
        "receiver_window_s",
        "packets_sent",
        "sender_bytes",
        "actual_packet_rate_pps",
        "sender_throughput_bps",
        "packets_received",
        "receiver_bytes",
        "receiver_throughput_window_bps",
        "receiver_throughput_interval_bps",
        "packet_loss_pct",
        "malformed_packets",
        "openflow_packet_delta",
        "openflow_byte_delta",
        "sender_log",
        "receiver_log",
    ]

    net = None

    try:
        print("Starting Mininet experiment topology...")
        net = create_topology(interactive=False)

        print("Checking host connectivity...")
        net.pingAll()

        # Allow reactive forwarding rules to settle before taking baselines.
        time.sleep(1)

        with CSV_FILE.open("w", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            csv_file.flush()

            for rate in args.rates:
                for trial in range(1, args.trials + 1):
                    print(
                        f"\nRunning rate={rate} packets/s, "
                        f"trial={trial}/{args.trials}"
                    )

                    row = run_trial(net, rate, trial)
                    writer.writerow(row)
                    csv_file.flush()

                    print(
                        f"Sent={row['packets_sent']}, "
                        f"received={row['packets_received']}, "
                        f"loss={row['packet_loss_pct']}%, "
                        f"OpenFlow packets={row['openflow_packet_delta']}"
                    )

        print(f"\nCSV saved to: {CSV_FILE}")
        print(f"Raw logs saved under: {RAW}")

    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"\nExperiment failed: {error}", file=sys.stderr)
        sys.exit(1)

    finally:
        if net is not None:
            print("Stopping experiment topology...")
            net.stop()


if __name__ == "__main__":
    main()
