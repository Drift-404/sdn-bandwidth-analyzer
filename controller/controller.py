import sys
from pathlib import Path

# Add the project root to Python's module search path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.flow_stats import FlowStatsTracker
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib import hub


class BandwidthController(app_manager.OSKenApp):
    """Learning-switch controller with periodic flow statistics."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.stats_tracker = FlowStatsTracker()
        self.monitor_thread = hub.spawn(self._monitor)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        self.datapaths[datapath.id] = datapath

        # Send unmatched packets to the controller.
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]
        self._add_flow(datapath, 0, match, actions)

        self.logger.info(
            "Switch %s connected using OpenFlow 1.3",
            datapath.id,
        )

    def _add_flow(self, datapath, priority, match, actions):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ]

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
        )
        datapath.send_msg(flow_mod)


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        in_port = msg.match["in_port"]
        dpid = datapath.id

        # Ignore packets that are too short to contain an Ethernet header.
        if len(msg.data) < 14:
            return

        # Convert binary MAC addresses to OS-Ken-compatible strings.
        dst_mac = ":".join(f"{b:02x}" for b in msg.data[0:6])
        src_mac = ":".join(f"{b:02x}" for b in msg.data[6:12])

        self.mac_to_port.setdefault(dpid, {})

        # Learn the source MAC address and its ingress port.
        self.mac_to_port[dpid][src_mac] = in_port

        out_port = self.mac_to_port[dpid].get(
            dst_mac,
            ofproto.OFPP_FLOOD,
        )

        actions = [parser.OFPActionOutput(out_port)]

        # Install a forwarding rule when the destination is known.
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_dst=dst_mac,
            )
            self._add_flow(datapath, 10, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        packet_out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(packet_out)


    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER])
    def state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[datapath.id] = datapath

    def _monitor(self):
        while True:
            for datapath in list(self.datapaths.values()):
                parser = datapath.ofproto_parser
                ofproto = datapath.ofproto

                request = parser.OFPFlowStatsRequest(
                    datapath,
                    0,
                    ofproto.OFPTT_ALL,
                    ofproto.OFPP_ANY,
                    ofproto.OFPG_ANY,
                    0,
                    0,
                    parser.OFPMatch(),
                )
                datapath.send_msg(request)

            hub.sleep(5)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        datapath = ev.msg.datapath

        for stat in ev.msg.body:
            if stat.priority == 0:
                continue

            result = self.stats_tracker.update(
                datapath.id,
                stat,
            )

            # First sample establishes the baseline.
            if result is None:
                continue

            self.logger.info(
                "FLOW_RATE switch=%s priority=%s "
                "packets=%s bytes=%s "
                "packet_rate=%.2f pps throughput=%.2f kbps "
                "match=%s",
                result["switch_id"],
                result["priority"],
                result["packet_delta"],
                result["byte_delta"],
                result["packet_rate_pps"],
                result["throughput_kbps"],
                result["match"],
            )
