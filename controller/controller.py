import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.flow_stats import FlowStatsTracker
from app.congestion import CongestionPolicy

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
    """Learning switch with flow monitoring and congestion control."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    # D2 target: h3 -> h4 through s1
    TARGET_SWITCH_ID = 1
    TARGET_IN_PORT = 2
    TARGET_DST_MAC = "00:00:00:00:00:04"
    TARGET_OUT_PORT = 3

    METER_ID = 1
    ENABLE_DYNAMIC_METERING = (
        os.getenv("SDN_DYNAMIC_METERING", "1").strip() == "1"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.mac_to_port = {}
        self.datapaths = {}

        self.stats_tracker = FlowStatsTracker()

        # One independent congestion policy per switch.
        self.congestion_policies = {}

        # Tracks which switches currently have our meter installed.
        self.active_meters = set()

        self.monitor_thread = hub.spawn(self._monitor)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        self.datapaths[datapath.id] = datapath
        self.congestion_policies[datapath.id] = CongestionPolicy(
            meter_rate_kbps=500,
            min_hold_seconds=15,
        )

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

    def _is_target_flow(self, stat):
        """Identify the h3 -> h4 forwarding rule on s1."""

        return (
            stat.priority == 10
            and stat.match.get("in_port") == self.TARGET_IN_PORT
            and str(stat.match.get("eth_dst", "")).lower()
            == self.TARGET_DST_MAC
        )
    def _modify_target_flow(self, datapath, meter_id=None):
        """Modify the h3 -> h4 rule with or without a meter."""

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        match = parser.OFPMatch(
            in_port=self.TARGET_IN_PORT,
            eth_dst=self.TARGET_DST_MAC,
        )

        actions = [
            parser.OFPActionOutput(self.TARGET_OUT_PORT)
        ]

        instructions = []

        # OpenFlow meter instruction must precede apply-actions.
        if meter_id is not None:
            instructions.append(
                parser.OFPInstructionMeter(meter_id)
            )

        instructions.append(
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        )

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_MODIFY_STRICT,
            table_id=0,
            priority=10,
            match=match,
            instructions=instructions,
        )

        datapath.send_msg(flow_mod)

    def _install_meter(self, datapath):
        """Install a configured DROP meter and attach it to h3 -> h4."""

        dpid = datapath.id

        if dpid != self.TARGET_SWITCH_ID:
            return

        if dpid in self.active_meters:
            return

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        policy = self.congestion_policies[dpid]
        meter_rate = policy.meter_rate_kbps

        band = parser.OFPMeterBandDrop(
            rate=meter_rate,
            burst_size=100,
        )

        meter_mod = parser.OFPMeterMod(
            datapath=datapath,
            command=ofproto.OFPMC_ADD,
            flags=(
                ofproto.OFPMF_KBPS
                | ofproto.OFPMF_BURST
            ),
            meter_id=self.METER_ID,
            bands=[band],
        )

        datapath.send_msg(meter_mod)

        self._modify_target_flow(
            datapath,
            meter_id=self.METER_ID,
        )

        self.active_meters.add(dpid)

        self.logger.warning(
            "CONGESTION_ACTION switch=%s "
            "action=ACTIVATE_METER rate=%s kbps",
            dpid,
            meter_rate,
        )

    def _remove_meter(self, datapath):
        """Restore normal forwarding and remove the h3 -> h4 meter."""

        dpid = datapath.id

        if dpid not in self.active_meters:
            return

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Restore the original unmetered forwarding rule first.
        self._modify_target_flow(datapath)

        meter_mod = parser.OFPMeterMod(
            datapath=datapath,
            command=ofproto.OFPMC_DELETE,
            flags=0,
            meter_id=self.METER_ID,
            bands=[],
        )

        datapath.send_msg(meter_mod)

        self.active_meters.discard(dpid)

        self.logger.warning(
            "CONGESTION_ACTION switch=%s action=REMOVE_METER",
            dpid,
        )

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        in_port = msg.match["in_port"]
        dpid = datapath.id

        if len(msg.data) < 14:
            return

        dst_mac = ":".join(
            f"{b:02x}" for b in msg.data[0:6]
        )
        src_mac = ":".join(
            f"{b:02x}" for b in msg.data[6:12]
        )

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src_mac] = in_port

        out_port = self.mac_to_port[dpid].get(
            dst_mac,
            ofproto.OFPP_FLOOD,
        )

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_dst=dst_mac,
            )

            if (
                dpid == self.TARGET_SWITCH_ID
                and in_port == self.TARGET_IN_PORT
                and dst_mac == self.TARGET_DST_MAC
                and dpid in self.active_meters
            ):
                self._modify_target_flow(
                    datapath,
                    meter_id=self.METER_ID,
                )
            else:
                self._add_flow(
                    datapath,
                    10,
                    match,
                    actions,
                )

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

    @set_ev_cls(
        ofp_event.EventOFPStateChange,
        [MAIN_DISPATCHER],
    )
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

    @set_ev_cls(
        ofp_event.EventOFPFlowStatsReply,
        MAIN_DISPATCHER,
    )
    def flow_stats_reply_handler(self, ev):
        datapath = ev.msg.datapath
        dpid = datapath.id

        policy = self.congestion_policies.get(dpid)

        for stat in ev.msg.body:
            if stat.priority == 0:
                continue

            result = self.stats_tracker.update(
                dpid,
                stat,
            )

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

            if (
                not self.ENABLE_DYNAMIC_METERING
                or dpid != self.TARGET_SWITCH_ID
                or policy is None
                or not self._is_target_flow(stat)
            ):
                continue

            decision = policy.evaluate(
                result["throughput_kbps"]
            )

            if decision == "activate":
                self._install_meter(datapath)

            elif decision == "deactivate":
                self._remove_meter(datapath)