# Home Network Monitoring & Automation Platform

A segmented home lab network with VLANs, firewall rules, and a custom-built
monitoring stack that tracks device status, bandwidth, and uptime — built to
apply networking fundamentals and full-stack development in one project.

## Overview

<!-- 2-4 sentences: what you built, why, and the key technologies. Example:
This project simulates a small enterprise network at home, using OPNsense
for routing and firewalling, a managed switch for VLAN segmentation, and a
Python/React monitoring stack to visualize network health in real time. -->

## Architecture

<!-- Embed your "after" diagram here -->
![Network Diagram](docs/network-diagram-after.png)

**Stack:** OPNsense · Kea DHCP · VLANs · Python · React · Docker · SQLite/PostgreSQL

## Skills Demonstrated

- Network segmentation across dedicated physical links per VLAN
  (originally designed and verified as a single 802.1Q tagged trunk; see
  Lessons Learned for why the as-built design moved to per-VLAN links)
- Firewall rule design (least-privilege between segments, verified end to end
  on real physical client hardware for every VLAN)
- DHCP configuration per subnet (Kea DHCPv4)
- Full-stack monitoring application (Python backend, React dashboard)
- Containerization with Docker / Docker Compose
- Network troubleshooting and traffic verification (nmap, Wireshark, tcpdump)
- Systematic root-cause isolation using packet captures at every hop
  (client → switch → hypervisor → VM → WAN), distinguishing config bugs
  from hypervisor/host-platform limitations
- Systematic debugging of misconfigurations, including a service port
  conflict traced at the OS socket level (see `docs/testing-log.md`)

## Network Design

| VLAN | Name | Subnet | Gateway | Purpose |
|---|---|---|---|---|
| 1 | Default (home network) | 192.168.50.0/24 | 192.168.50.1 | Existing router, desktop, switch mgmt |
| 10 | Trusted | 10.10.10.0/24 | 10.10.10.1 | Main lab machines |
| 20 | IoT | 10.10.20.0/24 | 10.10.20.1 | Untrusted devices |
| 30 | Lab | 10.10.30.0/24 | 10.10.30.1 | Experiments, test VMs |

Full plan: [`docs/ip-vlan-plan.md`](docs/ip-vlan-plan.md)

## Firewall Policy Summary — implemented and verified

- **Trusted** → unrestricted outbound and to other VLANs
- **IoT** → DNS to its own gateway, internet access, blocked from all
  private (RFC1918) ranges including other VLANs
- **Lab** → same policy as IoT, scoped to its own subnet

Verified end-to-end on real physical client hardware for all three VLANs
(Trusted, IoT, Lab): correct DHCP leasing, DNS resolution, internet
reachability, and blocking of cross-VLAN/gateway traffic all confirmed. See
[`docs/testing-log.md`](docs/testing-log.md) for full results.

## Progress

- [x] Phase 1 — Network design (IP/VLAN plan, diagrams)
- [x] Phase 2 — OPNsense VM + VLAN interfaces + Kea DHCPv4 configured
- [x] Phase 2b — Physical switch wired, 802.1Q trunk live, firewall rules
      built and verified end to end with a VLAN-tagged test client
- [x] Phase 2c — Real standalone physical client test on switch access
      ports, confirmed on all three VLANs (Trusted, IoT, Lab) with separate
      spare-laptop test devices. The original single-trunk (802.1Q tagged)
      design was abandoned after a VirtualBox host-bridging limitation made
      tagged traffic undeliverable to the guest (see Lessons Learned); the
      as-built network instead gives each VLAN its own dedicated untagged
      physical link into OPNsense. See `docs/testing-log.md` for full
      results.
- [x] Phase 3 — Monitoring backend (Python collector, SQLite) — complete (`collector/`): 19 unit tests pass, and a live run on the lab recorded device and internet checks plus OPNsense firewall events received over remote syslog
- [x] Phase 4 — React dashboard + alerting — complete: FastAPI API, React dashboard (`dashboard/`) and alert engine with 38 unit tests; running on the lab, where it caught and later cleared two real gateway-offline alerts (see Lessons Learned). Discord webhook delivery not yet tested
- [ ] Phase 5 — Config backup automation + final documentation

