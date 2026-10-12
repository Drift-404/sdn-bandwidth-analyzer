# SDN Bandwidth Meter and Traffic Analyzer

## 1. Project Overview

The SDN Bandwidth Meter and Traffic Analyzer is a UDP-based network measurement application integrated with Software-Defined Networking (SDN). It generates controlled UDP traffic in a Mininet topology, measures application-level performance, and compares those measurements with packet and byte counters obtained from OpenFlow forwarding rules.

The project uses Python sockets for traffic generation and reception, Mininet for network emulation, Open vSwitch as the software switch, and OS-Ken as the SDN controller.

### Objectives

- Generate UDP traffic at configurable packet rates and durations.
- Count transmitted and received data packets.
- Measure application-level throughput.
- Estimate packet loss using sender summaries and received sequence numbers.
- Collect OpenFlow flow statistics.
- Compare application-level measurements with network-level counters.
- Evaluate traffic under different configured packet rates.

## 2. System Architecture

### Components

| Component | Responsibility |
|---|---|
| UDP sender (`app/sender.py`) | Generates sequenced UDP data packets at a configured rate and sends transmission summaries. |
| UDP receiver (`app/receiver.py`) | Receives datagrams, validates packets, counts packets and bytes, calculates throughput, and estimates packet loss. |
| Packet protocol (`app/protocol.py`) | Defines the binary message format and creates and parses data and summary packets. |
| SDN controller (`controller/controller.py`) | Learns MAC addresses, installs forwarding rules, and periodically requests OpenFlow flow statistics. |
| Mininet topology (`topology/topology.py`) | Creates three hosts connected to an OpenFlow 1.3 switch. |
| Flow counter utility (`scripts/flow_counters.py`) | Reads forwarding-rule counters and calculates counter differences between snapshots. |
| Experiment runner (`scripts/run_experiments.py`) | Automates traffic trials, collects measurements, saves raw logs, and writes a CSV results file. |
| Protocol tests (`tests/test_protocol.py`) | Tests packet encoding, decoding, and malformed-packet rejection. |

### Network topology

The emulated network contains three hosts connected to one Open vSwitch bridge.

- **h1:** `10.0.0.1` — UDP traffic sender
- **h2:** `10.0.0.2` — UDP traffic receiver
- **h3:** `10.0.0.3` — additional host for connectivity testing
- **s1:** OpenFlow 1.3 switch
- **c0:** remote OS-Ken controller at `127.0.0.1:6653`

Each host connects to the switch through a traffic-controlled link configured with a bandwidth of 10 Mbps.

### Packet and measurement flow

1. The controller connects to the switch and installs a table-miss rule.
2. Hosts exchange packets through the switch. The controller learns source MAC addresses and installs forwarding rules when destinations become known.
3. The UDP receiver listens on port 5001.
4. The sender transmits data packets containing a sender identifier, sequence number, timestamp, and declared datagram size.
5. After transmission, the sender sends summary packets containing the reported packet and byte totals.
6. The receiver calculates application-level metrics and estimates packet loss.
7. The experiment runner records application measurements and the change in the matching OpenFlow counters.

## 3. Technologies and Prerequisites

- Ubuntu Linux
- Python 3
- Mininet
- Open vSwitch
- OS-Ken SDN controller
- Python virtual environment for OS-Ken
- Git

The topology uses system Python because Mininet is installed as an Ubuntu system package. The OS-Ken controller runs in the `osken-env` virtual environment.

## 4. Repository Structure

```text
sdn-bandwidth-analyzer/
├── app/
│   ├── analyzer.py
│   ├── protocol.py
│   ├── receiver.py
│   └── sender.py
├── controller/
│   ├── controller.py
│   └── stats.py
├── docs/
├── results/
│   ├── experiment_results.csv
│   ├── validation_2026-10-12.csv
│   └── raw/
├── scripts/
│   ├── flow_counters.py
│   └── run_experiments.py
├── tests/
│   └── test_protocol.py
├── topology/
│   └── topology.py
├── requirements.txt
└── README.md
```

