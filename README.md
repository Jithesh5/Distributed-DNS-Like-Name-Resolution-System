# Distributed DNS-Like Name Resolution System

A distributed DNS-like name-resolution system implemented in C using UDP sockets, Mininet, Open vSwitch (OVS), and an OS-Ken SDN controller.

The project demonstrates hostname-to-IP resolution through primary and backup DNS servers, client-side caching, timeout and retry handling, SDN-based backend selection, flow-statistics-based failover, and lookup-latency measurement.

This is an educational DNS-like prototype. It does not implement the complete DNS standard.

## 1. Project Objectives

- Resolve domain names using a lightweight UDP request/response protocol.
- Run a client, a primary DNS server, and a backup DNS server in a Mininet network.
- Maintain separate hostname-to-IP mapping files for the primary and backup servers.
- Use a virtual DNS service address so the client does not need to know which backend is active.
- Use Open vSwitch with OpenFlow 1.3.
- Use an OS-Ken controller to redirect DNS requests to the selected backend.
- Rewrite DNS response source addresses so clients see the virtual service address.
- Support manual primary/backup selection through a controller control socket.
- Monitor OpenFlow statistics and attempt automatic failover when the primary appears unresponsive.
- Cache successful responses on the client using a TTL.
- Record lookup outcomes and latency in CSV files for evaluation.

## 2. Technologies Used

- C
- GCC and Make
- UDP sockets
- Python 3
- Mininet
- Open vSwitch (OVS)
- OS-Ken SDN controller
- OpenFlow 1.3
- Netcat (`nc`) for backend selection
- Matplotlib for evaluation graphs
- Ubuntu / Ubuntu under WSL2

## 3. Project Architecture

The Mininet topology contains three hosts connected through three Open vSwitches arranged in a linear topology.

```text
                       OS-Ken SDN Controller
                         OpenFlow 1.3
                               |
                               |
                         +-----------+
                         |    s1     |
                         | Client SW |
                         +-----------+
                          /         \
                         /           \
                  +-----------+   +-----------+
                  |    s2     |---|    s3     |
                  | Primary   |   | Backup    |
                  | DNS path  |   | DNS path  |
                  +-----------+   +-----------+
                       |                |
                     dns1              dns2
                  10.0.0.3          10.0.0.4
                   Primary           Backup

                       client
                    10.0.0.2
                  connected to s1
```

The switches are connected in a line: `s1 - s2 - s3`. The client is attached to `s1`, the primary DNS server is attached to `s2`, and the backup DNS server is attached to `s3`.

### Network components

| Component | Mininet host | IP address | Role |
|---|---|---|---|
| Client | `client` | `10.0.0.2` | Sends DNS-like queries |
| Primary DNS server | `dns1` | `10.0.0.3` | Primary name-resolution backend |
| Backup DNS server | `dns2` | `10.0.0.4` | Backup name-resolution backend |
| Virtual DNS service | — | `10.0.0.3` | Address used by the client |
| DNS service port | — | UDP `5300` | Query/response communication |

The controller connects to the switches using OpenFlow 1.3. The DNS service rules are installed on the client-facing switch, `s1`.

### Hostname mappings

Primary server (`data/server1.map`):

| Domain | Resolved IP |
|---|---|
| `www.college.local` | `10.0.0.10` |
| `library.college.local` | `10.0.0.11` |
| `portal.college.local` | `10.0.0.12` |

Backup server (`data/server2.map`):

| Domain | Resolved IP |
|---|---|
| `www.college.local` | `10.0.0.10` |
| `library.college.local` | `10.0.0.11` |
| `backup.college.local` | `10.0.0.13` |

The `backup.college.local` entry is useful for checking that the backup server is handling requests.

### How the system works

