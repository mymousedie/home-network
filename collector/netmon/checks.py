"""Active checks: ICMP ping and DNS lookup timing. Standard library only,
works on Windows (the collector's target host) and Linux."""
import os
import random
import re
import socket
import struct
import subprocess
import time

IS_WINDOWS = os.name == "nt"

# Windows prints "time=27ms" or "time<1ms"; Linux prints "time=27.4 ms".
_RTT_RE = re.compile(r"time\s*([=<])\s*([\d.]+)\s*ms", re.IGNORECASE)


def parse_ping_rtt(output):
    """Return RTT in ms from ping output, or None if there was no reply."""
    m = _RTT_RE.search(output)
    if not m:
        return None
    rtt = float(m.group(2))
    # "time<1ms" means under 1 ms; report 0.5 rather than 1 so it isn't overstated.
    if m.group(1) == "<":
        rtt = rtt / 2
    return rtt


def ping(host, timeout_s=2):
    """Send one ICMP echo. Returns (up, rtt_ms)."""
    if IS_WINDOWS:
        cmd = ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(int(timeout_s)), host]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s + 3
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, None
    rtt = parse_ping_rtt(proc.stdout)
    # Windows can print "Reply from <other host>: Destination host unreachable"
    # with exit code 0, so require an actual time= value, not just exit status.
    if rtt is None:
        return False, None
    return True, rtt


def _build_dns_query(name):
    tid = random.randint(0, 0xFFFF)
    header = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)  # RD set, 1 question
    qname = b"".join(
        bytes([len(label)]) + label.encode("ascii") for label in name.split(".")
    ) + b"\x00"
    question = qname + struct.pack(">HH", 1, 1)  # type A, class IN
    return tid, header + question


def dns_lookup_ms(server, name, timeout_s=2):
    """Time an A-record lookup against a specific resolver.

    Returns elapsed ms, or None on timeout / non-success response code.
    Queries the resolver directly (rather than using the OS resolver) so the
    result reflects OPNsense's Unbound, not whatever the host happens to use.
    """
    tid, packet = _build_dns_query(name)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout_s)
    try:
        start = time.perf_counter()
        sock.sendto(packet, (server, 53))
        data, _ = sock.recvfrom(512)
        elapsed = (time.perf_counter() - start) * 1000
    except (socket.timeout, OSError):
        return None
    finally:
        sock.close()
    if len(data) < 12:
        return None
    rid, flags = struct.unpack(">HH", data[:4])
    rcode = flags & 0x000F
    if rid != tid or rcode != 0:
        return None
    return elapsed