The files `app/analyzer.py` and `controller/stats.py` are currently placeholders and are not part of the demonstrated measurement workflow.

## 5. Setup

### 5.1 Install system dependencies

Install Mininet and Open vSwitch if they are not already available:

```bash
sudo apt update
sudo apt install mininet openvswitch-switch python3-venv
```

Verify Mininet is available:

```bash
/usr/bin/python3 -c \
  "from mininet.net import Mininet; print('Mininet import OK')"
```

### 5.2 Prepare the OS-Ken environment

Activate the existing environment:

```bash
source ~/osken-env/bin/activate
```

Verify OS-Ken is available:

```bash
osken-manager --version
```

If setting up a new environment, create it and install OS-Ken:

```bash
python3 -m venv ~/osken-env
source ~/osken-env/bin/activate
pip install os-ken
```

### 5.3 Clone the repository

```bash
git clone <repository-url>
cd sdn-bandwidth-analyzer
```

Replace `<repository-url>` with the Git repository URL.

## 6. Running the System

Use separate terminals for the controller and topology.

### Terminal 1: Start the controller

```bash
cd ~/sdn-bandwidth-analyzer
source ~/osken-env/bin/activate
osken-manager controller/controller.py
```

Leave the controller running.

### Terminal 2: Start the Mininet topology

```bash
cd ~/sdn-bandwidth-analyzer
sudo /usr/bin/python3 topology/topology.py
```

At the `mininet>` prompt, test connectivity:

```text
pingall
```

The expected result for the demonstrated topology is 0% packet loss, with all six host-to-host checks succeeding.

Inspect OpenFlow rules from another terminal:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

### Manual UDP traffic test

Start the receiver on h2 from the Mininet CLI:

```text
h2 python3 -m app.receiver --host 10.0.0.2 --port 5001 --duration 5 --summary-wait 2
```

In another terminal, generate traffic from h1:

```text
h1 python3 -m app.sender --host 10.0.0.2 --port 5001 --sender-id h1 --packet-size 1024 --rate 25 --duration 3
```

The receiver waits for the first valid data packet before beginning its measurement window. The sender transmits summary packets after the data phase so the receiver can estimate loss.

### Automated experiment

First, exit the manually running Mininet CLI by typing `exit`. Keep the controller running.

Then execute:

```bash
cd ~/sdn-bandwidth-analyzer
sudo -E /usr/bin/python3 scripts/run_experiments.py --rates 25 50 100 --trials 3
```

The runner creates its own topology, performs connectivity checks, runs the sender and receiver for each trial, collects flow-counter differences, and writes the results.

**Important:** the experiment runner overwrites `results/experiment_results.csv`. Preserve existing results before running a new experiment if you need to retain the original dataset.

## 7. Measurements

### Application-level metrics

- **Packets sent:** Number of data datagrams reported by the sender.
- **Packets received:** Number of valid data datagrams received by the receiver.
- **Application bytes:** Total data datagram bytes reported by the sender or receiver.
- **Actual packet rate:** Packets transmitted divided by the sender's elapsed time.
- **Sender throughput:** Application bytes multiplied by eight, divided by the sender's elapsed time.
- **Receiver throughput (configured window):** Received data bits divided by the configured measurement duration.
- **Receiver throughput (packet arrival interval):** Received data bits divided by the time between the first and last accepted data packets, when that interval is positive.
- **Estimated packet loss:** Sender-reported data packet count minus the number of unique received sequence numbers, divided by the sender-reported count.
- **Malformed packets:** Datagrams rejected during protocol parsing.

Packet loss is reported as unknown when the receiver does not obtain a sender summary. UDP does not guarantee delivery of either data or summary packets.

### OpenFlow metrics

The experiment runner takes counter snapshots before and after a traffic trial and calculates:

```text
OpenFlow packet delta = packets after - packets before
OpenFlow byte delta   = bytes after - bytes before
```

