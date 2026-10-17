# Testing \& Troubleshooting Log

Running log of setup steps, tests, issues hit, and fixes for the home network
monitoring project. Dated entries, most recent last.

\---

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

\---

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

* TRUSTED: 10.10.10.1/24
* IOT: 10.10.20.1/24
* LAB: 10.10.30.1/24
**Result:** All three show as up (green) under Interfaces > Overview.

\---

## 2026-09-23 — DHCP setup

**Issue:** Expected a "Services > DHCPv4" page per-interface (older ISC DHCP
layout from most tutorials/docs). No such tab existed under Services.
**Cause:** This OPNsense version defaults to **Kea DHCP** rather than the
legacy ISC DHCPv4 server. Kea's UI is structured differently — subnets
instead of one page per interface.
**Fix:** Used Services > Kea DHCP > Kea DHCPv4 instead. Created three
subnets under the Subnets tab:

* 10.10.10.0/24 (Trusted), pool 10.10.10.100–199
* 10.10.20.0/24 (IoT), pool 10.10.20.100–199
* 10.10.30.0/24 (Lab), pool 10.10.30.100–199

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

\---

## 2026-10-09 — Switch arrived; physical VLAN configuration

**Step:** TP-Link TL-SG108E switch arrived. Connected existing devices:
router → port 1, main desktop PC → port 2, laptop (built-in NIC, temporary)
→ port 8, for initial switch management access.

