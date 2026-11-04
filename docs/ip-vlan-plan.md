# IP & VLAN Plan

This document defines the addressing scheme, VLAN layout, and interface
mapping for the home lab network. It's the source of truth — OPNsense,
switch, and DHCP configs should all match this.

## VLAN Table

| VLAN ID | Name | Subnet | Gateway | OPNsense Interface | Purpose |
|---|---|---|---|---|---|
| 1 | Default/Management | 192.168.50.0/24 | 192.168.50.1 | N/A (ASUS-managed) | Router, desktop, switch mgmt |
| 10 | Trusted | 10.10.10.0/24 | 10.10.10.1 | Trusted (em1) | Personal/trusted devices |
| 20 | IoT | 10.10.20.0/24 | 10.10.20.1 | IoT (em2) | Smart TVs, phones, untrusted devices |
| 30 | Lab | 10.10.30.0/24 | 10.10.30.1 | Lab (em3) | Test clients, experiments, VMs |

**Note:** VLAN IDs/tags above describe the switch-side VLAN each subnet
lives on. On the OPNsense/host side there is no tagging anymore — each
interface is a dedicated untagged physical link (see Physical Port Layout
and Interface Naming Reference below).

**As-built note:** The original design below described a single 802.1Q
tagged trunk carrying all three VLANs over one physical link (port 7). This
was abandoned after a VirtualBox-on-Windows host-bridging limitation made
tagged frames undeliverable to the guest VM (confirmed via Wireshark —
frames reached the host NIC intact but never reached OPNsense; see
`docs/testing-log.md`). The as-built network instead gives each VLAN its
own dedicated **untagged** physical link from a separate host NIC into its
own switch port, each bridged individually into OPNsense. The logical
VLAN/subnet design (IDs, ranges, policy) is unchanged — only the physical
delivery method changed. See the "AS BUILT" port table and Interface
Naming Reference below for the current wiring.

VLAN 1 remains the switch's default/native VLAN, carrying the existing home
network (router, desktop) — kept separate from the lab subnets below.

**Note:** The original plan used a dedicated 10.10.1.0/24 management VLAN.
In practice, the switch's own management IP and the existing home devices
stayed on the default VLAN 1 (192.168.50.0/24, assigned by the ASUS
router), since those devices were already connected before the VLAN
build-out. The 10.10.x.x ranges are used exclusively for the new
Trusted/IoT/Lab lab segments behind OPNsense.

## Address Allocation Convention

Within each 10.10.x.0/24 lab subnet:

| Range | Use |
|---|---|
| `.1` | Gateway (OPNsense interface IP) |
| `.2 – .49` | Static infrastructure (future Pi, NAS) |
| `.50 – .99` | Static reservations (DHCP reservations by MAC) |
| `.100 – .199` | DHCP dynamic pool |
| `.200 – .254` | Reserved / future use |

## DHCP (Kea DHCPv4, on OPNsense)

| Interface | Subnet | Pool Range |
|---|---|---|
| TRUSTED | 10.10.10.0/24 | 10.10.10.100 – 10.10.10.199 |
| IOT | 10.10.20.0/24 | 10.10.20.100 – 10.10.20.199 |
| LAB | 10.10.30.0/24 | 10.10.30.100 – 10.10.30.199 |

Configured under **Services > Kea DHCP > Kea DHCPv4 > Subnets**, with all
three interfaces explicitly bound under **Settings > Interfaces** (Kea
requires this in addition to defining the subnet pools).

The existing 192.168.50.0/24 network (VLAN 1) continues to use the ASUS
router's own DHCP server — untouched by this project.

## Physical / Switch Port Layout (TP-Link TL-SG108E) — AS BUILT (current, v2)

Supersedes the original single-trunk design (see Change Log). Each VLAN now
has its own dedicated untagged physical link from the OPNsense host into
the switch, instead of one tagged trunk carrying all three.

