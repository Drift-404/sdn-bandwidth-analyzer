
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

from topology.topology_d2 import create_topology

RESULTS = ROOT / "results"
RAW = RESULTS / "d2_raw"

PACKET_SIZE = 1024
RATE = 100
SENDER_DURATION = 30
RECEIVER_DURATION = 40
SUMMARY_WAIT = 2

FLOWS = {
    "h1_h2": {
        "sender": "h1",
        "receiver": "h2",
        "destination": "10.0.0.2",
        "port": 5001,
        "sender_id": "h1",
        "in_port": 1,
        "dst_mac": "00:00:00:00:00:02",
    },
    "h3_h4": {
        "sender": "h3",
        "receiver": "h4",
        "destination": "10.0.0.4",
        "port": 5002,
        "sender_id": "h3",
        "in_port": 2,
        "dst_mac": "00:00:00:00:00:04",
    },
}

CSV_FILE = RESULTS / "d2_experiment_results.csv"


def read_flow_counters():
    result = subprocess.run(
        ["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "s1"],
        check=True,
        capture_output=True,
        text=True,
    )

    counters = {}

    for flow_name, config in FLOWS.items():
        matches = []

        for line in result.stdout.splitlines():
            incoming = re.search(
                rf'\bin_port=(?:"s1-eth{config["in_port"]}"|'
                rf'{config["in_port"]})(?:,|\s)',
                line,
            )

            destination = re.search(
                rf'\b(?:dl_dst|eth_dst)={config["dst_mac"]}(?:,|\s)',
                line,
            )

            outgoing = re.search(
                r'actions=.*output:(?:"s1-eth3"|3)(?:,|\s|$)',
                line,
            )

            priority = re.search(r"\bpriority=10(?:,|\s)", line)

            if not all((incoming, destination, outgoing, priority)):
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
                f"Expected exactly one {flow_name} flow on s1; "
                f"found {len(matches)}."
            )

        counters[flow_name] = matches[0]

    return counters


def extract(pattern, content, cast=float):
    match = re.search(pattern, content)
    return cast(match.group(1)) if match else None


def parse_logs(sender_text, receiver_text):
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


def run_trial(net, mode, trial):
    processes = []
    open_files = []
    logs = {}

    try:
        # Start both receivers before sending traffic.
        for flow_name, config in FLOWS.items():
            receiver_log = (
                RAW / mode / f"trial_{trial}_{flow_name}_receiver.log"
            )
            receiver_log.parent.mkdir(parents=True, exist_ok=True)

            receiver_file = receiver_log.open("w")
            open_files.append(receiver_file)

            receiver = net.get(config["receiver"]).popen(
                [
                    "python3", "-u", "-m", "app.receiver",
                    "--host", config["destination"],
                    "--port", str(config["port"]),
                    "--duration", str(RECEIVER_DURATION),
                    "--summary-wait", str(SUMMARY_WAIT),
                ],
                cwd=str(ROOT),
                stdout=receiver_file,
                stderr=subprocess.STDOUT,
            )

            processes.append(receiver)
            logs[(flow_name, "receiver")] = receiver_log

        time.sleep(1)

        # Capture counters immediately before simultaneous traffic.
        before = read_flow_counters()

        senders = []

        for flow_name, config in FLOWS.items():
            sender_log = (
                RAW / mode / f"trial_{trial}_{flow_name}_sender.log"
            )

            sender_file = sender_log.open("w")
            open_files.append(sender_file)

            sender = net.get(config["sender"]).popen(
                [
                    "python3", "-u", "-m", "app.sender",
                    "--host", config["destination"],
                    "--port", str(config["port"]),
                    "--sender-id", config["sender_id"],
                    "--packet-size", str(PACKET_SIZE),
                    "--rate", str(RATE),
                    "--duration", str(SENDER_DURATION),
                ],
                cwd=str(ROOT),
                stdout=sender_file,
                stderr=subprocess.STDOUT,
            )

            senders.append((flow_name, sender))
            logs[(flow_name, "sender")] = sender_log

        # Wait for both senders.
        for flow_name, sender in senders:
            status = sender.wait(timeout=SENDER_DURATION + 15)

            if status != 0:
                raise RuntimeError(
                    f"{flow_name} sender failed; inspect its raw log."
                )

        # Receivers finish after their measurement and summary windows.
        for process in processes:
            status = process.wait(
                timeout=RECEIVER_DURATION + SUMMARY_WAIT + 20
            )

            if status != 0:
                raise RuntimeError("A receiver failed; inspect raw logs.")

        # Allow the last OpenFlow statistics update to settle.
        time.sleep(2)
        after = read_flow_counters()

        rows = []

        for flow_name in FLOWS:
            sender_text = logs[(flow_name, "sender")].read_text(
                errors="replace"
            )
            receiver_text = logs[(flow_name, "receiver")].read_text(
                errors="replace"
            )

            metrics = parse_logs(sender_text, receiver_text)
            sent = metrics["packets_sent"]
            received = metrics["packets_received"]

            if sent is not None and received is not None:
                if received > sent:
                    raise RuntimeError(
                        f"{flow_name}: received count exceeds transmitted count."
                    )

                metrics["packet_loss_pct"] = (
                    round((sent - received) / sent * 100, 2)
                    if sent > 0 else 0.0
                )

            required = (
                "packets_sent",
                "sender_bytes",
                "packets_received",
                "receiver_bytes",
                "packet_loss_pct",
            )

            missing = [
                key for key in required if metrics[key] is None
            ]

            if missing:
                raise RuntimeError(
                    f"{flow_name}: missing measurements {missing}."
                )

            packet_delta = (
                after[flow_name]["packets"]
                - before[flow_name]["packets"]
            )
            byte_delta = (
                after[flow_name]["bytes"]
                - before[flow_name]["bytes"]
            )

            if packet_delta < 0 or byte_delta < 0:
                raise RuntimeError(
                    f"{flow_name}: OpenFlow counters reset during trial."
                )

            rows.append({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "mode": mode,
                "trial": trial,
                "flow": flow_name,
                "rate_pps": RATE,
                "packet_size_bytes": PACKET_SIZE,
                "sender_duration_s": SENDER_DURATION,
                "receiver_window_s": RECEIVER_DURATION,
                **metrics,
                "openflow_packet_delta": packet_delta,
                "openflow_byte_delta": byte_delta,
                "sender_log": str(
                    logs[(flow_name, "sender")].relative_to(ROOT)
                ),
                "receiver_log": str(
                    logs[(flow_name, "receiver")].relative_to(ROOT)
                ),
            })

        return rows

    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        for file_handle in open_files:
            file_handle.close()


