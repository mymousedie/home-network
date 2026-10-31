"""Receive OPNsense firewall logs over remote syslog (UDP) and store them.

OPNsense emits one `filterlog` line per logged packet, with comma-separated
fields. Only rules with the "Log" checkbox ticked produce lines, so the
Log checkbox must be enabled on the rules you want counted.

Field layout (IPv4), after the "filterlog[pid]: " prefix:
  0 rule#  1 subrule  2 anchor  3 tracker  4 interface  5 reason  6 action
  7 direction  8 ip version  9 tos  10 ecn  11 ttl  12 id  13 offset
  14 flags  15 proto number  16 proto name  17 length  18 src  19 dst
  then for tcp/udp: 20 src port  21 dst port ...
"""
import re
import socket
import threading

from . import db


# OPNsense can forward in either syslog format; the filterlog CSV payload is
# the same, only the header differs:
#   RFC 3164: <134>Oct 28 14:00:00 host filterlog[123]: 87,,,...
#   RFC 5424: <134>1 2026-10-28T14:00:00-05:00 host filterlog 123 - [meta ...] 87,,,...
_PAYLOAD_3164 = re.compile(r"filterlog(?:\[\d+\])?:\s+(?P<p>.*)$")
_PAYLOAD_5424 = re.compile(r"filterlog\s+\S+\s+\S+\s+(?:-|(?:\[[^\]]*\])+)\s+(?P<p>.*)$")


def parse_filterlog(line):
    """Parse one syslog line. Returns a dict, or None if it isn't a usable
    IPv4 filterlog entry."""
    m = _PAYLOAD_3164.search(line) or _PAYLOAD_5424.search(line)
    if not m:
        return None
    f = m.group("p").strip().split(",")
    if len(f) < 20 or f[8] != "4":
        return None  # IPv6 and malformed lines are skipped for now
    ev = {
        "iface": f[4],
        "action": f[6],
        "direction": f[7],
        "proto": f[16].lower(),
        "src": f[18],
        "dst": f[19],
        "src_port": None,
        "dst_port": None,
    }
    if ev["proto"] in ("tcp", "udp") and len(f) >= 22:
        try:
            ev["src_port"] = int(f[20])
            ev["dst_port"] = int(f[21])
        except ValueError:
            pass
    return ev


def serve(conn, bind, port, stop_event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind, port))
    sock.settimeout(1.0)
    try:
        while not stop_event.is_set():
            try:
                data, _addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            ev = parse_filterlog(data.decode("utf-8", errors="replace"))
            if ev:
                db.record_fw_event(conn, ev)
    finally:
        sock.close()


def start(db_path, bind, port, stop_event):
    # Own connection: sqlite connections shouldn't be shared across threads
    # for writes without extra locking.
    conn = db.connect(db_path)
    t = threading.Thread(
        target=serve, args=(conn, bind, port, stop_event), daemon=True, name="syslog"
    )
    t.start()
    return t
