# IP & VLAN Plan

This document defines the addressing scheme, VLAN layout, and interface
mapping for the home lab network. It's the source of truth — OPNsense,
switch, and DHCP configs should all match this.

## VLAN Table

| VLAN ID | Name | Subnet | Gateway | OPNsense Interface | Purpose |
|---|---|---|---|---|---|
| 1 | Management | 10.10.1.0/24 | 10.10.1.1 | LAN (untagged) | Switch admin, OPNsense mgmt |
| 10 | Trusted | 10.10.10.0/24 | 10.10.10.1 | TRUSTED (OPT1) | Personal/trusted devices |
| 20 | IoT | 10.10.20.0/24 | 10.10.20.1 | IOT (OPT2) | Smart TVs, phones, untrusted devices |
| 30 | Lab | 10.10.30.0/24 | 10.10.30.1 | LAB (OPT3) | Test clients, experiments, VMs |

All VLANs are tagged (802.1Q) on the trunk between OPNsense and the managed
switch, with parent interface `em1` (LAN NIC). VLAN 1 remains the native/
untagged VLAN on the trunk.

## Address Allocation Convention

Within each /24:

| Range | Use |
|---|---|
| `.1` | Gateway (OPNsense interface IP) |
| `.2 – .49` | Static infrastructure (switch mgmt, future Pi, NAS) |
| `.50 – .99` | Static reservations (DHCP reservations by MAC) |
| `.100 – .199` | DHCP dynamic pool |
| `.200 – .254` | Reserved / future use |

## DHCP (Kea DHCPv4)

| Interface | Subnet | Pool Range |
|---|---|---|
| TRUSTED | 10.10.10.0/24 | 10.10.10.100 – 10.10.10.199 |
| IOT | 10.10.20.0/24 | 10.10.20.100 – 10.10.20.199 |
| LAB | 10.10.30.0/24 | 10.10.30.100 – 10.10.30.199 |

Configured under **Services > Kea DHCP > Kea DHCPv4 > Subnets**, with all
three interfaces explicitly bound under **Settings > Interfaces** (Kea
requires this in addition to defining the subnet pools).

## Physical / Switch Port Layout (TP-Link TL-SG108E)

| Port | Mode | VLANs |
|---|---|---|
| 1 | Trunk (to laptop USB adapter / OPNsense LAN) | 1 untagged, 10/20/30 tagged |
| 2 | Access | 10 (Trusted) |
| 3 | Access | 20 (IoT) |
| 4 | Access | 30 (Lab) |
| 5–8 | Unused / spare | Assign later (e.g. Raspberry Pi) |

*Not yet wired — pending switch and USB adapter delivery. See
`docs/testing-log.md` for status.*

## Firewall Policy Summary

| Source VLAN | Allowed | Blocked |
|---|---|---|
| Trusted | Any (internet + all local VLANs) | — |
| IoT | Internet only | All RFC1918 destinations (other VLANs) |
| Lab | Internet only | All RFC1918 destinations (other VLANs) |
| All VLANs | OPNsense (DNS/DHCP) | — |

Rule ordering matters — block rules for IoT/Lab must sit above their allow-
internet rule, since OPNsense evaluates top-down, first match wins.

## Interface Naming Reference

| Physical/Logical | OPNsense Name | Description |
|---|---|---|
| em0 | WAN | Upstream to ASUS RT-AX5400 (NAT) |
| em1 | LAN | Trunk to managed switch |
| vlan0.1 on em1 | OPT1 / TRUSTED | 10.10.10.0/24 |
| vlan0.2 on em1 | OPT2 / IOT | 10.10.20.0/24 |
| vlan0.3 on em1 | OPT3 / LAB | 10.10.30.0/24 |

## Physical / Switch Port Layout (TP-Link TL-SG108E) — AS BUILT

Port	Device	VLAN membership	Tagged/Untagged	PVID
1	ASUS router	1 (default)	Untagged	1
2	Main desktop PC	1 (default)	Untagged	1
3	Trusted test device	10	Untagged	10
4	IoT test device	20	Untagged	20
5	Lab test device	30	Untagged	30
6	Unused / spare	1 (default)	—	1
7	Trunk — laptop USB adapter → OPNsense LAN	1, 10, 20, 30	Tagged (all four)	1
8	Laptop built-in NIC (switch management only)	1 (default)	Untagged	1

This differs from the original plan (trunk on port 1) — router and desktop were already connected to ports 1 and 2 before VLAN configuration began, so the trunk was assigned to port 7 instead to avoid disrupting existing connectivity. Port 8 carries only switch-management traffic over VLAN 1, separate from the actual OPNsense trunk on port 7.

Switch management IP: 192.168.50.250 (static, set outside the router's DHCP range).

Firewall Policy Summary
Source VLAN	Allowed	Blocked
Trusted	Any (internet + all local VLANs)	—
IoT	Internet only	All RFC1918 destinations (other VLANs)
Lab	Internet only	All RFC1918 destinations (other VLANs)
All VLANs	OPNsense (DNS/DHCP)	—

Rule ordering matters — block rules for IoT/Lab must sit above their allow- internet rule, since OPNsense evaluates top-down, first match wins.

Interface Naming Reference
Physical/Logical	OPNsense Name	Description
em0	WAN	Upstream to ASUS RT-AX5400 (NAT)
em1	LAN	Trunk to managed switch (port 7)
vlan0.1 on em1	OPT1 / TRUSTED	10.10.10.0/24
vlan0.2 on em1	OPT2 / IOT	10.10.20.0/24
vlan0.3 on em1	OPT3 / LAB	10.10.30.0/24

## Change Log

| Date | Change |
|---|---|
| 2026-09-26 | Initial plan drafted (Phase 1) |
| 2026-09-27| VLAN interfaces created and corrected (parent interface fix — see testing-log.md) |
| 2026-09-27 | Kea DHCPv4 subnets and interface bindings configured |
2026-10-09	Physical switch configured; port layout and management VLAN updated to match as-built setup