## Setup / Reproduction

<!-- Fill in as each phase is completed. Example:
1. Clone this repo
2. Import `configs/opnsense/config-backup-*.xml` into a fresh OPNsense install
3. `docker compose up -d` to start the monitoring stack
4. Visit `http://localhost:3000` for the dashboard -->

## Testing & Verification

- VLAN interfaces (Trusted/IoT/Lab) created, corrected, and confirmed up
- Kea DHCPv4 subnets configured and bound to all VLAN interfaces
- Firewall isolation policy (DNS + internet allowed, all private ranges
  blocked) verified for IoT and Lab using a VLAN-tagged VM test client over
  the original trunk design, then re-verified end-to-end on **real
  physical client hardware** after the pivot to per-VLAN untagged links —
  Trusted, IoT, and Lab all confirmed: correct DHCP lease, own-gateway/
  cross-VLAN traffic blocked as designed, internet + DNS working
- A genuine VirtualBox host-bridging limitation (tagged 802.1Q frames
  confirmed via Wireshark reaching the host NIC but never reaching the
  guest VM) was root-caused and worked around by redesigning the physical
  topology — see Lessons Learned

Full log: [`docs/testing-log.md`](docs/testing-log.md)

## Lessons Learned / Troubleshooting

- **Problem:** Two of three VLANs were tagged on the WAN parent interface
  instead of LAN. **Fix:** Verified and corrected the parent interface for
  each VLAN under Interfaces > Devices > VLAN.
- **Problem:** Kea DHCPv4 subnets were configured but not handing out
  leases. **Fix:** Kea requires interfaces to be explicitly bound under
  Settings, separate from defining subnet pools.
- **Problem:** A bridged VM's tagged DHCP requests reached OPNsense (per
  `tcpdump`) but got no response. **Fix:** Found via `sockstat` that
  Dnsmasq had silently claimed port 67 on every interface, blocking Kea
  from binding anywhere — disabled Dnsmasq's DHCP and consolidated
  everything onto Kea.
- **Problem:** Initial firewall isolation tests appeared to pass when they
  should have been blocked. **Fix:** The test client had multiple active
  interfaces and was routing pings out the wrong one by default; re-ran
  with `ping -I <interface>` to force traffic out the correct VLAN.
- **Problem (major, architectural):** With a real physical client plugged
  into a switch access port, 802.1Q-tagged frames were confirmed via
  host-side Wireshark to arrive intact at the host's physical NIC, but
  never appeared on OPNsense's bridged VLAN sub-interfaces inside the VM —
  with every standard fix (Promiscuous "Allow All," correct adapter
  selection, full VM power-cycle, NIC offloads disabled) ruled out. This
  pointed to a VirtualBox-on-Windows limitation in relaying tagged frames
  across the bridge, not a configuration error. **Fix:** Abandoned the
  single tagged-trunk design entirely. Redesigned the topology so each
  VLAN gets its own dedicated **untagged** physical link from a separate
  host NIC (two added USB-to-Ethernet adapters) into its own switch port,
  each bridged individually into its own OPNsense interface — eliminating
  VLAN tagging from the host-to-switch path altogether. Required
  reconfiguring the switch's port/VLAN table, re-bridging VirtualBox
  adapters, and reassigning OPNsense interfaces directly onto the physical
  NICs (no more `vlan0.x` sub-interfaces). Full walkthrough in
  `docs/testing-log.md`.
- **Problem:** After the topology rebuild, two of the new USB adapters were
  bridged to the wrong physical switch ports in VirtualBox (Adapter 3/4
  swapped), so testing IoT returned a Lab address and vice versa. **Fix:**
  Diagnosed via switch port-statistics Clear-and-retry (isolating exactly
  which physical port was carrying live traffic), then swapped the two
  adapters' "Name" bindings in VirtualBox Settings > Network.
