# SDN Bandwidth Meter and Traffic Analyzer

## 1. Project Overview

The **SDN Bandwidth Meter and Traffic Analyzer** is a UDP-based network measurement and traffic-management application integrated with Software-Defined Networking (SDN).

The project uses Python sockets to generate and receive controlled UDP traffic, Mininet to emulate network topologies, Open vSwitch (OVS) to forward packets, and OS-Ken as the SDN controller.

The project is developed across two deliverables:

- **D1 – Network Measurement:** Generates UDP traffic at configurable rates, measures application-level performance, collects OpenFlow statistics, and compares measurements across different traffic conditions.
- **D2 – Dynamic SDN Congestion Control:** Extends the measurement system with a multi-switch topology and a dynamic congestion-control mechanism that installs and removes OpenFlow meters based on measured network traffic.

### Objectives

- Generate UDP traffic at configurable packet rates, packet sizes, and durations.
- Measure transmitted and received packets and application-level throughput.
- Estimate packet loss using sender summaries and received sequence numbers.
- Collect packet and byte counters from OpenFlow forwarding rules.
- Compare application-level measurements with network-level statistics.
- Monitor network traffic using the SDN controller.
- Detect congestion using configurable throughput thresholds.
- Dynamically install and remove OpenFlow meters to control traffic.
- Compare static and dynamic network behaviour under competing traffic conditions.

---

## 2. System Architecture

### Technologies

| Component | Technology |
|---|---|
| Programming language | Python 3 |
| Traffic generation and reception | Python UDP sockets |
| Network emulation | Mininet |
| Software switches | Open vSwitch |
| SDN controller | OS-Ken |
| Network protocol | OpenFlow 1.3 |
| Experiment data | CSV |
| Version control | Git and GitHub |

### Main Components

| Component | Responsibility |
|---|---|
| `app/sender.py` | Generates sequenced UDP data packets and sends transmission summaries. |
| `app/receiver.py` | Receives datagrams, validates packets, counts packets and bytes, calculates throughput, and estimates packet loss. |
| `app/protocol.py` | Defines the binary packet format and creates and parses data and summary packets. |
| `app/congestion.py` | Implements the congestion policy, including activation thresholds, recovery thresholds, consecutive samples, and minimum hold time. |
| `app/flow_stats.py` | Tracks OpenFlow flow-counter samples and calculates packet rates and throughput. |
| `controller/controller.py` | Implements the OpenFlow 1.3 learning switch, collects flow statistics, and manages dynamic congestion-control meters. |
| `topology/topology.py` | Creates the original three-host D1 Mininet topology. |
| `topology/topology_d2.py` | Creates the four-host, two-switch D2 Mininet topology. |
| `scripts/flow_counters.py` | Reads forwarding-rule counters and calculates counter differences. |
| `scripts/run_experiments.py` | Automates D1 traffic experiments and records results. |
| `scripts/run_d2_experiments.py` | Automates D2 static and dynamic experiments and records results. |

---

## 3. Network Topologies

### 3.1 D1 Topology – Network Measurement

The original D1 topology contains three hosts connected to one Open vSwitch bridge.

| Component | Address / Configuration | Role |
|---|---|---|
| h1 | `10.0.0.1` | UDP traffic sender |
| h2 | `10.0.0.2` | UDP traffic receiver |
| h3 | `10.0.0.3` | Additional host for connectivity testing |
| s1 | OpenFlow 1.3 | Open vSwitch |
| c0 | `127.0.0.1:6653` | Remote OS-Ken controller |

Each host connects to the switch through a traffic-controlled link configured with a bandwidth of 10 Mbps.

The primary measurement flow is:

`h1 → s1 → h2`

### 3.2 D2 Topology – Dynamic Congestion Control

D2 extends the network to four hosts connected through two Open vSwitch bridges.

| Component | IP address | Role |
|---|---|---|
| h1 | `10.0.0.1` | Competing traffic sender |
| h2 | `10.0.0.2` | Competing traffic receiver |
| h3 | `10.0.0.3` | Dynamically metered traffic sender |
| h4 | `10.0.0.4` | Dynamically metered traffic receiver |
| s1 | OpenFlow 1.3 | First Open vSwitch |
| s2 | OpenFlow 1.3 | Second Open vSwitch |
| c0 | `127.0.0.1:6653` | Remote OS-Ken controller |