**Issue:** Tried reaching the switch's default management IP
(`192.168.0.1`) by manually setting the laptop's Ethernet adapter to a
static IP (`192.168.0.10/24`). Got `ERR\_CONNECTION\_TIMED\_OUT` in the
browser and 100% packet loss on ping.
**Cause:** The switch was actually already reachable on the home network's
real subnet (`192.168.50.x`) via DHCP from the ASUS router, since the
switch, router, and desktop were all already connected together. The
static `192.168.0.10` IP put the laptop on a completely different,
unrelated subnet, so `192.168.0.1` was never going to be reachable from
that adapter. `ipconfig` confirmed the laptop's Ethernet adapter still had
a `192.168.50.133` DHCP address the whole time, not the static IP I
thought I'd set.
**Fix:** Abandoned the manual static-IP approach. Reverted the adapter back
to Automatic (DHCP), then accessed the switch directly at its actual
DHCP-assigned address shown in its own System Info page
(`192.168.50.248`).
**Lesson:** Don't assume a device's documented default IP applies once
it's already live on an existing network with its own DHCP server — check
where it actually landed first (switch's own System Info page, or the
router's DHCP client list) rather than reaching for the factory-default
address.

**Step:** Set a static management IP on the switch itself (System > IP
Setting): `192.168.50.250`, matching the home network's real range so it
won't drift again.

**Step:** Mapped physical ports to actual connected devices: port 1 =
router, port 2 = desktop PC, port 8 = laptop (temporary management-only
connection). Reserved port 7 for the OPNsense trunk (laptop's USB adapter),
since ports 1 and 2 were already in use — differs from the original plan,
which assumed the trunk would be on port 1.

**Step:** Configured 802.1Q VLANs (System > VLAN > 802.1Q VLAN):

* Enabled 802.1Q VLAN mode globally
* VLAN 10 (Trusted): port 3 untagged, port 7 tagged
* VLAN 20 (IoT): port 4 untagged, port 7 tagged
* VLAN 30 (Lab): port 5 untagged, port 7 tagged
* Default VLAN 1 retained all ports untagged (router/desktop/laptop
management unaffected)

**Step:** Checked 802.1Q PVID Setting — ports 3/4/5 had already picked up
PVID 10/20/30 automatically from the VLAN membership step above; no manual
PVID changes were needed. Confirmed port 1, 2, 7, 8 remained at PVID 1.
**Note:** On this firmware (TL-SG108E v6, firmware 1.0.0 build 20250710),
setting a port as an untagged member of a VLAN auto-updates its PVID — this
isn't true on all managed switches, so it was worth explicitly verifying
rather than assuming.

**Result:** Switch-side VLAN configuration matches the design. Updated
`docs/ip-vlan-plan.md` with the as-built port layout (trunk on port 7, not
port 1) and the real management IP scheme.

**Next:** Move laptop's USB Ethernet adapter from port 8 to port 7 (the
trunk), bridge OPNsense's LAN adapter to that USB adapter in VirtualBox
with promiscuous mode enabled, and run the first real client VLAN test.

\---

## 2026-10-15 — Management interface (OPT4) added for GUI access

**Problem:** After bridging OPNsense's LAN (em1) to the physical trunk for
hardware testing, the old Internal-Network-based test client ("Client jaja")
could no longer reach the OPNsense web GUI — LAN was no longer on `intnet`.

**Fix:** Added a dedicated management interface instead of reusing LAN:

* Added Adapter 3 to the OPNsense VM: Internal Network, name `intnet`
(same network Client jaja's Adapter 1 uses).
* Re-ran Interfaces > Assign via the console (had to retype WAN/LAN/OPT
names manually — auto-detection doesn't work reliably for virtual NICs
with no physical link to toggle).
* Assigned the new NIC as **OPT4**, static IP `192.168.2.1/24`, DHCP range
`192.168.2.100–199`.

**Issue:** OPT4 had no firewall rules at all (OPT interfaces get zero rules
by default — no automatic "allow management" rule like LAN gets). Client
could get a DHCP lease but not ping or reach the GUI.
**Fix:** Temporarily disabled the firewall from the console (`pfctl -d`),
added a Pass/any/any rule on OPT4 through the GUI, then re-enabled
(`pfctl -e`). Confirmed stable management access afterward.
**Lesson:** A newly assigned OPT interface is fully locked down until you
explicitly add a rule — easy to forget since LAN's behavior (auto-allow)
isn't the default.

\---

## 2026-10-16 — Real firewall policy implemented and verified (IoT/Lab isolation)

**Step:** Built the actual Trusted/IoT/Lab firewall rules in OPNsense,
matching the policy in `docs/ip-vlan-plan.md`:

* Created a `RFC1918` alias (Firewall > Aliases, Network(s) type) containing
`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` — OPNsense doesn't ship a
built-in "private networks" alias like some other firewalls.
* **Trusted:** single Pass any/any rule — full access.
* **IoT / Lab:** three rules each, in order (top to bottom, first match
wins):

  1. Pass — source: own net, destination: own gateway IP, port 53 (DNS)
  2. Block — source: own net, destination: `RFC1918` alias
  3. Pass — source: own net, destination: any (internet)
* Had to drag the DNS-allow rule above the Block rule by hand (new rules
get added at the bottom by default).

**Issue:** First attempt at creating the IoT "allow internet" rule left the
**Interface** field on "Floating" instead of "IoT" — it showed up under a
separate "Floating rules" section instead of "Interface rules > IoT".
**Fix:** Edited the rule and explicitly set Interface to IoT.

**Step:** Set up "Client jaja" as a real VLAN-tagged test client (no
physical device/USB adapter yet) by bridging a second adapter to the same
physical NIC OPNsense's trunk uses, with Promiscuous Mode: Allow All, then
creating 802.1Q sub-interfaces in Linux (`ip link add ... type vlan id 20`,
later migrated to `nmcli connection add type vlan ...` since NetworkManager
doesn't manage raw `ip link` VLAN interfaces).

**Issue (big one):** VLAN-tagged DHCP requests never got a response, even
though the OPNsense-side VLAN interfaces, Kea subnets, and interface
bindings were all correctly configured.
**Diagnosis path:**

1. Captured on the client with `tcpdump -i enp0s10 -e -n vlan or port 67 or port 68` — confirmed tagged (`vlan 20`) DHCP requests were actually
leaving the VM.
2. Captured on OPNsense's console (`tcpdump -i vlan0.2 -n port 67 or port 68`) — the tagged requests **were** arriving at OPNsense. So the
physical trunk (host NIC → switch port 7 → OPNsense) was working
end-to-end.
3. Checked the Windows host's Realtek NIC driver (Device Manager > Advanced

> "Priority \& VLAN") — it was already set to "Priority \& VLAN Enable",
   so tag-stripping at the driver level wasn't the problem (this \*is\* a
   real, common gotcha with bridged VMs on Windows hosts — just not this
   one).

4. Checked the Kea DHCPv4 log (Services > Kea DHCP > Kea DHCPv4 > Log
File) and found the real cause:
`DHCPSRV\_OPEN\_SOCKET\_FAIL ... failed to bind fallback socket to address 10.10.20.1, port 67 ... Address already in use - is another DHCP server running?` — happening on all three VLAN interfaces, even after a clean
reboot (so not a stuck process).
5. Confirmed via `sockstat -4 | grep 67` on the OPNsense console: **Dnsmasq**
(`Services > Dnsmasq DNS \& DHCP`, enabled by an earlier setup step) was
bound to `\*:67` — a wildcard covering every interface, not just the
ones it had DHCP ranges configured for. This silently blocked Kea from
binding anywhere, even on interfaces Dnsmasq itself wasn't using.
**Fix:** Consolidated onto a single DHCP backend. Added OPT4's subnet
(`192.168.2.0/24`) to Kea, bound OPT4 under Kea's Settings > Interfaces,
then fully disabled Dnsmasq (General > Enable, unchecked). Rebooted.
`sockstat` afterward showed `kea-dhcp4` cleanly bound per-interface on
OPT4, Trusted, IoT, and Lab — no more wildcard conflict.
**Lesson:** Don't run two DHCP server backends at once in OPNsense, even if
they're scoped to different interfaces on paper — Dnsmasq's default
`bind-dynamic` behavior claims the port globally. The OPT4 DHCP that
"worked" earlier in this project was actually being served by Dnsmasq
(enabled by the console wizard when I said yes to "enable DHCP server" on
OPT4), not Kea — I didn't realize two separate DHCP engines were active
until this conflict surfaced on the VLAN interfaces.

**Step:** With the port conflict resolved, retested VLAN 20 (IoT) DHCP —
got a clean lease (`10.10.20.100/24`) via the NetworkManager VLAN
connection.

**Issue:** Initial isolation test (plain `ping` to OPT4/LAN/Trusted) showed
all of them unexpectedly succeeding from the IoT client.
**Cause:** Not a firewall bug — a routing artifact on the test client.
With two active interfaces (OPT4's `enp0s3` and IoT's tagged `enp0s10.20`),
the default route via OPT4 (lower metric, 100) was winning for all
cross-subnet traffic, so pings were leaving via OPT4 — which has an
allow-all rule — instead of IoT.
**Fix:** Re-ran every test with `ping -I enp0s10.20 ...` to force traffic
out the correct interface.

**Result — IoT isolation test (`enp0s10.20`, lease `10.10.20.100`):**

|Target|Expected|Result|
|-|-|-|
|`dig @10.10.20.1 google.com` (DNS)|resolve|✅ resolved|
|`8.8.8.8` (internet)|pass|✅ 0% loss|
|`192.168.2.1` (OPT4/mgmt)|block|✅ 100% loss|
|`192.168.1.1` (base LAN)|block|✅ 100% loss|
|`10.10.10.1` (Trusted)|block|✅ 100% loss|
|`10.10.20.1` ping (own gateway, ICMP)|block\*|✅ 100% loss|

\* Only DNS (port 53) to the gateway was explicitly allowed — ICMP to the
gateway was never added as an exception, so this block is expected
behavior, not a bug.

**Result — Lab isolation test (`enp0s10.30`, lease `10.10.30.100`):**

|Target|Expected|Result|
|-|-|-|
|`dig @10.10.30.1 google.com` (DNS)|resolve|✅ resolved|
|`8.8.8.8` (internet)|pass|✅ 0% loss|
|`192.168.2.1` (OPT4/mgmt)|block|✅ 100% loss|
|`192.168.1.1` (base LAN)|block|✅ 100% loss|
|`10.10.10.1` (Trusted)|block|✅ 100% loss|
|`10.10.20.1` (IoT)|block|✅ 100% loss|

Both VLANs match the documented policy exactly: internet + DNS only, fully
isolated from every other segment including each other.

## Pending

* \[x] Confirm a client on IoT/Lab gets the correct 10.10.x.x lease
* \[x] Test IoT/Lab isolation with ping/DNS (virtual VLAN-tagged client over
the real physical trunk — not yet a standalone physical end device)
* \[x] Firewall isolation rules for IOT and LAB created and verified
* \[ ] Repeat the isolation test from an actual physical device once the
USB-to-Ethernet adapter arrives (current test used a VM bridged onto
the same physical trunk with manually tagged VLAN sub-interfaces —
proves the policy works, but a real device on switch ports 3/4/5 is
still the more representative end-to-end test)
* \[ ] Ping-tested inter-VLAN routing directly from OPNsense
(Interfaces > Diagnostics > Ping, source TRUSTED → 10.10.20.1, etc.)
* \[ ] First OPNsense config backup exported and redacted