def main():
    parser = argparse.ArgumentParser(
        description="Run simultaneous two-flow D2 SDN experiments."
    )

    parser.add_argument(
        "--mode",
        choices=("static", "dynamic"),
        required=True,
        help="Controller mode currently running.",
    )

    parser.add_argument(
        "--trials",
        type=int,
        default=3,
        help="Number of trials.",
    )

    args = parser.parse_args()

    if args.trials < 1:
        parser.error("--trials must be positive.")

    RESULTS.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "timestamp_utc", "mode", "trial", "flow",
        "rate_pps", "packet_size_bytes",
        "sender_duration_s", "receiver_window_s",
        "packets_sent", "sender_bytes",
        "actual_packet_rate_pps", "sender_throughput_bps",
        "packets_received", "receiver_bytes",
        "receiver_throughput_window_bps",
        "receiver_throughput_interval_bps",
        "packet_loss_pct", "malformed_packets",
        "openflow_packet_delta", "openflow_byte_delta",
        "sender_log", "receiver_log",
    ]

    if not CSV_FILE.exists():
        with CSV_FILE.open("w", newline="") as csv_file:
            csv.writer(csv_file).writerow(fieldnames)

    print(f"Mode: {args.mode}")
    print(f"Trials: {args.trials}")
    print(f"CSV: {CSV_FILE}")

    net = None

    try:
        print("\nStarting D2 topology...")
        net = create_topology(interactive=False)

        print("\nChecking connectivity...")
        loss = net.pingAll()

        if loss != 0:
            raise RuntimeError(
                f"Host connectivity check failed: {loss}% packet loss."
            )

        time.sleep(2)

        completed_trials = {}

        if CSV_FILE.exists():
            with CSV_FILE.open("r", newline="") as csv_file:
                reader = csv.DictReader(csv_file)

                for row in reader:
                    if row["mode"] == args.mode:
                        trial_number = int(row["trial"])
                        completed_trials.setdefault(
                            trial_number, set()
                        ).add(row["flow"])

        required_flows = set(FLOWS)

        for trial in range(1, args.trials + 1):
            existing_flows = completed_trials.get(trial, set())

            if existing_flows == required_flows:
                print(f"Skipping completed trial {trial}.")
                continue

            if existing_flows:
                raise RuntimeError(
                    f"Trial {trial} is incomplete in the CSV. "
                    "Inspect the existing records before continuing."
                )
            print(
                f"\nRunning {args.mode} trial "
                f"{trial}/{args.trials}..."
            )

            rows = run_trial(net, args.mode, trial)

            with CSV_FILE.open("a", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=fieldnames,
                )
                writer.writerows(rows)

            for row in rows:
                print(
                    f"{row['flow']}: "
                    f"sent={row['packets_sent']}, "
                    f"received={row['packets_received']}, "
                    f"loss={row['packet_loss_pct']}%, "
                    f"OpenFlow packets={row['openflow_packet_delta']}"
                )

        print(f"\nResults appended to {CSV_FILE}")
        print(f"Raw logs saved under {RAW / args.mode}")

    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"\nExperiment failed: {error}", file=sys.stderr)
        sys.exit(1)

    finally:
        if net is not None:
            print("\nStopping D2 topology...")
            net.stop()


if __name__ == "__main__":
    main()