The two switches are connected through an inter-switch link configured with:

- Bandwidth: **1 Mbps**
- Delay: **5 ms**

The two traffic flows are:

- **h1 → h2:** Competing traffic.
- **h3 → h4:** Traffic monitored and controlled by the dynamic congestion policy.

Both switches connect to the remote OS-Ken controller using OpenFlow 1.3.

The constrained inter-switch link provides a challenging scenario in which competing traffic flows share limited network capacity.

---

## 4. Packet and Measurement Workflow

### 4.1 UDP Communication

The application uses UDP sockets for traffic generation and reception.

Each data packet contains:

- Sender identifier
- Sequence number
- Timestamp
- Declared datagram size

After transmitting the data packets, the sender sends summary packets containing its reported packet and byte totals.

The receiver:

1. Waits for incoming UDP traffic.
2. Parses and validates received packets.
3. Tracks unique sequence numbers.
4. Counts received packets and bytes.
5. Calculates throughput.
6. Uses sender summaries to estimate packet loss.
7. Reports malformed packets and measurement statistics.

UDP does not guarantee delivery. Packet-loss estimation therefore depends on receiving a valid sender summary.

### 4.2 OpenFlow Statistics

The SDN controller periodically requests flow statistics from connected switches.

The application uses flow-counter samples to calculate:

- Packet-count differences.
- Byte-count differences.
- Packet rate.
- Throughput in bits per second and kilobits per second.

The experiment runners also take OpenFlow counter snapshots before and after traffic trials.

The counter difference is calculated as:

```text
OpenFlow packet delta = packets after - packets before
OpenFlow byte delta   = bytes after - bytes before
```

OpenFlow counters measure packets matching the selected forwarding rule. They are not necessarily identical to application-level packet counts because summary packets and other matching traffic may contribute.

---

## 5. D2 Dynamic Congestion Control

### 5.1 Overview

D2 introduces a dynamic congestion-control mechanism implemented in the OS-Ken controller.

The controller monitors the throughput of the h3 → h4 flow using OpenFlow statistics.

When congestion is detected, it installs an OpenFlow meter on the monitored forwarding rule. When the network recovers, the meter is removed and normal forwarding is restored.

The implementation uses OpenFlow meters rather than dynamic rerouting.

### 5.2 Congestion Policy Configuration

The congestion policy uses the following parameters:

| Parameter | Value |
|---|---:|
| High congestion threshold | 150 kbps |
| Low congestion threshold | 120 kbps |
| Consecutive samples required | 2 |
| Meter rate | 500 kbps |
| Minimum meter hold time | 15 seconds |

### 5.3 Congestion Detection

The controller periodically collects flow statistics and evaluates the measured throughput.

The policy works as follows:

1. The monitored flow's throughput is measured.
2. If throughput reaches or exceeds 150 kbps for two consecutive samples, congestion is detected.
3. The controller installs an OpenFlow meter on the h3 → h4 forwarding rule.
4. The meter applies a drop band configured at 500 kbps.
5. The monitored flow is constrained while the competing flow can receive a larger share of the available network capacity.

### 5.4 Recovery Mechanism

The controller does not immediately remove the meter when throughput falls.

Instead:

1. The minimum meter hold time of 15 seconds must have elapsed.
2. Throughput must fall to or below 120 kbps.
3. Two consecutive low-throughput samples must be observed.
4. The controller removes the meter and restores unmetered forwarding.

The separate activation and recovery thresholds implement hysteresis, helping prevent rapid switching between congestion states.

### 5.5 Static and Dynamic Modes

The controller supports two operating modes.

| Mode | Behaviour |
|---|---|
| Static | Normal forwarding and flow monitoring continue, but dynamic congestion metering is disabled. |
| Dynamic | The congestion policy evaluates flow statistics and installs or removes meters in response to traffic conditions. |

The mode is controlled using the environment variable:

```bash
SDN_DYNAMIC_METERING=0  # Static mode
SDN_DYNAMIC_METERING=1  # Dynamic mode
```

---

## 6. Setup and Prerequisites

### 6.1 Requirements