- **Problem:** The Lab VLAN passed DHCP and correctly blocked gateway/
  cross-VLAN traffic, but internet/DNS appeared to fail with zero firewall
  log entries. **Cause:** Not a connectivity or rule problem — the Lab
  rules simply didn't have logging enabled, and `tcpdump` on OPNsense's
  interfaces confirmed traffic was arriving and being processed normally.
  The actual DNS/ping failures were a backlog of stale, retried
  connections saturating VirtualBox's shared NAT engine from earlier
  testing. **Fix:** None needed on the config side — closing stale
  retry loops cleared it.
- **Problem:** The host laptop itself (also running the hypervisor) lost
  internet on its own wired Trusted connection whenever OPNsense was
  powered on. **Cause:** Several stacked issues — a leftover static IP
  from earlier GUI-access troubleshooting with no gateway set; and more
  fundamentally, the host is simultaneously a DHCP client on all three
  VLANs at once (each bridged physical NIC is also a normal Windows
  adapter), so Windows was routing general internet traffic out the wrong
  VLAN's gateway. **Fix:** Reset the adapter to DHCP, then set a higher
  (lower-priority) interface metric on the IoT/Lab-bridged adapters so
  Windows always prefers the Trusted adapter's route for general traffic.
- **Problem:** Even after the above, the host's internet through OPNsense
  remained unreliable (high jitter, intermittent full packet loss),
  including when pinging straight from OPNsense's own console. **Cause:**
  Windows' Memory Integrity / Core Isolation (Virtualization-Based
  Security) was enabled, which forces VirtualBox to run on top of
  Windows' own Hypervisor Platform instead of its native hypervisor —  a
  well-documented cause of degraded/unreliable VirtualBox networking.
  **Fix:** Disabled Memory Integrity (Windows Security > Device security >
  Core isolation) and rebooted, which measurably improved reliability
  (0% packet loss vs. consistent failures beforehand).
- **Note (not a bug):** Residual latency/jitter on the host's own direct
  internet path traced to the home ISP itself being Verizon 5G Home
  Internet (fixed wireless/cellular), stacked with double NAT (VirtualBox's
  software NAT for OPNsense's WAN, then OPNsense's own NAT for Trusted
  clients). This is an inherent characteristic of the WAN medium, not a
  configuration issue — confirmed by OPNsense's own WAN-side ping tests
  and a full traceroute successfully reaching `8.8.8.8` through the
  carrier network.

- **The monitor flagged a "failure" that was my own firewall policy.** The
  dashboard showed the IoT and Lab gateways offline while DNS through them
  worked. The `block private network` rules (RFC1918 includes each
  gateway's own address) silently dropped the monitoring host's pings, and
  because those rules had logging off, Live View showed nothing. Turning
  logging on exposed the `block` hits at once. Fix: a narrow, logged pass
  rule above each block rule (ICMP echo from the monitoring host only, to
  This Firewall). Lesson: a block rule without logging is invisible, and an
  empty log is not proof that no traffic arrived.
- **A switch VLAN setting leaked the home LAN into IoT.** Firewall logs
  showed `192.168.50.x` broadcast and multicast arriving on the IoT
  interface. On the TL-SG108E, ports 3-7 were still untagged members of
  VLAN 1 as well as their own VLAN, so VLAN 1 traffic left through them.
  Removing them (VLAN 1 on ports 1-2 only, after confirming every PVID)
  ended it. Lesson: check PVID *and* membership, and save the switch config.
- **The monitor was measuring the wrong internet path.** A third USB
  adapter connected the host straight to the home router and tied the
  Trusted adapter's route metric, so Windows sent the collector's internet
  pings around OPNsense. Setting the Trusted adapter's metric lowest
  (10, with the home-router adapter at 40 as a backup) put the checks back
  on the OPNsense WAN. Earlier internet figures are not a clean baseline.

Full details: [`docs/testing-log.md`](docs/testing-log.md)

## Roadmap

- Pi-hole or Unbound for VLAN-aware DNS filtering
- WireGuard VPN for remote access
- Automated OPNsense config backups
- Basic anomaly alerting (Discord/email)

