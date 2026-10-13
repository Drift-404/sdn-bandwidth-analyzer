
#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


def create_topology(interactive=True):
    """Create a simple SDN bandwidth measurement topology."""

    net = Mininet(
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
        build=False,
    )

    info("*** Adding remote SDN controller\n")
    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653,
    )

    info("*** Adding OpenFlow switch\n")
    s1 = net.addSwitch(
        "s1",
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

    info("*** Connecting hosts to the switch\n")
    net.addLink(h1, s1, bw=10)
    net.addLink(h2, s1, bw=10)
    net.addLink(h3, s1, bw=10)

    info("*** Building network\n")
    net.build()

    info("*** Starting controller and switch\n")
    net.start()

    info("*** Topology is ready\n")
    info("*** Hosts: h1, h2, h3\n")
    info("*** Switch: s1 (OpenFlow 1.3)\n")
    info("*** Use 'pingall' to test connectivity\n")

    if interactive:
        try:
            CLI(net)
        finally:
            info("*** Stopping network\n")
            net.stop()

    return net


if __name__ == "__main__":
    setLogLevel("info")
    create_topology()
  
