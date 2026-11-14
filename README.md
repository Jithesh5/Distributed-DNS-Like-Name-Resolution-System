# Distributed DNS-Like Name Resolution System with SDN-Based Backend Selection

A DNS-like name-resolution service written in C (UDP sockets) and run inside a Mininet network of three Open vSwitch switches. A Python OS-Ken controller (OpenFlow 1.3) redirects queries sent to one virtual service address to either a primary or a backup DNS server, and rewrites replies so the client never sees which backend answered.

This is an educational prototype. It does not implement the DNS standard (no recursion, record types, binary wire format or authoritative zones).

**Repository:** https://github.com/Jithesh5/Distributed-DNS-Like-Name-Resolution-System

## Team

| Name | SRN |
|---|---|
| Jithesh Shetty | PES2UG25CS650 |
| Yavanika Y Mutta | PES2UG25CS619 |
| Zaki U Rehaman | PES2UG25CS623 |

## Status at a glance

| Feature | Status |
|---|---|
| UDP request/response resolution (primary and backup servers) | Working |
| Virtual service address with OpenFlow rewrite (request and response) | Working |
| Manual backend selection (`BACKEND PRIMARY` / `BACKEND BACKUP`) | Working |
| Client cache (TTL), 1 s timeout with one retry, multi-server fallback, CSV log | Working |
| Linear three-switch topology (`s1 - s2 - s3`) | Working |
| **Automatic failover** | **Not completed** (see [Limitations](#limitations)) |
| Automatic failback | Not implemented |

## Architecture

Three hosts, three switches in a line, one remote controller.

```text
                 OS-Ken controller (OpenFlow 1.3, tcp/6653)
                   |           |           |
    client ------ s1 --------- s2 -------- s3
   10.0.0.2      (port 2 is   |            |
   (s1 port 1)    the uplink) dns1         dns2
                             10.0.0.3     10.0.0.4
                             primary      backup

   Virtual DNS service address seen by the client: 10.0.0.3 : UDP 5300
   Controller control socket (same host as controller): 127.0.0.1 : UDP 9999
```

| Node | Mininet name | IP | MAC | Switch | Role |
|---|---|---|---|---|---|
| Client | `client` | 10.0.0.2 | 00:00:00:00:00:01 | s1 | Sends queries |
| Primary DNS | `dns1` | 10.0.0.3 | 00:00:00:00:00:02 | s2 | Default backend |
| Backup DNS | `dns2` | 10.0.0.4 | 00:00:00:00:00:03 | s3 | Standby backend |

The virtual service address `10.0.0.3` is also the primary server's real address. With the primary selected the destination rewrite is an identity rewrite; with the backup selected it becomes `10.0.0.4`.

### Request and response path

1. The client sends `QUERY <domain>` over UDP to `10.0.0.3:5300`.
2. On `s1`, a priority-200 rule matches IPv4 UDP traffic to `10.0.0.3:5300`, rewrites the destination IP and MAC to the selected backend, and outputs on the uplink (port 2).
3. The packet is forwarded through `s2` (and `s3` for the backup) by MAC-learning rules and reaches the server.
4. The server replies `OK <ip> <ttl>` or `NOT_FOUND - 0`.
5. A priority-200 rule on `s1` matches UDP source port 5300 from the selected backend to `10.0.0.2`, rewrites the source IP back to `10.0.0.3`, and outputs on the client port (port 1).
6. The client prints the result, caches successful answers for the TTL, and appends a CSV record.

### Controller behaviour

- Every switch gets a priority-0 table-miss rule that sends packets to the controller. A packet-in handler learns MAC addresses, floods ARP and unknown destinations, and installs priority-10 forwarding rules (idle timeout 60 s).
- Switch `s1` (datapath ID 1) also gets the two DNS rules, tagged with cookie `0xD15D0001` so they can be deleted and reinstalled as a group when the backend changes.
- A control thread listens on UDP `127.0.0.1:9999` for `BACKEND PRIMARY` and `BACKEND BACKUP`.
- An experimental flow-statistics check also exists in the code (see Limitations). It is not a working feature.

## Repository structure

```text
Distributed_DNS_SDN_Final_Project/
├── Makefile
├── README.md
├── client/client.c                    UDP client: cache, timeout/retry, fallback, CSV log
├── servers/server.c                   UDP DNS-like server
├── controller/dns_sdn_controller.py   OS-Ken OpenFlow 1.3 controller
├── topology/dns_topology.py           Mininet topology "dns"
├── data/
│   ├── server1.map                    Primary mapping file
│   └── server2.map                    Backup mapping file
├── scripts/
│   ├── generate_evaluation.py         Builds results/evaluation_summary.md and latency_by_test.png
│   └── run_stage3.sh                  Launcher (edit PROJECT_DIR first)
├── tests/manual_test.sh               Builds the project and prints run instructions
└── results/                           Recorded CSV runs, evaluation summary, latency chart
```

`dns_client` and `dns_server` are produced by `make`.

## Application protocol

Plain text over UDP, 512-byte maximum, port 5300.

| Direction | Message | Meaning |
|---|---|---|
| Client to server | `QUERY <domain>` | Resolve a name |
| Server to client | `OK <ip> <ttl>` | Found (the server always sends TTL 10) |
| Server to client | `NOT_FOUND - 0` | Name not in the mapping file |
| Server to client | `BAD_REQUEST - 0` | Malformed request |
| Server to client | `ERROR 0` | Mapping file could not be opened |

## Mapping data

| Domain | `server1.map` (primary) | `server2.map` (backup) |
|---|---|---|
| `www.college.local` | 10.0.0.10 | 10.0.0.10 |
| `library.college.local` | 10.0.0.11 | 10.0.0.11 |
| `portal.college.local` | 10.0.0.12 | not present |
| `backup.college.local` | not present | 10.0.0.13 |
| `google.com` | 142.250.195.14 | 142.250.195.14 |
| `youtube.com` | 142.250.72.14 | 142.250.72.14 |

`portal.college.local` (primary only) and `backup.college.local` (backup only) prove which server is answering. The server re-reads its map file on every query, so edits apply without a restart.

## Client behaviour

Usage: `./dns_client <log.csv> <server-ip> <server-port> [<server-ip> <server-port> ...]` (up to 8 servers).

- **Cache:** 128 entries, TTL taken from the server reply (10 s). `NOT_FOUND` is not cached.
- **Timeout and retry:** 1-second receive timeout, two attempts per server. A fully failed lookup therefore takes about 2 s.
- **Fallback:** if a server fails or answers `NOT_FOUND`, the next configured server is tried. Outcomes: `OK`, `NOT_FOUND`, `ALL_SERVERS_FAILED`.
- **Server label:** when only the virtual address is given, every answer is labelled `SERVER1`. Identify the real backend by the data returned.
- **CSV columns:** `domain,status,source,latency_ms,server_number` (cache hits are logged as `CACHE`, 0 ms, server number 0).

## Requirements

Ubuntu, native or under WSL2, with Mininet and Open vSwitch working.

```bash
sudo apt update
sudo apt install -y build-essential make python3 python3-pip python3-venv \
    mininet openvswitch-switch netcat-openbsd

python3 -m venv ~/osken-controller-venv
source ~/osken-controller-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install os-ken
```

Optional, for the evaluation graph: `python -m pip install matplotlib`.

## Build

From the project root:

```bash
make clean && make
```

This produces `dns_client` and `dns_server` with `-Wall -Wextra -Wpedantic -O2`.

## Run the demonstration

Use three Ubuntu terminals plus the Mininet prompt. Run everything from the project root, and start the controller **before** Mininet.

**Terminal 1: controller**

```bash
cd ~/path/to/Distributed_DNS_SDN_Final_Project
source ~/osken-controller-venv/bin/activate
osken-manager --ofp-tcp-listen-port 6653 controller/dns_sdn_controller.py
```

Expected: `Control socket listening on 127.0.0.1:9999`, then `Switch 1 connected`, `Switch 2 connected`, `Switch 3 connected`, and `DNS rules installed on s1: 10.0.0.3 -> 10.0.0.3`.

**Terminal 2: Mininet**

```bash
sudo mn -c
sudo mn --custom topology/dns_topology.py --topo dns \
    --controller=remote,ip=127.0.0.1,port=6653 \
    --switch ovsk,protocols=OpenFlow13
```

At the `mininet>` prompt:

```text
pingall
dns1 ./dns_server 5300 ./data/server1.map &
dns2 ./dns_server 5300 ./data/server2.map &
```

Expected: `0% dropped`, and each server prints `UDP resolver listening on port 5300 using ...`.

**Terminal 3: backend control (ordinary Ubuntu shell, not the Mininet prompt)**

```bash
echo -n 'BACKEND PRIMARY' | nc -u -w 1 127.0.0.1 9999
```

**Start the client** at the `mininet>` prompt, with a fresh CSV for this run:

```text
client ./dns_client ./results/final_demo.csv 10.0.0.3 5300
```

Avoid arrow keys at the `dns>` prompt; they are logged as junk rows.

### Demo scenarios

| # | Scenario | Action | Expected result |
|---|---|---|---|
| 1 | Primary resolution | Backend PRIMARY. Enter `www.college.local`, then `portal.college.local` | `status=OK`, IPs `10.0.0.10` and `10.0.0.12`; `dns1` console shows both queries |
| 2 | Unknown name | Enter `unknown.college.local` | `status=NOT_FOUND` |
| 3 | Client cache | Enter `www.college.local` twice within 10 s | Second result shows `source=CACHE latency_ms=0.000` |
| 4 | Cache expiry | Wait over 10 s, enter `www.college.local` again | Server lookup again (`source=SERVER1`) |
| 5 | Manual switch to backup | Terminal 3: `echo -n 'BACKEND BACKUP' \| nc -u -w 1 127.0.0.1 9999`. Client: `backup.college.local` | `status=OK ip=10.0.0.13`; `dns2` console shows the query; controller logs `Dynamic backend changed to 10.0.0.4` |
| 6 | Primary rejects backup-only name | `BACKEND PRIMARY`, then enter `backup.college.local` | `NOT_FOUND` (proves the primary is serving) |
| 7 | Timeout and retry | Quit the client, run `dns1 pkill dns_server`, restart the client, enter `www.college.local` | `timed out; retrying once`, then `ALL_SERVERS_FAILED` after about 2,000 ms |
| 8 | Restore | `dns1 ./dns_server 5300 ./data/server1.map &`, then `BACKEND PRIMARY` | Primary serves again; recovery is manual |

Automatic failover is deliberately not part of the demonstration because it is not completed.

Exit the client with `quit`.

### Verify the OpenFlow rules

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
sudo ovs-ofctl -O OpenFlow13 dump-flows s2
sudo ovs-ofctl -O OpenFlow13 dump-flows s3
```

On `s1`, two priority-200 rules with cookie `0xd15d0001` should exist. After scenario 5 the request rule contains `set_field:10.0.0.4->ip_dst` and `set_field:00:00:00:00:00:03->eth_dst`, and packet counters grow with each query.

### Evidence to keep

Save the controller log, both server consoles, `dump-flows s1` before and after the backend switch, and the new `results/final_demo.csv`. Then regenerate the report:

```bash
python3 scripts/generate_evaluation.py
```

This writes `results/evaluation_summary.md` and `results/latency_by_test.png`.

## Test results

Figures come from the CSV files in `results/`. They are small samples from separate runs, not a controlled benchmark. Rows with escape sequences in the domain column (from arrow-key presses) are excluded.

| Scenario | Source file(s) | Samples | Latency |
|---|---|---:|---|
| Client cache hit | `final_test`, `demo_cache`, `lookups` | 3 | 0.000 ms |
| Direct, no SDN | `direct_test` | 3 | 0.502 to 1.558 ms |
| SDN primary, two-switch stage | `stage3_primary_test` | 7 | 0.048 to 2.760 ms, mean about 1.31 ms |
| SDN backup, two-switch stage | `stage3_backup_test` | 5 | 0.403 to 2.326 ms, mean about 1.61 ms |
| SDN primary, three switches | `three_switch_primary` | 2 | 9.150 ms (first query), 0.766 ms |
| SDN backup, three switches | `three_switch_backup`, `three_switch_backup_verification`, `demo_backup` | 3 | 7.620 to 7.934 ms |
| Server unreachable (timeout) | `timeout_test`, `demo_timeout`, `demo_primary` | 6 | 2,026 to 2,074 ms |

Observations:

- A cache hit costs 0 ms against about 0.5 to 2 ms for a server lookup.
- The first query after rules change is slower (7 to 9 ms in the three-switch runs), consistent with ARP and packet-in handling.
- Backup lookups across three switches take about 7.6 to 7.9 ms; these are single queries, so the difference from the primary is indicative only.
- Every `ALL_SERVERS_FAILED` result is about 2 s, equal to two 1-second timeouts. These dominate the overall mean in `evaluation_summary.md` (118 ms mean against a 1.43 ms median).
- `generate_evaluation.py` reports 5 records for `stage3_primary_test.csv`, which contains 7; the table above uses the file's actual rows.

## Limitations

1. **Automatic failover is not completed.** The controller contains an experimental health check: once per second it compares the request-rule and response-rule packet counters on `s1`, and after 3 consecutive intervals with more requests than responses it is meant to switch to the backup. This was not demonstrated working end to end and no recorded result proves it, so it is not claimed as a feature. Backend switching works only manually with `BACKEND PRIMARY` and `BACKEND BACKUP`. If the primary fails, the client gets `ALL_SERVERS_FAILED` after about 2 s until an operator switches the backend.
2. **The health-check design is weak.** Counters are cumulative, so one lost reply leaves requests above responses permanently and could trigger a false failover of a healthy primary. The check runs only while the primary is selected and detects nothing when no requests are sent.
3. **No automatic failback.** Restoring the primary needs a manual `BACKEND PRIMARY`.
4. **Junk CSV rows.** Arrow keys at the `dns>` prompt write escape sequences as domain names in `demo_cache.csv`, `demo_primary.csv`, `demo_timeout.csv` and `stage3_backup_test.csv`.
5. **Hard-coded assumptions.** Datapath ID 1 is `s1`; client port 1, uplink port 2; IPs and MACs fixed to the Mininet topology.
6. **Server design.** Single-threaded, re-reads the mapping file per query, fixed TTL of 10 s.
7. **Not real DNS.** Text protocol, no recursion, record types or security.
8. **Launcher path.** `scripts/run_stage3.sh` hard-codes `$HOME/Downloads/distributed_dns_sdn_stage2`; edit `PROJECT_DIR` before using it.

## Troubleshooting

| Problem | Fix |
|---|---|
| Mininet reports stale state | Exit Mininet, run `sudo mn -c`, restart the controller and topology |
| Controller does not start | `source ~/osken-controller-venv/bin/activate`, check `osken-manager --help`, make sure port 6653 is free |
| Switches do not connect | Start the controller first; use port 6653 in both places and `protocols=OpenFlow13` |
| Client times out | Confirm both servers run on port 5300, the client targets `10.0.0.3 5300`, and `dump-flows s1` shows the DNS rules |
| `BACKEND` command has no effect | Run `nc` from the same Ubuntu environment as the controller; it listens on `127.0.0.1:9999` |
| Build fails | `make clean && make` from the project root |
| Python syntax check | `python3 -m py_compile controller/dns_sdn_controller.py topology/dns_topology.py scripts/generate_evaluation.py` (no output means success) |

## Future work

- Complete automatic failover with active health probes (a periodic test query from the controller) and per-interval counter deltas.
- Automatic failback with hysteresis.
- A measured failover-time test: primary failure to first successful backup answer.
- Repeated trials per scenario (for example 30 queries) with mean, median and a percentile.
- Configurable TTL and cache statistics.
- Automated integration tests using the Mininet Python API.