1. The client sends a UDP request in the format `QUERY <domain>` to the virtual DNS service address `10.0.0.3` on port `5300`.
2. The packet reaches switch `s1`.
3. The OpenFlow DNS request rule on `s1` matches IPv4 UDP traffic destined for `10.0.0.3:5300`.
4. Based on the controller's selected backend, the rule rewrites the destination IP and destination Ethernet MAC address, then forwards the packet toward the server-side network.
5. The selected DNS server looks up the domain in its mapping file.
6. The server responds with `OK <ip> <ttl>` if the domain exists, or `NOT_FOUND - 0` if it does not.
7. The response rule on `s1` rewrites the response source IP to the virtual service address `10.0.0.3` and forwards it to the client.
8. The client displays the result and stores successful answers in its local cache until the TTL expires.

### SDN backend selection and failover

The controller initially selects the primary backend (`10.0.0.3`). It listens for UDP control commands on `127.0.0.1:9999`:

- `BACKEND PRIMARY` selects the primary DNS server.
- `BACKEND BACKUP` selects the backup DNS server.

The controller also polls DNS-related OpenFlow flow statistics approximately once per second. While the primary is selected, it compares request and response packet counters. If requests appear to exceed responses for three consecutive polling intervals, it attempts to switch the DNS service rules to the backup server.

**Important limitation:** This is a flow-statistics-based health heuristic, not a guaranteed health check. It can miss failures or produce false positives. The controller does not automatically fail back to the primary; use the manual `BACKEND PRIMARY` command to restore it.

## 4. Repository Structure

```text
Distributed_DNS_SDN_Final_Project/
├── Makefile
├── README.md
├── README_STAGE3.md
├── client/
│   └── client.c
├── servers/
│   └── server.c
├── controller/
│   └── dns_sdn_controller.py
├── topology/
│   └── dns_topology.py
├── data/
│   ├── server1.map
│   └── server2.map
├── tests/
│   └── manual_test.sh
├── scripts/
│   ├── run_stage3.sh
│   └── generate_evaluation.py
├── results/
│   ├── *.csv
│   ├── evaluation_summary.md
│   └── latency_by_test.png
├── dns_client
└── dns_server
```

The compiled executables `dns_client` and `dns_server` are generated by `make`. If they are not present or need to be rebuilt, follow the build instructions below.

## 5. Requirements and Installation

Use Ubuntu or Ubuntu under WSL2. Run Mininet and Open vSwitch in an environment where they are installed and operational.

Install the required system packages:

```bash
sudo apt update
sudo apt install -y build-essential make python3 python3-pip python3-venv \
    mininet openvswitch-switch netcat-openbsd
```

Verify the main tools:

```bash
gcc --version
make --version
python3 --version
mn --version
ovs-vsctl --version
```

### Set up OS-Ken

Create and activate a Python virtual environment if you do not already have one:

```bash
python3 -m venv ~/osken-controller-venv
source ~/osken-controller-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install os-ken
```

For later sessions, activate the existing environment:

```bash
source ~/osken-controller-venv/bin/activate
```

Check that the controller launcher is available:

```bash
osken-manager --help
```

### Build the C programs

From the project root directory:

```bash
make clean
make
```

This creates:

- `dns_client` — interactive UDP DNS-like client.
- `dns_server` — UDP name-resolution server.

To remove the compiled executables:

```bash
make clean
```

## 6. Running the Project

Open separate terminal windows for the controller, Mininet, and backend-control commands. Run the commands from the project root directory.

### Terminal 1: Start the SDN controller

```bash
cd ~/path/to/Distributed_DNS_SDN_Final_Project
source ~/osken-controller-venv/bin/activate
osken-manager --ofp-tcp-listen-port 6653 controller/dns_sdn_controller.py
```

Replace `~/path/to/Distributed_DNS_SDN_Final_Project` with the actual location of the project.

Keep this terminal running. The controller listens for OpenFlow switch connections on port `6653` and backend-selection commands on UDP port `9999`.

### Terminal 2: Start the Mininet topology

```bash
cd ~/path/to/Distributed_DNS_SDN_Final_Project
sudo mn --custom topology/dns_topology.py --topo dns \
    --controller=remote,ip=127.0.0.1,port=6653 \
    --switch ovsk,protocols=OpenFlow13
```

Wait for the `mininet>` prompt.

Check network connectivity:

```text
pingall
```

The expected result in a correctly working topology is that all three hosts can reach one another, with `0% dropped`.

