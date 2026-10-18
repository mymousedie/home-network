# IP & VLAN Plan

This document defines the addressing scheme, VLAN layout, and interface
mapping for the home lab network. It's the source of truth — OPNsense,
switch, and DHCP configs should all match this.

## VLAN Table

| VLAN ID | Name | Subnet | Gateway | OPNsense Interface | Purpose |
|---|---|---|---|---|---|
| 1 | Default/Management | 192.168.50.0/24 | 192.168.50.1 | N/A (ASUS-managed) | Router, desktop, switch mgmt |
| 10 | Trusted | 10.10.10.0/24 | 10.10.10.1 | TRUSTED (OPT1) | Personal/trusted devices |
| 20 | IoT | 10.10.20.0/24 | 10.10.20.1 | IOT (OPT2) | Smart TVs, phones, untrusted devices |
| 30 | Lab | 10.10.30.0/24 | 10.10.30.1 | LAB (OPT3) | Test clients, experiments, VMs |

All VLANs are tagged (802.1Q) on the trunk between OPNsense and the managed
switch (port 7), with parent interface `em1` (LAN NIC) on the OPNsense VM.
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

## Physical / Switch Port Layout (TP-Link TL-SG108E) — AS BUILT

| Port | Device | VLAN membership | Tagged/Untagged | PVID |
|---|---|---|---|---|
| 1 | ASUS router | 1 (default) | Untagged | 1 |
| 2 | Main desktop PC | 1 (default) | Untagged | 1 |
| 3 | Trusted test device | 10 | Untagged | 10 |
| 4 | IoT test device | 20 | Untagged | 20 |
| 5 | Lab test device | 30 | Untagged | 30 |
| 6 | Unused / spare | 1 (default) | — | 1 |
| 7 | **Trunk** — laptop USB adapter → OPNsense LAN | 1, 10, 20, 30 | Tagged (all four) | 1 |
| 8 | Laptop built-in NIC (switch management only) | 1 (default) | Untagged | 1 |

This differs from the original plan (trunk on port 1) — router and desktop
were already connected to ports 1 and 2 before VLAN configuration began, so
the trunk was assigned to port 7 instead to avoid disrupting existing
connectivity. Port 8 carries only switch-management traffic over VLAN 1,
separate from the actual OPNsense trunk on port 7.

Switch management IP: `192.168.50.250` (static, set outside the router's
DHCP range).

## Firewall Policy Summary — IMPLEMENTED AND VERIFIED (2026-10-17)

| Source VLAN | Allowed | Blocked |
|---|---|---|
| Trusted | Any (internet + all local VLANs) | — |
| IoT | DNS to own gateway (10.10.20.1:53); internet | All RFC1918 destinations, including other VLANs and ICMP to own gateway |
| Lab | DNS to own gateway (10.10.30.1:53); internet | All RFC1918 destinations, including other VLANs and ICMP to own gateway |

Actual OPNsense rule order per interface (top to bottom, first match wins):

**IoT:**
1. Pass — IoT net → IoT address, port 53 (DNS)
2. Block — IoT net → RFC1918 alias
3. Pass — IoT net → any (internet)

**Lab:** same pattern, scoped to Lab net / Lab address.

A custom **RFC1918** firewall alias was created (`10.0.0.0/8`,
`172.16.0.0/12`, `192.168.0.0/16`) since OPNsense has no built-in alias for
this.

**Verified 2026-10-17** via a VLAN-tagged test client (Client jaja, bridged
to the trunk NIC with 802.1Q sub-interfaces for VLAN 20 and VLAN 30): DHCP
leasing, DNS resolution, internet access, and blocking of OPT4/LAN/Trusted/
cross-VLAN destinations all confirmed working exactly as designed. See
`docs/testing-log.md` for full test results and the two significant issues
found and fixed along the way (NIC driver VLAN tag stripping setting, and
a Kea DHCP vs. Dnsmasq port-67 conflict).

## Interface Naming Reference

| Physical/Logical | OPNsense Name | Description |
|---|---|---|
| em0 | WAN | Upstream to ASUS RT-AX5400 (NAT) |
| em1 | LAN | Trunk to managed switch (port 7) |
| vlan0.1 on em1 | OPT1 / TRUSTED | 10.10.10.0/24 |
| vlan0.2 on em1 | OPT2 / IOT | 10.10.20.0/24 |
| vlan0.3 on em1 | OPT3 / LAB | 10.10.30.0/24 |
| em2 | OPT4 / MGMT | 192.168.2.0/24 — internal management interface, added to reach the GUI once LAN was dedicated to the physical trunk |

## Change Log

| Date | Change |
|---|---|
| 2026-09-XX | Initial plan drafted (Phase 1) |
| 2026-09-XX | VLAN interfaces created and corrected (parent interface fix — see testing-log.md) |
| 2026-09-XX | Kea DHCPv4 subnets and interface bindings configured |
| 2026-10-09 | Physical switch configured; port layout and management VLAN updated to match as-built setup |
| 2026-10-14 | OPT4 management interface added (em2, Internal Network `intnet`) so the GUI stays reachable with LAN dedicated to the physical trunk |
| 2026-10-16/17 | Firewall rules for Trusted/IoT/Lab built and fully verified with a VLAN-tagged test client; fixed a NIC driver VLAN-tagging setting and a Kea DHCP vs. Dnsmasq port-67 conflict along the way — see testing-log.md |
