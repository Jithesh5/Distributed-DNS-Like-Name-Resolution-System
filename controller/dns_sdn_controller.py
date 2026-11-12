from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib import hub
from os_ken.lib.packet import packet, ethernet
import socket
import logging

LOG = logging.getLogger("project22.sdn")

CLIENT_IP = "10.0.0.2"
PRIMARY_IP = "10.0.0.3"
BACKUP_IP = "10.0.0.4"

DNS_PORT = 5300

# Ports on the client-facing switch s1
CLIENT_PORT = 1
UPLINK_PORT = 2

# Mininet assigns these datapath IDs to s1, s2 and s3.
SERVICE_SWITCH_ID = 1

CLIENT_MAC = "00:00:00:00:00:01"
PRIMARY_MAC = "00:00:00:00:00:02"
BACKUP_MAC = "00:00:00:00:00:03"

CONTROL_IP = "127.0.0.1"
CONTROL_PORT = 9999

DNS_COOKIE = 0xD15D0001


class DistributedDNSController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(DistributedDNSController, self).__init__(*args, **kwargs)

        self.datapaths = {}
        self.mac_to_port = {}

        self.backend_ip = PRIMARY_IP
        self._bad_intervals = 0

        self._control_thread = hub.spawn(self._control_loop)
        self._stats_thread = hub.spawn(self._poll_flow_stats)

    def _add_flow(self, dp, priority, match, actions,
                  cookie=0, idle_timeout=0):

        ofp = dp.ofproto
        parser = dp.ofproto_parser

        instructions = [
            parser.OFPInstructionActions(
                ofp.OFPIT_APPLY_ACTIONS, actions
            )
        ]

        mod = parser.OFPFlowMod(
            datapath=dp,
            cookie=cookie,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout
        )

        dp.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):

        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        self.mac_to_port.setdefault(dp.id, {})

        ofp = dp.ofproto
        parser = dp.ofproto_parser

        # Send unknown packets to the controller.
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofp.OFPP_CONTROLLER,
                ofp.OFPCML_NO_BUFFER
            )
        ]

        self._add_flow(dp, 0, match, actions)

        # Install DNS service rules only on client-facing switch s1.
        if dp.id == SERVICE_SWITCH_ID:
            self._install_dns_rules(dp, self.backend_ip)

        LOG.info("Switch %s connected", dp.id)

    def _install_dns_rules(self, dp, backend_ip):

        if dp.id != SERVICE_SWITCH_ID:
            return

        ofp = dp.ofproto
        parser = dp.ofproto_parser

        # Remove previous DNS service rules.
        delete = parser.OFPFlowMod(
            datapath=dp,
            command=ofp.OFPFC_DELETE,
            cookie=DNS_COOKIE,
            cookie_mask=0xffffffffffffffff,
            table_id=ofp.OFPTT_ALL,
            out_port=ofp.OFPP_ANY,
            out_group=ofp.OFPG_ANY,
            match=parser.OFPMatch()
        )

        dp.send_msg(delete)

        if backend_ip == PRIMARY_IP:
            backend_mac = PRIMARY_MAC
        elif backend_ip == BACKUP_IP:
            backend_mac = BACKUP_MAC
        else:
            LOG.error("Unknown backend: %s", backend_ip)
            return

        # DNS request: redirect the virtual service address
        # to the selected backend and forward towards s2.
        req_match = parser.OFPMatch(
            eth_type=0x0800,
            ip_proto=17,
            ipv4_dst=PRIMARY_IP,
            udp_dst=DNS_PORT
        )

        req_actions = [
            parser.OFPActionSetField(ipv4_dst=backend_ip),
            parser.OFPActionSetField(eth_dst=backend_mac),
            parser.OFPActionOutput(UPLINK_PORT)
        ]

        self._add_flow(
            dp, 200, req_match, req_actions,
            cookie=DNS_COOKIE
        )

        # DNS response: restore the virtual service source IP
        # and send the response to the client.
        rep_match = parser.OFPMatch(
            eth_type=0x0800,
            ip_proto=17,
            ipv4_src=backend_ip,
            udp_src=DNS_PORT,
            ipv4_dst=CLIENT_IP
        )

        rep_actions = [
            parser.OFPActionSetField(ipv4_src=PRIMARY_IP),
            parser.OFPActionOutput(CLIENT_PORT)
        ]

        self._add_flow(
            dp, 200, rep_match, rep_actions,
            cookie=DNS_COOKIE
        )

        LOG.info(
            "DNS rules installed on s1: %s -> %s",
            PRIMARY_IP, backend_ip
        )

    def _reset_health_tracking(self):
        self._bad_intervals = 0

    def _poll_flow_stats(self):

        while True:

            dp = self.datapaths.get(SERVICE_SWITCH_ID)

            if dp is not None:
                ofp = dp.ofproto
                parser = dp.ofproto_parser

                request = parser.OFPFlowStatsRequest(
                    datapath=dp,
                    table_id=ofp.OFPTT_ALL,
                    out_port=ofp.OFPP_ANY,
                    out_group=ofp.OFPG_ANY,
                    cookie=DNS_COOKIE,
                    cookie_mask=0xffffffffffffffff,
                    match=parser.OFPMatch()
                )

                dp.send_msg(request)

            hub.sleep(1.0)

    @set_ev_cls(
        ofp_event.EventOFPFlowStatsReply,
        MAIN_DISPATCHER
    )
    def flow_stats_reply_handler(self, ev):

        msg = ev.msg

        # Only s1 contains the DNS service rules.
        if msg.datapath.id != SERVICE_SWITCH_ID:
            return

        if self.backend_ip != PRIMARY_IP:
            return

        request_packets = None
        response_packets = None

        for stat in msg.body:

            match = stat.match

            if (
                match.get("ipv4_dst") == PRIMARY_IP
                and match.get("udp_dst") == DNS_PORT
            ):
                request_packets = stat.packet_count

            elif (
                match.get("ipv4_src") == PRIMARY_IP
                and match.get("udp_src") == DNS_PORT
                and match.get("ipv4_dst") == CLIENT_IP
            ):
                response_packets = stat.packet_count

        if request_packets is None or response_packets is None:
            return

        pending = request_packets - response_packets

        if pending > 0:
            self._bad_intervals += 1

            LOG.warning(
                "Primary DNS may be unresponsive: "
                "requests=%d responses=%d bad_intervals=%d",
                request_packets,
                response_packets,
                self._bad_intervals
            )
        else:
            self._bad_intervals = 0

        if self._bad_intervals >= 3:

            LOG.error("Primary DNS appears unhealthy; switching to backup")

            self.backend_ip = BACKUP_IP
            self._reset_health_tracking()

            dp = self.datapaths.get(SERVICE_SWITCH_ID)

            if dp is not None:
                self._install_dns_rules(dp, self.backend_ip)

            LOG.warning(
                "Automatic failover completed: backend=%s",
                self.backend_ip
            )

    def _control_loop(self):

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        try:
            sock.bind((CONTROL_IP, CONTROL_PORT))
            sock.settimeout(1.0)

            LOG.info(
                "Control socket listening on %s:%d",
                CONTROL_IP,
                CONTROL_PORT
            )

            while True:

                try:
                    data, _ = sock.recvfrom(1024)
                except socket.timeout:
                    continue

                command = data.decode(
                    "utf-8", "replace"
                ).strip().upper()

                if command == "BACKEND PRIMARY":
                    self.backend_ip = PRIMARY_IP

                elif command == "BACKEND BACKUP":
                    self.backend_ip = BACKUP_IP

                else:
                    LOG.warning("Unknown control command: %r", command)
                    continue

                self._reset_health_tracking()

                dp = self.datapaths.get(SERVICE_SWITCH_ID)

                if dp is not None:
                    self._install_dns_rules(dp, self.backend_ip)

                LOG.info(
                    "Dynamic backend changed to %s",
                    self.backend_ip
                )

        finally:
            sock.close()

    @set_ev_cls(
        ofp_event.EventOFPPacketIn,
        MAIN_DISPATCHER
    )
    def packet_in_handler(self, ev):

        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        in_port = msg.match.get("in_port")

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        dpid = dp.id
        self.mac_to_port.setdefault(dpid, {})

        src = eth.src.lower()
        dst = eth.dst.lower()

        # Learn the source MAC address on this switch.
        self.mac_to_port[dpid][src] = in_port

        # ARP packets are flooded for address resolution.
        if eth.ethertype == 0x0806:
            actions = [
                parser.OFPActionOutput(ofp.OFPP_FLOOD)
            ]

        else:
            # Look up the destination MAC on this switch.
            out_port = self.mac_to_port[dpid].get(dst)

            if out_port is None:
                out_port = ofp.OFPP_FLOOD

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            # Install a learned forwarding rule for known destinations.
            if out_port != ofp.OFPP_FLOOD:

                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=dst
                )

                self._add_flow(
                    dp,
                    10,
                    match,
                    actions,
                    idle_timeout=60
                )

        # Forward the packet.
        if msg.buffer_id != ofp.OFP_NO_BUFFER:

            out = parser.OFPPacketOut(
                datapath=dp,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions
            )

        else:

            out = parser.OFPPacketOut(
                datapath=dp,
                buffer_id=ofp.OFP_NO_BUFFER,
                in_port=in_port,
                actions=actions,
                data=msg.data
            )

        dp.send_msg(out)
