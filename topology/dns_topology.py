from mininet.topo import Topo

class DistributedDNSTopo(Topo):
    def build(self):
        # Create hosts
        client = self.addHost(
            "client",
            ip="10.0.0.2/24",
            mac="00:00:00:00:00:01"
        )

        dns1 = self.addHost(
            "dns1",
            ip="10.0.0.3/24",
            mac="00:00:00:00:00:02"
        )

        dns2 = self.addHost(
            "dns2",
            ip="10.0.0.4/24",
            mac="00:00:00:00:00:03"
        )

        # Create three Open vSwitch switches
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")
        s3 = self.addSwitch("s3", protocols="OpenFlow13")

        # Connect hosts to switches
        self.addLink(client, s1)
        self.addLink(dns1, s2)
        self.addLink(dns2, s3)

        # Connect switches in a linear topology
        self.addLink(s1, s2)
        self.addLink(s2, s3)


topos = {"dns": lambda: DistributedDNSTopo()}