### Start the primary DNS server

At the `mininet>` prompt:

```text
dns1 ./dns_server 5300 ./data/server1.map &
```

### Start the backup DNS server

At the `mininet>` prompt:

```text
dns2 ./dns_server 5300 ./data/server2.map &
```

Both servers should report that they are listening on UDP port `5300`.

### Terminal 3: Select the primary backend

Run this in a normal Ubuntu terminal, not at the `mininet>` prompt:

```bash
echo -n 'BACKEND PRIMARY' | nc -u -w 1 127.0.0.1 9999
```

Check the controller terminal for a message confirming that the active backend is `10.0.0.3`.

To select the backup backend:

```bash
echo -n 'BACKEND BACKUP' | nc -u -w 1 127.0.0.1 9999
```

Check the controller terminal for confirmation that the active backend is `10.0.0.4`.

## 7. Testing DNS Resolution

Run the client from the `mininet>` prompt. The client sends requests to the virtual service address `10.0.0.3`, regardless of which backend is selected.

```text
client ./dns_client ./results/manual_test.csv 10.0.0.3 5300
```

At the `dns>` prompt, enter domains one at a time.

### Test 1: Resolve a domain from the primary server

First select the primary backend from Terminal 3:

```bash
echo -n 'BACKEND PRIMARY' | nc -u -w 1 127.0.0.1 9999
```

At the client's `dns>` prompt:

```text
www.college.local
```

Expected result (the latency value will vary):

```text
RESULT domain=www.college.local status=OK ip=10.0.0.10 source=SERVER1 latency_ms=...
```

### Test 2: Resolve another primary domain

```text
portal.college.local
```

Expected result:

```text
RESULT domain=portal.college.local status=OK ip=10.0.0.12 source=SERVER1 latency_ms=...
```

### Test 3: Test an unknown domain

```text
unknown.college.local
```

Expected result:

```text
RESULT domain=unknown.college.local status=NOT_FOUND latency_ms=...
```

### Test 4: Resolve a backup-only domain

Select the backup backend from Terminal 3:

```bash
echo -n 'BACKEND BACKUP' | nc -u -w 1 127.0.0.1 9999
```

Then, at the client's `dns>` prompt:

```text
backup.college.local
```

Expected result:

```text
RESULT domain=backup.college.local status=OK ip=10.0.0.13 source=SERVER1 latency_ms=...
```

The client labels the configured destination as `SERVER1` because it is the first server in its command-line server list. The SDN controller transparently redirects that virtual service request to the selected backend.

### Test 5: Check client-side caching

Query a known domain twice in the same client session:

```text
www.college.local
www.college.local
```

The first successful lookup should come from the server. The second lookup should normally be served from the client cache and show:

```text
source=CACHE latency_ms=0.000
```

The cache entry expires according to the TTL returned by the server. In the current server implementation, successful responses use a TTL of 10 seconds.

Exit the client:

```text
quit
```

## 8. Verify OpenFlow Rules

