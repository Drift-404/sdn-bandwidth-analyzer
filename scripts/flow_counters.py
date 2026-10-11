
#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_STATE = Path("/tmp/sdn_flow_before.json")


def read_flow_counters():
    result = subprocess.run(
        ["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "s1"],
        check=True,
        capture_output=True,
        text=True,
    )

    matches = []

    for line in result.stdout.splitlines():
        # Match the h1 -> h2 forwarding rule.
        if not re.search(r"\bin_port=1(?:,|\s)", line):
            continue
        if not re.search(
            r"\b(?:dl_dst|eth_dst)=00:00:00:00:00:02(?:,|\s)",
            line,
        ):
            continue
        if not re.search(r"\bpriority=10(?:,|\s)", line):
            continue
        if not re.search(r"\bactions=output:2(?:,|\s|$)", line):
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
            "Expected exactly one h1 -> h2 forwarding rule, "
            f"found {len(matches)}. Check the switch flows."
        )

    return matches[0]


def main():
    parser = argparse.ArgumentParser(
        description="Measure OpenFlow counter deltas for h1 -> h2."
    )
    parser.add_argument("action", choices=["snapshot", "compare"])
    parser.add_argument("--file", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()

    try:
        current = read_flow_counters()

        if args.action == "snapshot":
            args.file.write_text(json.dumps(current))
            print("Baseline counters saved.")
            print(f"Packets: {current['packets']}")
            print(f"Bytes:   {current['bytes']}")
            return

        if not args.file.exists():
            raise RuntimeError(
                f"No baseline found at {args.file}. Run snapshot first."
            )

        before = json.loads(args.file.read_text())
        packet_delta = current["packets"] - before["packets"]
        byte_delta = current["bytes"] - before["bytes"]

        if packet_delta < 0 or byte_delta < 0:
            raise RuntimeError(
                "Counters decreased; the switch or flow may have reset. "
                "Take a new baseline."
            )

        print("\n--- OpenFlow Counter Delta: h1 -> h2 ---")
        print(f"Packets before: {before['packets']}")
        print(f"Packets after:  {current['packets']}")
        print(f"Packet delta:   {packet_delta}")
        print(f"Bytes before:   {before['bytes']}")
        print(f"Bytes after:    {current['bytes']}")
        print(f"Byte delta:     {byte_delta}")

    except (subprocess.CalledProcessError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
