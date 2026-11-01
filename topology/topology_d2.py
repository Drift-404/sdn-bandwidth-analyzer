
#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


def create_topology(interactive=True):
    """Create a four-host, two-switch D2 topology."""

    net = Mininet(
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=False,
        build=False,
    )

    info("*** Adding remote SDN controller\n")
    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653,
    )

    info("*** Adding switches\n")

    s1 = net.addSwitch(
        "s1",
        protocols="OpenFlow13",
        failMode="secure",
    )

    s2 = net.addSwitch(
        "s2",
        protocols="OpenFlow13",
        failMode="secure",
    )

    info("*** Adding hosts\n")

    h1 = net.addHost(
        "h1",
        ip="10.0.0.1/24",
        mac="00:00:00:00:00:01",
    )

    h2 = net.addHost(
        "h2",
        ip="10.0.0.2/24",
        mac="00:00:00:00:00:02",
    )

    h3 = net.addHost(
        "h3",
        ip="10.0.0.3/24",
        mac="00:00:00:00:00:03",
    )

    h4 = net.addHost(
        "h4",
        ip="10.0.0.4/24",
        mac="00:00:00:00:00:04",
    )

    info("*** Connecting h1 and h3 to s1\n")

    net.addLink(h1, s1, port2=1, bw=10)
    net.addLink(h3, s1, port2=2, bw=10)

    info("*** Connecting h2 and h4 to s2\n")

    net.addLink(h2, s2, port2=1, bw=10)
    net.addLink(h4, s2, port2=2, bw=10)

    info("*** Creating 1 Mbps inter-switch bottleneck\n")

    net.addLink(
        s1,
        s2,
        port1=3,
        port2=3,
        bw=1,
        delay="5ms",
    )

    info("*** Building network\n")
    net.build()

    info("*** Starting controller and switches\n")
    net.start()

    info("*** D2 topology ready\n")
    info("*** h1 -> h2: competing traffic\n")
    info("*** h3 -> h4: dynamically metered traffic\n")
    info("*** Inter-switch link: 1 Mbps, 5ms delay\n")

    if interactive:
        try:
            CLI(net)
        finally:
            info("*** Stopping D2 network\n")
            net.stop()

    return net


if __name__ == "__main__":
    setLogLevel("info")
    create_topology()