| Port | Device | VLAN membership | Tagged/Untagged | PVID |
|---|---|---|---|---|
| 1 | ASUS router | 1 (default) | Untagged | 1 |
| 2 | Main desktop PC | 1 (default) | Untagged | 1 |
| 3 | Trusted test device (spare laptop) | 10 | Untagged | 10 |
| 4 | IoT test device (spare laptop) | 20 | Untagged | 20 |
| 5 | Lab test device (spare laptop) | 30 | Untagged | 30 |
| 6 | **OPNsense IoT link** — USB-Ethernet adapter #1 → em2 | 20 | Untagged | 20 |
| 7 | **OPNsense Trusted link** — host's built-in Realtek NIC → em1 | 10 | Untagged | 10 |
| 8 | **OPNsense Lab link** — USB-Ethernet adapter #2 → em3 | 30 | Untagged | 30 |

**VLAN 1 membership:** only ports 1 and 2 are members of the default VLAN.
Ports 3-8 are untagged members of their own VLAN only. (On 2026-11-03 the
switch was found with ports 3-7 still in VLAN 1 as well, which let
home-LAN broadcasts and multicast from `192.168.50.x` flow out the IoT
uplink into `em2`; see Change Log and testing-log.md.) Save the switch
config after any change (System Tools > Save Config) or it can revert.

Each OPNsense-facing port (6, 7, 8) is bridged in VirtualBox to one physical
host NIC with Promiscuous Mode "Allow All," then assigned directly to its
OPNsense interface — no VLAN tagging or sub-interfaces are involved on
these links at all. Ports 3/4/5 remain untagged client test-access ports on
their respective VLANs, used to verify policy with real standalone
hardware.

**Historical note:** An earlier revision of this doc attributed port 7 to a
USB adapter; it was always the host's built-in Realtek NIC connected by
plain Ethernet, carrying a single 802.1Q tagged trunk. That trunk design
(and the OPT4/management interface that went with it) has been fully
retired — see Change Log.

Switch management IP: `192.168.50.250` (static, set outside the router's
DHCP range).

## Firewall Policy Summary — IMPLEMENTED AND VERIFIED (2026-10-17)

| Source VLAN | Allowed | Blocked |
|---|---|---|
| Trusted | Any (internet + all local VLANs) | — |
| IoT | DNS to own gateway (10.10.20.1:53); ICMP echo from the monitoring host only (10.10.20.100) to the firewall; internet | All other RFC1918 destinations, including other VLANs and ICMP to own gateway from any other device |
| Lab | DNS to own gateway (10.10.30.1:53); ICMP echo from the monitoring host only (10.10.30.100) to the firewall; internet | All other RFC1918 destinations, including other VLANs and ICMP to own gateway from any other device |

Actual OPNsense rule order per interface (top to bottom, first match wins):

**IoT:**
1. Pass — IoT net → IoT address, port 53 (DNS)
2. Pass — `10.10.20.100` → This Firewall, ICMP echo request, logged
   (`IoT - monitor pings`, added 2026-11-03)
3. Block — IoT net → RFC1918 alias
4. Pass — IoT net → any (internet)

**Lab:** same pattern, scoped to Lab net / Lab address, with
`Lab - monitor pings` allowing `10.10.30.100` → This Firewall (ICMP echo).

The monitoring host (the Windows machine running the collector) is a DHCP
client on every VLAN through its bridged adapters, so the ping rules are
keyed to its addresses. Both addresses should be pinned with Kea DHCP
reservations (TODO: confirm they are in place) so the rules cannot silently
stop matching when a lease changes. The rule is
deliberately narrow: other devices on those VLANs still cannot ping their
gateway.

A custom **RFC1918** firewall alias was created (`10.0.0.0/8`,
`172.16.0.0/12`, `192.168.0.0/16`) since OPNsense has no built-in alias for
this.

