# Testing & Troubleshooting Log

Running log of setup steps, tests, issues hit, and fixes for the home network
monitoring project. Dated entries, most recent last.

---

## 2026-09-23 — OPNsense VM setup

**Step:** Installed OPNsense in a VirtualBox VM (Windows 11 Home host).
**Result:** Success. VM created with 2 CPUs, 2–4 GB RAM, 20 GB disk.
**Notes:** Used the NAT adapter for WAN, planned a second adapter for the
LAN/trunk side once hardware arrives.

**Step:** Created a Linux client VM to test against OPNsense.
**Result:** Success — client boots and can reach OPNsense's LAN interface.

**Issue:** Tried reaching OPNsense at `https://localhost:8443` from the
client and from the host browser — got "Unable to connect" / "refused to
connect."
**Cause:** No VirtualBox NAT port-forwarding rule existed (host port 8443 →
guest port 443 was never created). This was a leftover step from an earlier
plan and was never actually needed once LAN access worked.
**Fix:** Abandoned the port-forward approach entirely. Access OPNsense
directly via its LAN IP from the Linux client's browser instead. No rule
needed for the project going forward.

---

## 2026-09-23 — VLAN creation

**Step:** Created VLAN interfaces (tag 10 / Trusted, tag 20 / IoT, tag 30 /
Lab) under Interfaces > Devices > VLAN.
**Issue #1:** Menu was labeled "Devices" rather than the older "Other Types"
naming found in most guides — cost some time locating the right page.
**Fix:** Confirmed via OPNsense's current UI that VLAN configuration lives
under Interfaces > Devices > VLAN.

**Issue #2:** After creating all three VLANs, they weren't yet selectable in
Interfaces > Assignments. dropdown appeared empty.
**Cause:** Hadn't clicked **Apply** on the VLAN list page after adding them,
so the assignments page didn't pick up the pending changes.
**Fix:** Clicked Apply on the VLAN page, refreshed Assignments, VLANs then
appeared in the "new interface" dropdown as expected.

**Issue #3 (bigger one):** After assigning all three VLANs as OPT1/OPT2/OPT3,
noticed in the Assignments table that IoT and Lab were tagged on parent
interface `em0` (WAN) instead of `em1` (LAN). Only Trusted was correctly
tagged on LAN.
**Cause:** Picked the wrong interface from the dropdown while creating the
IoT and Lab VLANs — likely defaulted to the first option in the list.
**Fix:** Edited both VLAN entries under Interfaces > Devices > VLAN, changed
parent interface to `em1` (LAN), applied changes. Confirmed all three now
show `Parent: em1` in the Assignments table.
**Lesson:** Always double-check the parent interface column after creating
VLANs — an easy mistake to make and one that would have quietly broken
segmentation (VLAN traffic would have ridden the WAN NIC instead of LAN).

**Step:** Enabled each VLAN interface (TRUSTED, IOT, LAB) with static IPv4:
- TRUSTED: 10.10.10.1/24
- IOT: 10.10.20.1/24
- LAB: 10.10.30.1/24
**Result:** All three show as up (green) under Interfaces > Overview.

---

## 2026-09-23 — DHCP setup

**Issue:** Expected a "Services > DHCPv4" page per-interface (older ISC DHCP
layout from most tutorials/docs). No such tab existed under Services.
**Cause:** This OPNsense version defaults to **Kea DHCP** rather than the
legacy ISC DHCPv4 server. Kea's UI is structured differently — subnets
instead of one page per interface.
**Fix:** Used Services > Kea DHCP > Kea DHCPv4 instead. Created three
subnets under the Subnets tab:
- 10.10.10.0/24 (Trusted), pool 10.10.10.100–199
- 10.10.20.0/24 (IoT), pool 10.10.20.100–199
- 10.10.30.0/24 (Lab), pool 10.10.30.100–199

**Issue:** Even after creating subnets and clicking Apply, wasn't sure Kea
was actually listening on the VLAN interfaces.
**Cause:** Found under the Settings tab that **Interfaces** was set to
"Nothing selected" — Kea was enabled but not bound to any interface, so no
subnet would actually respond to DHCP requests regardless of the pools
being configured correctly.
**Fix:** Selected TRUSTED, IOT, and LAB under Settings > Interfaces, saved,
re-applied on the Subnets tab, and started the Kea DHCPv4 service (play
button, now shows green/running).
**Lesson:** In Kea, defining a subnet and binding an interface are two
separate steps — easy to assume one implies the other.

---

## Pending — waiting on hardware

Physical switch (TP-Link TL-SG108E) and USB Ethernet adapter for the laptop
have not arrived yet. Client-side VLAN testing (confirming a device actually
receives a 10.10.x.x lease over a tagged trunk) is blocked until they do.
Decided against simulating this fully inside VirtualBox, since nested
virtual VLAN tagging wouldn't reflect the real trunk/access-port setup and
risked wasted effort on VM networking quirks unrelated to the actual design.

**Next steps once hardware arrives:**
- Wire USB adapter to switch port 1 (trunk), configure port VLAN
  memberships on the TL-SG108E
- Attach OPNsense's LAN adapter to the USB adapter (bridged) with
  promiscuous mode enabled
- Confirm a real client on each VLAN gets the correct 10.10.x.x lease
- Test IoT → Trusted isolation with ping/nmap
- Log results here

## In the meantime

- [ ] Ping-tested inter-VLAN routing directly from OPNsense
      (Interfaces > Diagnostics > Ping, source TRUSTED → 10.10.20.1, etc.)
- [ ] Drafted firewall isolation rules for IOT and LAB (not yet verifiable
      without real client traffic, but logic is in place)
- [ ] First OPNsense config backup exported and redacted