- Ubuntu Linux
- Python 3
- Mininet
- Open vSwitch
- OS-Ken
- Git
- Python virtual environment for OS-Ken

Mininet is installed as an Ubuntu system package. Therefore, the topology and experiment runners use system Python.

The OS-Ken controller runs inside the `osken-env` virtual environment.

### 6.2 Install System Dependencies

```bash
sudo apt update
sudo apt install mininet openvswitch-switch python3-venv git
```

Verify Mininet:

```bash
/usr/bin/python3 -c \
  "from mininet.net import Mininet; print('Mininet import OK')"
```

### 6.3 Prepare the OS-Ken Environment

Activate the existing environment:

```bash
source ~/osken-env/bin/activate
```

Verify OS-Ken:

```bash
osken-manager --version
```

To create a new environment if necessary:

```bash
python3 -m venv ~/osken-env
source ~/osken-env/bin/activate
pip install os-ken
```

### 6.4 Clone the Repository

```bash
git clone <repository-url>
cd sdn-bandwidth-analyzer
```

Replace `<repository-url>` with the GitHub repository URL.

---

## 7. Running D1 – Network Measurement

Use separate terminals for the controller and topology.

### Terminal 1: Start the Controller

```bash
cd ~/sdn-bandwidth-analyzer
source ~/osken-env/bin/activate
osken-manager controller/controller.py
```

Leave the controller running.

### Terminal 2: Start the D1 Topology

```bash
cd ~/sdn-bandwidth-analyzer
sudo /usr/bin/python3 topology/topology.py
```

At the Mininet prompt, test connectivity:

```text
pingall
```

The expected result is 0% packet loss, with all six host-to-host checks succeeding.

Inspect OpenFlow rules from another terminal:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

### 7.1 Manual UDP Traffic Test

Start the receiver on h2 from the Mininet CLI:

```text
h2 python3 -m app.receiver --host 10.0.0.2 --port 5001 --duration 5 --summary-wait 2
```

In another terminal, generate traffic from h1:

```text
h1 python3 -m app.sender --host 10.0.0.2 --port 5001 --sender-id h1 --packet-size 1024 --rate 25 --duration 3
```

The receiver waits for the first valid data packet before beginning its measurement window. The sender transmits summary packets after the data phase so the receiver can estimate packet loss.

### 7.2 Automated D1 Experiment

Exit the manually running Mininet CLI by typing `exit`. Keep the controller running.

Execute:

```bash
cd ~/sdn-bandwidth-analyzer
sudo -E /usr/bin/python3 scripts/run_experiments.py --rates 25 50 100 --trials 3
```

The runner creates its own topology, performs connectivity checks, runs traffic trials, collects application measurements and OpenFlow counter differences, saves raw logs, and writes the results.

**Important:** The D1 experiment runner overwrites:

`results/experiment_results.csv`

Preserve existing results before running a new experiment if you need to retain the original dataset.

---

## 8. Running D2 – Dynamic Congestion Control

The D2 experiment runner creates and stops its own Mininet topology. Do not leave another Mininet topology running when starting an automated D2 experiment.

The controller must remain running throughout each experiment.

### 8.1 Start the Controller in Dynamic Mode

In Terminal 1:

```bash
cd ~/sdn-bandwidth-analyzer
source ~/osken-env/bin/activate
SDN_DYNAMIC_METERING=1 osken-manager controller/controller.py
```

### 8.2 Run the Dynamic Experiment

In Terminal 2:

```bash
cd ~/sdn-bandwidth-analyzer
sudo -E /usr/bin/python3 scripts/run_d2_experiments.py --mode dynamic --trials 3
```

The runner:

1. Creates the D2 Mininet topology.
2. Checks host connectivity.
3. Starts UDP receivers for both traffic flows.
4. Generates competing UDP traffic.
5. Collects sender and receiver measurements.
6. Collects OpenFlow counter differences.
7. Saves the results and raw logs.

### 8.3 Run the Static Experiment

Stop the dynamic controller with `Ctrl+C` after the experiment has completed.

Start a new controller instance in static mode in Terminal 1:

```bash
cd ~/sdn-bandwidth-analyzer
source ~/osken-env/bin/activate
SDN_DYNAMIC_METERING=0 osken-manager controller/controller.py
```

In Terminal 2:

```bash
cd ~/sdn-bandwidth-analyzer
sudo -E /usr/bin/python3 scripts/run_d2_experiments.py --mode static --trials 3
```

The static experiment uses normal forwarding and flow monitoring without dynamic meter installation.

**Important:** The controller mode and experiment runner mode must match. Use a static controller for `--mode static` and a dynamic controller for `--mode dynamic`.

### 8.4 D2 Output Files

The D2 experiment runner writes its results to:

`results/d2_experiment_results.csv`

Raw experiment logs are stored under:

```text
results/d2_raw/
├── static/
└── dynamic/
```

The D2 results file is separate from the D1 results file.

The runner records completed trials and skips trials already present in the CSV. If a trial is only partially recorded, it reports the incomplete state rather than silently treating it as completed.

---

## 9. Experimental Results

### 9.1 D1 Results

The original D1 experiment consisted of nine trials: three trials each at configured rates of 25, 50, and 100 packets per second.

Each trial used 1024-byte data datagrams and a three-second sender duration.

| Configured rate | Average actual rate | Average sender throughput | Average OpenFlow packet delta |
|---:|---:|---:|---:|
| 25 pps | 23.20 pps | 190.01 kbps | 78.3 |
| 50 pps | 45.59 pps | 373.49 kbps | 149.7 |
| 100 pps | 90.62 pps | 742.36 kbps | 294.3 |

The measured sender rates were below the configured targets.

Across the original nine trials, sender and receiver packet counts and byte counts matched, with zero reported application packet loss.

A separate validation trial conducted on 12 October 2026 at 25 pps transmitted 75 data packets, received all 75, reported zero packet loss, and recorded an OpenFlow packet-counter delta of 79.

These measurements show that increasing the configured traffic rate increased measured application throughput and the number of packets counted by the selected OpenFlow rule.

### 9.2 D2 Static vs Dynamic Results

Three trials were conducted in each mode using competing traffic on both flows.

Average packet-loss results:

| Traffic flow | Static average packet loss | Dynamic average packet loss |
|---|---:|---:|
| h1 → h2 | 24.43% | 13.46% |
| h3 → h4 | 24.47% | 34.23% |

### 9.3 Result Interpretation

The dynamic congestion-control policy produced the following observed changes:

- **h1 → h2:** Average packet loss decreased from 24.43% to 13.46%, a reduction of 10.97 percentage points.
- **h3 → h4:** Average packet loss increased from 24.47% to 34.23%, an increase of 9.76 percentage points.

This demonstrates the intended traffic-control trade-off.

When congestion is detected on the monitored h3 → h4 flow, the controller installs a meter that constrains that flow. This allows the competing h1 → h2 flow to receive a larger share of the available bandwidth.

The results are based on three trials per mode and describe the tested topology and configuration. They should not be interpreted as proof of performance under every network condition.

### 9.4 Important Measurement Distinction

Application-level packet counts and OpenFlow counter deltas measure different things.

- Application packet-loss estimates use sender summaries and received sequence numbers.
- OpenFlow counters measure traffic matching a particular forwarding rule.
- Summary packets and other matching traffic may contribute to OpenFlow counter values.

Consequently, OpenFlow counter deltas are auxiliary network-level measurements and should not be treated as identical to application-level packet counts.

---

## 10. Testing and Verification

### 10.1 Run the Unit Tests

Activate the OS-Ken virtual environment:

```bash
source ~/osken-env/bin/activate
```

Run:

```bash
python3 -m unittest discover -s tests -v
```

The complete test suite contains **23 tests**.

| Test module | Number of tests | Coverage |
|---|---:|---|
| `test_congestion.py` | 11 | Congestion thresholds, activation, recovery, hold time, and configuration validation |
| `test_protocol.py` | 7 | Data and summary packet encoding, decoding, and malformed-packet rejection |
| `test_stats.py` | 5 | Flow packet rate, throughput, initial samples, counter resets, and zero elapsed time |
| **Total** | **23** | |

All 23 tests passed in the latest verification run.

### 10.2 Python Compilation Check

The following command checks the sender and receiver modules:

```bash
python3 -m py_compile app/sender.py app/receiver.py
```

The broader project compilation check can be run with:

```bash
python3 -m py_compile \
  app/congestion.py \
  app/receiver.py \
  app/sender.py \
  app/flow_stats.py \
  controller/controller.py \
  topology/topology_d2.py \
  scripts/run_d2_experiments.py \
  tests/test_congestion.py
```

### 10.3 D1 Integration Verification

The D1 implementation was verified through:

- Mininet topology startup.
- Successful `pingall` with 0% packet loss.
- Installation of OpenFlow forwarding rules.
- Nonzero forwarding-rule packet and byte counters.
- Successful automated UDP traffic measurement.
- Generation and validation of experiment CSV results.

### 10.4 D2 Integration Verification

The D2 implementation was verified through:

- Successful startup of the four-host, two-switch topology.
- Successful host connectivity checks.
- Installation of the monitored h3 → h4 forwarding rule.
- Detection of congestion from OpenFlow flow statistics.
- Installation of meter ID 1 on the monitored forwarding rule.
- Application of the configured 500 kbps meter.
- Removal of the meter after recovery conditions were satisfied.
- Restoration of unmetered forwarding.
- Successful UDP transmission and reception, including summary packets.
- Generation of static and dynamic experiment results.


---

## 11. Troubleshooting

### `ModuleNotFoundError: No module named 'mininet'`

Use system Python for topology and experiment execution:

```bash
sudo /usr/bin/python3 topology/topology.py
```

Do not assume that the OS-Ken virtual environment contains system-installed Mininet packages.

### `RTNETLINK answers: File exists`

A previous Mininet run may have left stale virtual interfaces.

Exit the Mininet CLI and only when no other Mininet topology needs to remain active, run:

```bash
sudo mn -c
```

### Controller Port Already in Use

Check whether a controller is already running:

```bash
sudo ss -ltnp | grep ':6653'
```

Avoid starting a second controller on the same port.

### No OpenFlow Bridge Found

Check the bridge list:

```bash
sudo ovs-vsctl list-br
```

Start the topology and verify that the switch connects to the controller.

### Results File Contains Fewer Trials Than Expected

Inspect the relevant CSV before rerunning experiments.

The D1 runner overwrites:

```text
results/experiment_results.csv
```

The D2 runner writes to:

```text
results/d2_experiment_results.csv
```

The D2 runner skips completed trials when resuming. Do not delete or overwrite existing experiment results without first preserving them.

---

## 12. Limitations and Future Improvements

### Limitations

- UDP does not guarantee delivery of data or summary datagrams.
- Packet-loss estimation depends on receiving a valid sender summary.
- Application throughput and OpenFlow counter deltas measure different layers of the network.
- Dynamic congestion control is demonstrated through OpenFlow metering rather than dynamic rerouting.
- The D2 comparison uses three trials per mode, one topology, and a configured traffic scenario.
- The experiments do not establish that the same results will occur under all network conditions.
- The current implementation is intended for controlled network measurement and demonstration.

### Possible Future Improvements

- Evaluate additional congestion thresholds and meter rates.
- Increase the number of static and dynamic experiment trials.
- Test additional packet sizes and traffic-generation rates.
- Introduce link failures and recovery scenarios.
- Explore dynamic rerouting and more advanced traffic-prioritization policies.
- Develop a graphical interface for real-time monitoring and visualization.

---

## 13. Conclusion

The SDN Bandwidth Meter and Traffic Analyzer demonstrates network measurement and dynamic traffic management in a Mininet-based Software-Defined Networking environment.

D1 established the UDP measurement workflow, application-level performance calculations, and comparison with OpenFlow forwarding-rule statistics across multiple configured traffic rates.

D2 extended the system with a two-switch topology, flow-statistics monitoring, and a dynamic congestion-control policy that installs and removes OpenFlow meters based on measured traffic conditions.

The static and dynamic experiments demonstrate how SDN-based metering can influence the distribution of available network capacity between competing traffic flows.

Together, the two deliverables provide a reproducible foundation for UDP network measurement, OpenFlow monitoring, and dynamic SDN-based congestion control.

---

**Project:** SDN Bandwidth Meter and Traffic Analyzer
**Controller:** OS-Ken
**Network Emulator:** Mininet
**Switch:** Open vSwitch
**Protocol:** OpenFlow 1.3
**Traffic:** UDP