From a normal Ubuntu terminal, inspect the flows on the switches:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
sudo ovs-ofctl -O OpenFlow13 dump-flows s2
sudo ovs-ofctl -O OpenFlow13 dump-flows s3
```

On `s1`, look for DNS service rules matching UDP destination port `5300` and the virtual service address `10.0.0.3`. The controller installs request and response rules with priority `200`.

The request rule should perform actions equivalent to:

- Rewrite the destination IPv4 address to the selected backend.
- Rewrite the destination Ethernet MAC address to the selected backend MAC.
- Forward the packet through the uplink port.

The response rule should:

- Match a response from the currently selected backend to client `10.0.0.2`.
- Rewrite the response source IPv4 address to the virtual service address `10.0.0.3`.
- Forward the response to the client-facing port.

The controller also installs a table-miss rule that sends unmatched packets to the controller. Its packet-in handler performs MAC learning and forwards ARP or unknown-destination traffic by flooding.

## 9. Evaluation and CSV Results

The client records lookup results in a CSV file. The columns are:

| Column | Description |
|---|---|
| `domain` | Queried domain name |
| `status` | `OK`, `NOT_FOUND`, or `ALL_SERVERS_FAILED` |
| `source` | Cache or server source |
| `latency_ms` | Measured lookup latency in milliseconds |
| `server_number` | Position of the responding server in the client's configured server list |

You can choose a different output CSV path when starting the client, for example:

```text
client ./dns_client ./results/primary_run.csv 10.0.0.3 5300
```

Generate or refresh the evaluation report and latency graph from the project root:

```bash
python3 scripts/generate_evaluation.py
```

The evaluation files are written to:

- `results/evaluation_summary.md`
- `results/latency_by_test.png`

The repository also contains CSV files from earlier test scenarios. These are recorded measurements from those runs; rerunning tests may produce different values.

## 10. Troubleshooting

### Mininet reports stale network state

Exit the Mininet CLI and run:

```bash
sudo mn -c
```

Then restart the controller and topology.

### The controller does not start

Activate the correct virtual environment:

```bash
source ~/osken-controller-venv/bin/activate
osken-manager --help
```

Confirm that the `os-ken` package is installed and that no other process is already using the controller port `6653`.

### Switches do not connect to the controller

- Start the controller before starting Mininet.
- Confirm that both use OpenFlow port `6653`.
- Confirm that the topology uses `protocols=OpenFlow13`.
- Check the controller terminal for switch connection messages.

### DNS client times out

- Confirm that both DNS server processes are running.
- Check that the servers are listening on UDP port `5300`.
- Confirm that the client targets `10.0.0.3` and port `5300`.
- Confirm that the controller has selected the intended backend.
- Inspect the OpenFlow rules on `s1`.
- Check controller and DNS server terminal output.

### Backend-selection command has no effect

Run the `nc` command from the same Ubuntu environment as the controller:

```bash
echo -n 'BACKEND BACKUP' | nc -u -w 1 127.0.0.1 9999
```

Make sure the controller is listening on `127.0.0.1:9999`.

### C program compilation fails

Rebuild from the project root:

```bash
make clean
make
```

### Python syntax check

```bash
python3 -m py_compile controller/dns_sdn_controller.py
python3 -m py_compile topology/dns_topology.py
python3 -m py_compile scripts/generate_evaluation.py
```

No output means the Python syntax checks passed.

## 11. GitHub Collaboration

Clone the repository using its Git URL:

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd Distributed_DNS_SDN_Final_Project
```

Pull the latest changes before starting work:

```bash
git pull
```

After making changes:

```bash
git add .
git commit -m "Describe your changes"
git push
```

Avoid committing temporary files such as Python `__pycache__` directories, virtual environments, and unnecessary generated files.

## 12. Current Project Status

The project source and results directory include:

- C source code for the UDP client and DNS-like server.
- Separate primary and backup hostname mapping files.
- A Mininet topology with three hosts and three Open vSwitch switches.
- An OS-Ken controller using OpenFlow 1.3.
- Manual primary/backup backend selection through a UDP control socket.
- Flow-statistics-based automatic failover logic.
- Client-side response caching, timeout/retry handling, and CSV logging.
- Existing CSV test measurements and an evaluation summary.
- A script for generating the latency graph and evaluation report.

Run the project in your environment and retain fresh terminal output and test CSV files as evidence for any new demonstration or evaluation. Existing result files should not be treated as proof that a test has just been rerun.

## 13. Future Improvements

- Add a dedicated active health-check mechanism instead of relying only on flow-counter differences.
- Add automatic failback to the primary server after recovery.
- Improve failover verification with repeatable failure and recovery tests.
- Add automated unit and integration tests.
- Add configurable cache TTLs and more detailed cache statistics.
- Expand the mapping data and test cases.
- Measure failover detection time and compare cache-hit, cache-miss, primary, and backup latency under controlled conditions.
- Add network topology diagrams and screenshots from a clean demonstration run.

---

**Project:** Distributed DNS-Like Name Resolution System  
**Networking:** UDP sockets, Mininet, Open vSwitch, OpenFlow 1.3  
**Controller:** OS-Ken  
**Implementation:** C client and DNS-like servers, Python SDN controller and Mininet topology