**Verified 2026-10-17** via a VLAN-tagged VM test client (Client jaja) over
the original single-trunk design: DHCP leasing, DNS resolution, internet
access, and blocking of OPT4/LAN/Trusted/cross-VLAN destinations all
confirmed working exactly as designed.

**Re-verified 2026-10-25/26** end-to-end on **real physical client
hardware** (separate spare laptops on switch ports 3/4/5) after the
topology was rebuilt around per-VLAN untagged links: Trusted, IoT, and Lab
all confirmed — correct DHCP lease, own-gateway and cross-VLAN traffic
blocked as designed, DNS and internet access working. See
`docs/testing-log.md` for full test results, including the VirtualBox
host-bridging limitation that prompted the topology rebuild and the issues
found and fixed along the way.

## Interface Naming Reference — AS BUILT (current, v2)

| Physical/Logical | OPNsense Name | Description |
|---|---|---|
| em0 | WAN | VirtualBox NAT adapter (software NAT to the host's real internet connection) |
| em1 | Trusted | Host's built-in Realtek NIC, bridged → switch port 7, untagged, VLAN 10. 10.10.10.0/24 |
| em2 | IoT | USB-to-Ethernet adapter #1, bridged → switch port 6, untagged, VLAN 20. 10.10.20.0/24 |
| em3 | Lab | USB-to-Ethernet adapter #2, bridged → switch port 8, untagged, VLAN 30. 10.10.30.0/24 |

**Retired:** `vlan0.1`/`vlan0.2`/`vlan0.3` (VLAN sub-interfaces on a single
tagged trunk) and the `OPT4`/management interface (`192.168.2.0/24`,
internal-network-only) no longer exist. OPT4 was originally added to keep
GUI access available while LAN was fully dedicated to the trunk; once the
trunk was retired, GUI access is reached directly via the Trusted
interface instead, and OPT4 was deleted after being unassigned.

## Change Log

| Date | Change |
|---|---|
| 2026-09-23 | Initial plan drafted (Phase 1) |
| 2026-09-24 | VLAN interfaces created and corrected (parent interface fix — see testing-log.md) |
| 2026-09-24 | Kea DHCPv4 subnets and interface bindings configured |
| 2026-10-09 | Physical switch configured; port layout and management VLAN updated to match as-built setup |
| 2026-10-14 | OPT4 management interface added (em2, Internal Network `intnet`) so the GUI stays reachable with LAN dedicated to the physical trunk |
| 2026-10-16/17 | Firewall rules for Trusted/IoT/Lab built and fully verified with a VLAN-tagged test client; fixed a NIC driver VLAN-tagging setting and a Kea DHCP vs. Dnsmasq port-67 conflict along the way — see testing-log.md |
| 2026-10-25/26 | **Topology rebuild.** Root-caused a VirtualBox-on-Windows bridging limitation that silently dropped 802.1Q-tagged frames between the host NIC and the guest VM (confirmed via Wireshark). Abandoned the single tagged-trunk design; rebuilt the network so each VLAN has its own dedicated untagged physical link (switch ports 6/7/8 → em2/em1/em3) via two added USB-to-Ethernet adapters. Retired `vlan0.x` sub-interfaces and the OPT4/management interface. Re-verified Trusted/IoT/Lab end-to-end on real physical client hardware. Full narrative in testing-log.md. |
| 2026-11-03 | **Monitor access and switch cleanup.** The dashboard showed the IoT and Lab gateways offline. Cause: the `block private network` rules (RFC1918 includes each gateway address) silently dropped the monitoring host's pings; the rules had logging off, so Live View showed nothing. Added narrow, logged `monitor pings` pass rules above the block rules (Kea reservations for the host's IoT/Lab addresses still to confirm). Same investigation found ports 3-7 still untagged members of VLAN 1 on the switch (home-LAN traffic reaching `em2`); removed them, leaving VLAN 1 on ports 1-2. Host route metrics reordered so the Trusted adapter carries internet traffic. Details in testing-log.md. |