The counter utility selects the forwarding rule from h1 to h2, matching ingress port 1, destination MAC `00:00:00:00:00:02`, and output port 2.

OpenFlow counters measure traffic matching the selected switch rule. They are not identical to application data counts: summary packets and other matching traffic may also contribute.

## 8. Experimental Results

The original experiment consisted of nine trials: three trials each at configured rates of 25, 50, and 100 packets per second. Each trial used 1024-byte data datagrams and a three-second sender duration.

| Configured rate | Average actual rate | Average sender throughput | Average OpenFlow packet delta |
|---:|---:|---:|---:|
| 25 pps | 23.20 pps | 190.01 kbps | 78.3 |
| 50 pps | 45.59 pps | 373.49 kbps | 149.7 |
| 100 pps | 90.62 pps | 742.36 kbps | 294.3 |

The measured sender rates were below the configured targets. Across the original nine trials, the sender and receiver packet counts and byte counts matched, with zero reported application packet loss.

A separate validation trial was conducted on 12 October 2026 at 25 pps. It transmitted 75 data packets, received all 75, reported zero packet loss, and recorded an OpenFlow packet-counter delta of 79.

These measurements show that increasing the configured traffic rate increased measured application throughput and the number of packets counted by the selected OpenFlow rule. The results describe the tested setup and do not establish that all network loads or topologies will behave identically.

## 9. Testing

Run the protocol unit tests:

```bash
source ~/osken-env/bin/activate
python3 -m unittest discover -s tests -v
```

The seven protocol tests previously passed:

- Data packet round trip
- Summary packet round trip
- Invalid sender identifier rejection
- Oversized packet rejection
- Undersized packet rejection
- Truncated packet rejection
- Unknown packet type rejection

Additional integration checks previously confirmed:

- Mininet topology startup
- Successful `pingall` with 0% packet loss
- Installation of OpenFlow forwarding rules
- Nonzero forwarding-rule packet and byte counters
- Successful automated UDP traffic measurement
- Generation and validation of experiment CSV results

## 10. Troubleshooting

### `ModuleNotFoundError: No module named 'mininet'`

Use system Python for the topology:

```bash
sudo /usr/bin/python3 topology/topology.py
```

Do not assume the OS-Ken virtual environment contains system-installed Mininet packages.

### `RTNETLINK answers: File exists`

A previous Mininet run may have left stale virtual interfaces. Exit the Mininet CLI and run:

```bash
sudo mn -c
```

Do this only when no other Mininet topology needs to remain active.

### Controller port already in use

Check whether a controller is already running:

```bash
sudo ss -ltnp | grep ':6653'
```

Avoid starting a second controller on the same port.

### No OpenFlow bridge found

Check the bridge list:

```bash
sudo ovs-vsctl list-br
```

Start the topology and verify that the switch connects to the controller.

### Results file contains fewer trials than expected

The experiment runner overwrites the main CSV. Restore a committed original dataset with:

```bash
git show HEAD:results/experiment_results.csv > /tmp/original_results.csv
```

Review the file before replacing the current dataset.

## 11. Limitations

- UDP does not guarantee delivery of data or summary datagrams.
- Packet-loss estimation depends on receiving a valid sender summary.
- Application throughput and OpenFlow counter deltas measure different layers of the network.
- The controller currently learns MAC addresses, installs forwarding rules, and logs flow statistics. It does not dynamically reroute or prioritize traffic based on measured bandwidth.
- The experiments cover one three-host topology, one packet size, and the configured rates listed in the results.
- The current implementation is intended for controlled network measurement and demonstration.

## 12. Conclusion

The project demonstrates UDP traffic generation and reception in a Mininet-based SDN environment, with application-level performance measurements compared against OpenFlow forwarding-rule statistics. The tested topology achieved full host connectivity, and the original experiment set completed nine trials across three configured packet rates.

The implementation, test cases, experiment scripts, and recorded measurements provide a reproducible foundation for the D1 demonstration and subsequent development.
