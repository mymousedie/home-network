# Testing & Troubleshooting Log

Running log of setup steps, tests, issues hit, and fixes for the home network
monitoring project. Dated entries, most recent last.

---

## 2026-09-24 — OPNsense VM setup

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

## 2026-09-24 — VLAN creation

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

## 2026-09-24 — DHCP setup

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

## 2026-10-09 — Switch arrived; physical VLAN configuration

**Step:** TP-Link TL-SG108E switch arrived. Connected existing devices:
router → port 1, main desktop PC → port 2, laptop (built-in NIC, temporary)
→ port 8, for initial switch management access.

**Issue:** Tried reaching the switch's default management IP
(`192.168.0.1`) by manually setting the laptop's Ethernet adapter to a
static IP (`192.168.0.10/24`). Got `ERR_CONNECTION_TIMED_OUT` in the
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
- Enabled 802.1Q VLAN mode globally
- VLAN 10 (Trusted): port 3 untagged, port 7 tagged
- VLAN 20 (IoT): port 4 untagged, port 7 tagged
- VLAN 30 (Lab): port 5 untagged, port 7 tagged
- Default VLAN 1 retained all ports untagged (router/desktop/laptop
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

---

## 2026-10-15 — Management interface (OPT4) added for GUI access

**Problem:** After bridging OPNsense's LAN (em1) to the physical trunk for
hardware testing, the old Internal-Network-based test client ("Client jaja")
could no longer reach the OPNsense web GUI — LAN was no longer on `intnet`.

**Fix:** Added a dedicated management interface instead of reusing LAN:
- Added Adapter 3 to the OPNsense VM: Internal Network, name `intnet`
  (same network Client jaja's Adapter 1 uses).
- Re-ran Interfaces > Assign via the console (had to retype WAN/LAN/OPT
  names manually — auto-detection doesn't work reliably for virtual NICs
  with no physical link to toggle).
- Assigned the new NIC as **OPT4**, static IP `192.168.2.1/24`, DHCP range
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

---

## 2026-10-16 — Real firewall policy implemented and verified (IoT/Lab isolation)

**Step:** Built the actual Trusted/IoT/Lab firewall rules in OPNsense,
matching the policy in `docs/ip-vlan-plan.md`:
- Created a `RFC1918` alias (Firewall > Aliases, Network(s) type) containing
  `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` — OPNsense doesn't ship a
  built-in "private networks" alias like some other firewalls.
- **Trusted:** single Pass any/any rule — full access.
- **IoT / Lab:** three rules each, in order (top to bottom, first match
  wins):
  1. Pass — source: own net, destination: own gateway IP, port 53 (DNS)
  2. Block — source: own net, destination: `RFC1918` alias
  3. Pass — source: own net, destination: any (internet)
- Had to drag the DNS-allow rule above the Block rule by hand (new rules
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
1. Captured on the client with `tcpdump -i enp0s10 -e -n vlan or port 67 or
   port 68` — confirmed tagged (`vlan 20`) DHCP requests were actually
   leaving the VM.
2. Captured on OPNsense's console (`tcpdump -i vlan0.2 -n port 67 or port
   68`) — the tagged requests **were** arriving at OPNsense. So the
   physical trunk (host NIC → switch port 7 → OPNsense) was working
   end-to-end.
3. Checked the Windows host's Realtek NIC driver (Device Manager > Advanced
   > "Priority & VLAN") — it was already set to "Priority & VLAN Enable",
   so tag-stripping at the driver level wasn't the problem (this *is* a
   real, common gotcha with bridged VMs on Windows hosts — just not this
   one).
4. Checked the Kea DHCPv4 log (Services > Kea DHCP > Kea DHCPv4 > Log
   File) and found the real cause:
   `DHCPSRV_OPEN_SOCKET_FAIL ... failed to bind fallback socket to address
   10.10.20.1, port 67 ... Address already in use - is another DHCP server
   running?` — happening on all three VLAN interfaces, even after a clean
   reboot (so not a stuck process).
5. Confirmed via `sockstat -4 | grep 67` on the OPNsense console: **Dnsmasq**
   (`Services > Dnsmasq DNS & DHCP`, enabled by an earlier setup step) was
   bound to `*:67` — a wildcard covering every interface, not just the
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
| Target | Expected | Result |
|---|---|---|
| `dig @10.10.20.1 google.com` (DNS) | resolve | ✅ resolved |
| `8.8.8.8` (internet) | pass | ✅ 0% loss |
| `192.168.2.1` (OPT4/mgmt) | block | ✅ 100% loss |
| `192.168.1.1` (base LAN) | block | ✅ 100% loss |
| `10.10.10.1` (Trusted) | block | ✅ 100% loss |
| `10.10.20.1` ping (own gateway, ICMP) | block* | ✅ 100% loss |

\* Only DNS (port 53) to the gateway was explicitly allowed — ICMP to the
gateway was never added as an exception, so this block is expected
behavior, not a bug.

**Result — Lab isolation test (`enp0s10.30`, lease `10.10.30.100`):**
| Target | Expected | Result |
|---|---|---|
| `dig @10.10.30.1 google.com` (DNS) | resolve | ✅ resolved |
| `8.8.8.8` (internet) | pass | ✅ 0% loss |
| `192.168.2.1` (OPT4/mgmt) | block | ✅ 100% loss |
| `192.168.1.1` (base LAN) | block | ✅ 100% loss |
| `10.10.10.1` (Trusted) | block | ✅ 100% loss |
| `10.10.20.1` (IoT) | block | ✅ 100% loss |

Both VLANs match the documented policy exactly: internet + DNS only, fully
isolated from every other segment including each other.

## Pending

- [x] Confirm a client on IoT/Lab gets the correct 10.10.x.x lease
- [x] Test IoT/Lab isolation with ping/DNS (virtual VLAN-tagged client over
      the real physical trunk — not yet a standalone physical end device)
- [x] Firewall isolation rules for IOT and LAB created and verified
- [ ] Repeat the isolation test from an actual physical device once the
      USB-to-Ethernet adapter arrives (current test used a VM bridged onto
      the same physical trunk with manually tagged VLAN sub-interfaces —
      proves the policy works, but a real device on switch ports 3/4/5 is
      still the more representative end-to-end test)
- [ ] Ping-tested inter-VLAN routing directly from OPNsense
      (Interfaces > Diagnostics > Ping, source TRUSTED → 10.10.20.1, etc.)
- [ ] First OPNsense config backup exported and redacted

---

## 2026-10-16/17 — Bridged VLAN trunk testing, firewall rules, and full isolation verification

**Context:** With the physical switch wired and OPNsense's LAN bridged to the
host's USB-free built-in NIC (port 7), set out to build and verify the
IoT/Lab firewall isolation rules using "Client jaja" (Linux VM) as a
VLAN-tagged test client, since the real USB adapter for a standalone
physical client still hadn't arrived.

### Firewall rules built

- **Trusted:** one rule, Pass any/any — full access.
- **IoT:** three rules, in order (top to bottom, first match wins):
  1. Pass — IoT net → IoT address, port 53 (DNS)
  2. Block — IoT net → RFC1918 alias (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
  3. Pass — IoT net → any (internet)
- **Lab:** same pattern as IoT, scoped to Lab net and Lab address.
- Created a custom **RFC1918** firewall alias (OPNsense has no built-in one)
  with the three private ranges as Network(s) entries.

**Issue:** A rule intended as "IoT - allow internet" was accidentally
created as a **Floating** rule instead of being scoped to the IoT
interface.
**Fix:** Edited the rule and set Interface explicitly to IoT.
**Lesson:** Watch the Interface field carefully when adding a rule — it's
easy to leave it on a default/floating value without noticing.

### Issue: VLAN tags silently stripped by the host NIC

**Problem:** Set up a second VLAN-tagged sub-interface on Client jaja
(bridged to the same physical Realtek NIC as OPNsense's trunk, tagged for
VLAN 20/IoT) to act as a test client. DHCP requests sent from the client
never got a response, even though the client's own tcpdump showed properly
tagged (`vlan 20`) DHCP Request packets going out.
**Cause:** Windows' Realtek NIC driver has an **"Priority & VLAN"** advanced
property that can silently strip 802.1Q tags on traffic leaving the host,
even when a bridged VM is sending correctly-tagged frames at the guest
level.
**Fix:** Device Manager > Realtek PCIe GbE Family Controller > Properties >
Advanced > set **Priority & VLAN** to **Priority & VLAN Enabled** (it was
already set correctly in this case, but confirmed as the thing to check
first for any "my VM's tagged traffic isn't arriving" symptom).
**Verification:** Used `tcpdump -e` on the client (showed tagged frames
leaving) and `tcpdump` on OPNsense's own VLAN interface via console Shell
(confirmed tagged DHCP Request packets WERE arriving at OPNsense) to
isolate the problem to "arriving but not answered" rather than "not
arriving at all" — this ruled out the NIC/driver tagging layer as the
remaining cause and pointed at OPNsense itself.

### Issue: Kea DHCP and Dnsmasq fighting over port 67 (the real root cause)

**Problem:** Despite OPNsense correctly receiving tagged DHCP requests on
all three VLAN interfaces (confirmed via tcpdump on vlan0.1/.2/.3), Kea
never responded. Kea's own log showed repeated:
```
DHCPSRV_OPEN_SOCKET_FAIL ... failed to bind fallback socket to address
10.10.20.1, port 67, reason: Address already in use - is another DHCP
server running?
```
for all three VLAN subnets.
**Diagnosis:** Checked **Services > DHCRelay** (empty, not the cause), then
**Services > Dnsmasq DNS & DHCP** (enabled). Its DHCP ranges only listed
LAN and OPT4, which looked unrelated — but confirmed the real conflict
directly at the OS level via the console shell:
```
sockstat -4 | grep 67
```
which showed `dnsmasq` bound to `*:67` (a wildcard covering every
interface on the box), not just the LAN/OPT4 ranges visible in its GUI
config. Dnsmasq's `bind-dynamic` behavior claims port 67 system-wide once
enabled, regardless of which interfaces have explicit DHCP ranges
configured — this silently blocked Kea from binding on Trusted/IoT/Lab even
though Kea's own config (subnets + interface bindings) was entirely
correct.
**Root cause, traced further back:** Dnsmasq's DHCP had been enabled
earlier (without realizing it) when the OPNsense console wizard was used
to set up OPT4 (the management interface) and the wizard's "enable DHCP
server on this interface?" prompt was answered yes — that step appears to
configure Dnsmasq rather than Kea under the hood, which is why OPT4's DHCP
worked fine the whole time while Kea's never could once both services were
active.
**Fix:**
1. Added a new Kea DHCPv4 subnet for OPT4 (192.168.2.0/24, pool
   192.168.2.100-199) and bound OPT4 under Kea's Settings > Interfaces, so
   OPT4 no longer depended on Dnsmasq.
2. Disabled Dnsmasq entirely (Services > Dnsmasq DNS & DHCP > General >
   Enable unchecked).
3. Rebooted OPNsense for a clean port rebind.
4. Verified with `sockstat -4 | grep 67` — now shows four separate
   `kea-dhcp4` sockets, one per interface (192.168.2.1, 10.10.10.1,
   10.10.20.1, 10.10.30.1), no wildcard binding.
**Lesson:** Only run one DHCP backend at a time in OPNsense. A setup
wizard or console shortcut can silently enable a second one (Dnsmasq) even
while the "real" one (Kea) looks fully and correctly configured in its own
GUI — when a service that looks correctly configured still fails to bind,
check for a competing process holding the same port at the OS level
(`sockstat` on FreeBSD/OPNsense) rather than re-checking the same GUI
settings repeatedly.

### Verified: full isolation test results

With Kea fixed and the Floating-rule bug corrected, ran real VLAN-tagged
client tests for both IoT and Lab (sub-interfaces on Client jaja, tagged
20 and 30 respectively, over the real physical trunk to the switch):

| Test | IoT (10.10.20.100) | Lab (10.10.30.100) |
|---|---|---|
| DHCP lease obtained | ✅ 10.10.20.100/24 | ✅ 10.10.30.100/24 |
| DNS via own gateway (`dig @<gw> google.com`) | ✅ resolved | ✅ resolved |
| Internet (ping 8.8.8.8, sourced from VLAN interface) | ✅ 0% loss | ✅ 0% loss |
| Ping own gateway (ICMP, not explicitly allowed) | ✅ blocked (expected — only DNS is allowed, not ICMP) | ✅ blocked |
| Ping OPT4 (192.168.2.1) | ✅ blocked | ✅ blocked |
| Ping base LAN (192.168.1.1) | ✅ blocked | ✅ blocked |
| Ping Trusted gateway (10.10.10.1) | ✅ blocked | ✅ blocked |
| Ping IoT gateway from Lab (10.10.20.1) | n/a | ✅ blocked |

**Note on methodology:** initial pings to blocked destinations appeared to
succeed because the client's default route was pointing out a different
interface (OPT4) rather than the VLAN sub-interface under test. Re-ran all
tests with `ping -I <vlan-iface>` to force traffic out the correct
interface — this is the only way to get a true reading when a test client
has multiple active network interfaces, and is worth remembering for any
future multi-homed test client.

**Result:** IoT and Lab VLAN isolation is now fully verified end-to-end —
real 802.1Q tagged traffic over the physical trunk (switch port 7) →
OPNsense VLAN interfaces → Kea DHCP → firewall policy enforcement. This
matches the documented policy in `ip-vlan-plan.md` exactly.

## Remaining pending items (superseded — see 2026-10-25/26 below)

- [x] Physical (non-VM) client test on switch ports 3/4/5 — completed, but
      required a full topology redesign first (see below)
- [ ] OPNsense config backup exported and redacted (now genuinely
      worthwhile — VLANs, DHCP, and firewall rules are all complete)
- [ ] Phase 3: monitoring backend

---

## 2026-10-25/26 — Real physical client testing: the VirtualBox trunk-bridging bug, topology rebuild, and full verification

**Context:** With the virtual (VM-based) trunk test fully verified, moved
to the final piece: plugging a real, standalone physical laptop into a
switch access port (port 3, Trusted) to confirm the design works with
actual hardware, not just a VM sharing the host's NIC.

### The bug: tagged frames vanish between the host NIC and the guest VM

**Problem:** A real client on port 3 got no DHCP lease at all — not even an
APIPA fallback attempt completing, just silence.

**Diagnosis path (methodical, bottom-up):**
1. `tcpdump -i em1`/`vlan0.1` on the OPNsense console during a client DHCP
   attempt — nothing arrived.
2. Checked switch Monitoring > Port Statistics with Clear + retry on both
   the client port and the trunk port (port 7) — confirmed real traffic
   was moving on **both** ports, so the switch itself was forwarding
   correctly.
3. Ran Wireshark directly on the Windows host, capturing on the physical
   NIC that VirtualBox bridges into OPNsense's trunk — this was the
   decisive step. Captured DHCP Discover frames with an intact, correct
   **802.1Q VLAN ID: 10** tag, arriving at the host's own physical NIC.
4. Despite the host NIC receiving the correctly tagged frame, `tcpdump` on
   OPNsense's own `vlan0.1` interface (inside the VM) showed only ARP
   traffic — the tagged DHCP frames never arrived in the guest at all.
5. Ruled out every standard cause: Promiscuous Mode was already set to
   "Allow All," the correct physical adapter was selected, NIC offloads
   (Large Send Offload v2, TCP Checksum Offload, Receive Side Scaling)
   were disabled one at a time with no change, and the VM was fully power-
   cycled (not just rebooted) multiple times.

**Conclusion:** This is a VirtualBox-on-Windows host-bridging limitation —
tagged frames are visible to the host's NIC driver but the bridging/NDIS
filter layer fails to relay them into the guest. Not a switch, OPNsense,
or firewall-rule problem; the physical trunk design itself was no longer
viable on this specific host/hypervisor combination.

### Decision: abandon the tagged trunk, rebuild per-VLAN

Rather than keep chasing a hypervisor-level bug, redesigned the physical
topology: instead of one tagged trunk carrying all three VLANs, give each
VLAN its **own dedicated untagged physical link** from a separate host NIC
into its own switch port. This sidesteps VLAN tagging on the host-to-switch
path entirely. Two additional USB-to-Ethernet adapters (ASIX AX88179) were
purchased to provide the extra physical NICs needed.

**Switch reconfiguration:**
- Corrected PVID assignments (an initial attempt had port 6/7 PVIDs
  swapped) and removed port 7 from VLAN 20/30's tagged-member lists
  (leftover from the old trunk).
- Final 802.1Q table: port 6 = IoT (untagged, PVID 20), port 7 = Trusted
  (untagged, PVID 10), port 8 = Lab (untagged, PVID 30). Ports 3/4/5 remain
  client test-access ports, unchanged.

**VirtualBox reconfiguration:**
- Deleted the old `vlan0.1`/`vlan0.2`/`vlan0.3` sub-interfaces in OPNsense
  (Interfaces > Devices > VLAN) — this required first removing/unassigning
  each one's interface binding and unlocking it (a lock flag in the Edit
  Assignment dialog blocks deletion otherwise), then re-deleting.
- Added the two new USB adapters as VirtualBox Adapter 3 and Adapter 4,
  Bridged Adapter mode, Promiscuous "Allow All" — one caught a leftover
  "Attached to: Internal Network" setting from an earlier config that had
  to be switched to "Bridged Adapter" before the physical NIC list would
  even populate in the Name dropdown.
- Retired the OPT4/management interface (Adapter 3 in the old layout) —
  no longer needed once the design stopped relying on a single shared
  trunk.

**OPNsense reconfiguration (via console, since GUI access was temporarily
unavailable — see below):**
- Re-ran the Assign Interfaces wizard from the console, mapping WAN/
  Trusted/IoT/Lab directly onto `em0`–`em3` (no VLAN sub-interfaces).
- Set static IPs on each interface directly from console option 2, since
  there was a chicken-and-egg problem: with the old management interface
  retired, there was no way to reach the GUI yet to configure the new
  interfaces through it.
- Temporarily set the host's own Realtek NIC to a static IP
  (`10.10.10.50/24`, gateway/DNS `10.10.10.1`) to reach `https://10.10.10.1`
  and log back into the GUI once Trusted had a known IP.

### Bug: Adapter 3/4 bridged to the wrong physical ports

**Problem:** After the rebuild, testing from switch port 4 (wired for
IoT/VLAN 20) returned a **Lab**-range address (`10.10.30.101`, gateway
`10.10.30.1`) instead of an IoT address.

**Diagnosis:** Used the same switch Port Statistics Clear-and-retry
methodology as before — unplugged one USB adapter at a time and watched
which switch port's counters moved, confirming VirtualBox's **Adapter 3**
(bound to OPNsense's `em2`/IoT) was actually bridged to the USB adapter
physically plugged into port 8 (Lab), while **Adapter 4** (bound to `em3`/
Lab) was bridged to the adapter in port 6 (IoT) — exactly backwards.

**Fix:** Powered off the VM, swapped the two adapters' "Name" dropdown
selections in VirtualBox Settings > Network so each was bridged to its
physically-correct USB adapter, restarted. Retest on port 4 then correctly
returned a `10.10.20.x` address.

### Real physical client verification: Trusted and IoT

With the rewiring corrected, ran full policy tests from real standalone
laptops on switch ports 3 (Trusted) and 4 (IoT):

| Test | Trusted | IoT (10.10.20.101) |
|---|---|---|
| DHCP lease obtained | ✅ 10.10.10.100/24 | ✅ 10.10.20.101/24 |
| Ping own gateway (ICMP) | ✅ allowed (Trusted has no restrictions) | ✅ blocked (expected — only DNS is explicitly allowed to the gateway, not ICMP) |
| Ping another VLAN's gateway | ✅ allowed | ✅ blocked |
| DNS resolution (`nslookup`) | ✅ resolved | ✅ resolved |
| Internet (`ping 8.8.8.8`) | ✅ 0% loss | ✅ 0% loss |

### Lab VLAN: a NAT-backlog red herring, not a real bug

**Problem:** Lab (switch port 5) got a correct DHCP lease and correctly
blocked gateway/cross-VLAN ICMP, matching IoT's pattern exactly — but
`ping 8.8.8.8` and `nslookup google.com` both failed, and **Firewall >
Log Files > Live View showed zero entries at all** for the Lab client's
traffic, which looked identical in shape to the original trunk-bridging
bug (traffic silently not arriving).

**Diagnosis:**
1. Reviewed all three Lab firewall rules field-by-field against the
   working IoT pattern — interface, action, source, destination, and port
   all matched exactly. Rules were not the problem.
2. The "zero log entries" turned out to be a red herring: none of the
   three Lab (or IoT) rules have their **Log** checkbox enabled, so Live
   View never shows their traffic regardless of whether it's passing or
   being blocked — this had nothing to do with connectivity.
3. `tcpdump -i em3` on OPNsense confirmed Lab's traffic **was** arriving
   and being processed normally (DNS queries in, an NXDOMAIN response out
   for an internal-only name). Switch port counters on both the client
   port and Lab's OPNsense uplink port were incrementing normally too.
4. `tcpdump -i em0` (WAN) during a live test showed outbound ICMP/DNS
   correctly leaving OPNsense, NAT'd to the VirtualBox WAN address, and a
   flood of **"ICMP net X unreachable"** replies from VirtualBox's own NAT
   gateway (`10.0.2.2`) finally draining out — a backlog of stale,
   orphaned DNS/ICMP requests from earlier testing (multiple leftover
   `ping`/`nslookup` processes left running across several Command Prompt
   windows) had been saturating VirtualBox's shared NAT connection table.
5. After closing the stale processes, a clean `ping 8.8.8.8 -n 4` and
   `nslookup google.com` both succeeded immediately.

**Result:** No configuration fix was needed — Lab's firewall policy,
routing, and NAT were correct the entire time. **Lesson:** an idle-looking
Live View can mean "nothing logged," not "nothing happened" — check the
Log checkbox on a rule before treating an empty log as evidence of a
connectivity failure. Also: always fully close out leftover
test-client processes (`ping`/`nslookup` without a count flag run
indefinitely) before trusting a "no response" result, especially when
testing through a single shared NAT engine.

### Lab + IoT + Trusted: final full verification

| Test | Trusted | IoT (10.10.20.101) | Lab (10.10.30.101) |
|---|---|---|---|
| DHCP lease | ✅ | ✅ | ✅ |
| Own-gateway ICMP | ✅ allowed | ✅ blocked | ✅ blocked |
| Cross-VLAN ICMP | ✅ allowed | ✅ blocked | ✅ blocked |
| DNS resolution | ✅ | ✅ | ✅ (4/4 success after NAT backlog cleared) |
| Internet (`ping 8.8.8.8`) | ✅ 0% loss | ✅ 0% loss | ✅ 0% loss (4/4 after backlog cleared) |

All three VLANs are now fully verified end-to-end on real, standalone
physical client hardware via the rebuilt per-VLAN untagged topology — this
completes Phase 2c.

### Side-quest: getting the host laptop itself online as a Trusted client

Since the host also runs the hypervisor, its own built-in Ethernet NIC is
simultaneously (a) the physical link VirtualBox bridges into OPNsense's
Trusted interface, and (b) a normal Windows network adapter the host uses
for its own traffic. Getting the host itself working as a well-behaved
Trusted client surfaced several additional issues:

1. **Stale static IP, no gateway.** The host's Ethernet adapter was still
   on the `10.10.10.50/24` static config set earlier for emergency GUI
   access, plus a second leftover static IP (`192.168.0.10/24`) from
   before this cable was ever connected to the switch — and critically, no
   default gateway was set on either. **Fix:** reset the adapter to DHCP.
2. **Wrong default route.** The host is a DHCP client on all three VLANs
   simultaneously (each bridged NIC also behaves as a normal Windows
   adapter), so Windows picked IoT's gateway as the default route for
   general traffic instead of Trusted's — confirmed via `tracert 8.8.8.8`
   showing `10.10.20.1` as the first hop. **Fix:** manually raised the
   interface metric on the IoT/Lab-bridged adapters (Advanced TCP/IP
   Settings > uncheck Automatic metric) so Trusted is always preferred for
   general traffic, without disabling those adapters (disabling them
   breaks VirtualBox's ability to bridge them into the VM at all — tried
   this and the VM failed to boot, "network adapter not found," until
   re-enabled).
3. **VirtualBox NAT reliability.** Even after routing was fixed, the
   host's ping through OPNsense's WAN was wildly inconsistent (0–100%
   loss, 5–900ms+ jitter on pings as basic as the VirtualBox NAT gateway
   itself, `10.0.2.2`). Ruled out, in order: leftover stray `ping`
   processes (confirmed via Task Manager, and even an ICMP flood pattern
   of a dozen different request IDs within milliseconds of each other);
   host memory pressure (Task Manager showed 89% RAM used at one point,
   though freeing it to 63% didn't fix the jitter — so not the root
   cause); a full host reboot (didn't fix it either).
4. **Root cause: Windows Memory Integrity (VBS) forcing VirtualBox onto
   the Windows Hypervisor Platform.** Windows' Core Isolation / Memory
   Integrity was enabled (likely for Docker Desktop / WSL2), which forces
   VirtualBox to run on Windows' own hypervisor layer instead of its
   native one — a well-documented cause of exactly this kind of
   networking instability. **Fix:** disabled Memory Integrity (Windows
   Security > Device security > Core isolation), rebooted. OPNsense's own
   console ping to `8.8.8.8` immediately went from constant failure to
   0% packet loss (though still high latency — see next point). This is
   very likely the same underlying cause behind the original trunk-
   tagging bug earlier in this entry, not a separate issue.
5. **Attempted fix that didn't pan out:** tried switching OPNsense's WAN
   adapter from VirtualBox NAT to a Bridged Adapter on the host's Wi-Fi
   NIC, hoping to bypass VirtualBox's software NAT entirely. This failed —
   `dhclient em0` showed DHCPREQUESTs going out with no DHCPOFFER ever
   returned. Wi-Fi radios generally don't support true bridged/promiscuous
   operation the way wired NICs do (the AP only forwards for MAC
   addresses it has associated), so this is a dead end on Wi-Fi hardware.
   Reverted WAN back to NAT mode.
6. **Remaining latency is the ISP, not a bug.** With Memory Integrity off,
   OPNsense's WAN got a clean, 0%-loss ping to `8.8.8.8`, just at higher
   latency (~525–665ms) than normal broadband. A `tracert` from the
   Trusted client confirmed the actual cause: the host's internet
   connection is **Verizon 5G Home Internet** (cellular/fixed-wireless —
   confirmed via a `myvzw.com` hop in the trace), which carries inherently
   more latency and jitter than wired broadband, further compounded by
   double NAT (VirtualBox's NAT for WAN, then OPNsense's own NAT for
   Trusted clients). The trace did successfully reach `dns.google
   [8.8.8.8]` with a clean, consistent ~100ms response. **Conclusion:**
   this is a real, documented characteristic of the WAN medium on this
   specific host setup, not a network-design flaw — the VLAN segmentation,
   firewall policy, and routing are all confirmed correct.

### Remaining pending items

- [x] Real physical (non-VM) client test on switch ports 3/4/5 for all
      three VLANs — complete
- [x] OPNsense config backup exported and pushed
- [x] Phase 3: monitoring backend — collector written, unit-tested and verified live (below)

## 2026-10-28 — Phase 3: collector unit tests

Built `collector/` (ping/DNS checks, SQLite storage, UDP syslog listener for
OPNsense `filterlog`, summary report). `python -m unittest tests.test_netmon`:
19 tests, all passing (1 skipped: live loopback ping, no `ping` binary in the
build container).

Bugs found and fixed by the tests:

- **Syslog parser returned nothing for real OPNsense lines.** The first
  version looked for `": "` after `filterlog`, which only exists in RFC 3164
  format. OPNsense's RFC 5424 output has a pid, msgid and structured-data
  block instead. The parser now handles both.
- **DNS test hung.** The test monkeypatched `socket.sendto` globally, so the
  fake DNS server's replies were redirected back to itself. The patch now
  only redirects traffic aimed at port 53.

## 2026-10-31 — Phase 3: first live collector run

Ran `python -m netmon.runner` on the Windows host with OPNsense remote syslog
(UDP 5514, application `filter`) pointed at the host's Trusted IP, plus an
inbound Windows Defender Firewall rule for UDP 5514.

`python -m netmon.report --hours 1` after roughly 10 collection cycles:

| Signal | Result |
|---|---|
| Device checks | All five devices recorded 10 checks each. Uptime ranged from 40% (IoT gateway, avg 664 ms) to 80% (Lab gateway); the 192.168.50.x devices showed 50% |
| Internet health | 8.8.8.8: 50% loss, avg 33 ms; 1.1.1.1: 100% loss; avg DNS lookup 317 ms |
| Firewall events | Received over syslog and parsed: em0 pass 20775 / block 59, em1 pass 17 / block 4 |

**Conclusion:** the full pipeline works end to end: ping and DNS checks,
SQLite storage, remote syslog receive, filterlog parse and report. The
sub-100% uptime and loss figures are consistent with the known
Verizon 5G + double-NAT path and the host sitting on three bridged NICs, but
the first run was short and overlapped VM start-up, so it is not a baseline.
No em2 or em3 events yet because no client was generating traffic on those
VLANs. Next: a longer run for a real baseline, and a Lab client to produce
em3 block entries.

## 2026-10-31 — Phase 4: alert engine, API and dashboard

Added alerting (`netmon/alerts.py`), a read-only FastAPI backend
(`netmon/api.py`) and a React dashboard (`dashboard/`). `python -m unittest
discover -s tests -t .` now runs 38 tests, all passing (1 skipped: live
loopback ping, no `ping` binary in the build container).

| Area | Verified |
|---|---|
| Alert engine | A device alert needs 3 consecutive failures; one alert opens per condition and is not re-sent while it persists; it resolves when the condition clears; thresholds, windows and minimum-check counts behave; a dead webhook cannot raise |
| API | Every endpoint against a seeded database: uptime and loss maths, only unresolved alerts count as active, time series are ordered and bucketed, bad `hours` values are rejected, a path-traversal request cannot read files outside the dashboard folder |
| Dashboard | Built with Vite and rendered in a headless browser against generated demo data (`python -m netmon.demo`) in light and dark mode with no console errors; chart tooltips, the Show table toggle and the stale-collector banner checked |
| Palette | The two series colors used for ping targets pass the CVD and contrast checks in both themes |

Known limits: tooltips on the firewall column chart only appear over buckets
that contain data; DNS failures are not alerted on (a failed lookup is stored
the same as one that was not run); the API has no authentication, so it binds
to localhost.

Still to verify on the real lab: run collector, API and dashboard together
for a few hours, deliberately unplug a device to confirm a `device_down`
alert opens and resolves, and test the Discord webhook.

## 2026-11-03 — Phase 4 live: gateways "offline", switch VLAN leak, wrong route

The dashboard raised "IoT gateway is offline" and "Lab gateway is offline"
(plus a 10-50% loss reading on Trusted). Interfaces `em2`/`em3` were active
and the host's adapters had their VLAN addresses, so this was investigated
layer by layer.

| Check | Result | Meaning |
|---|---|---|
| `ping -n 50 10.10.10.1` from host | 0% loss, avg 5 ms | Trusted path healthy; the dashboard 50% was a stale window |
| `ping 10.10.20.1`, `10.10.30.1` from host | 100% loss | Real failure for IoT and Lab |
| `arp -a` on the host | Gateway MACs matched the VM's Adapter 3 and 4 MACs | Layer 2 and the VirtualBox adapter mapping were correct |
| IoT Live View | Only DNS replies passing; no ICMP entries at all | Pings were dropped by a rule that was not logging |
| IoT Live View after turning on Log for `block private network` | ICMP from `10.10.20.100` blocked by that rule | Root cause confirmed |
| IoT Live View | Default-deny hits from `192.168.50.54` and `192.168.50.1` | Home-LAN traffic was reaching `em2` |
| Switch 802.1Q page | VLAN 1 untagged on ports 1-7 | Second root cause: ports 3-7 were in VLAN 1 too |
| `Find-NetRoute 8.8.8.8` | Out Ethernet 5 via `192.168.50.1` (metric tie at 25) | Internet checks bypassed OPNsense |

Fixes applied and re-verified:

1. **Monitor pings.** Added `IoT - monitor pings` and `Lab - monitor pings`
   (ICMP echo from `10.10.20.100` / `10.10.30.100` to This Firewall, logged)
   above each block rule. Live View then showed `pass` entries for both
   VLANs and the offline alerts cleared.
2. **Switch.** Reduced VLAN 1 to ports 1-2; PVIDs confirmed 3/7=10, 4/6=20,
   5/8=30, 1/2=1. The `192.168.50.x` entries stopped appearing on IoT.
3. **Host routing.** Trusted adapter metric 10, home-router adapter 40;
   `Find-NetRoute 8.8.8.8` now exits the Trusted adapter via `10.10.10.1`.

Not yet done:

- [ ] Confirm Kea DHCP reservations for the host's IoT and Lab adapters
- [ ] Intermittent DNS on the Trusted VLAN: compare
      `nslookup google.com 10.10.10.1` with `nslookup google.com 8.8.8.8`;
      if only OPNsense is slow, enable Unbound query forwarding
- [ ] Multi-hour baseline now that the internet checks use the OPNsense path
- [ ] Test the Discord webhook
