import os
import socket
import struct
import tempfile
import threading
import time
import unittest

from netmon import checks, db, report, runner, syslog_listener

WIN_OK = "Reply from 8.8.8.8: bytes=32 time=27ms TTL=250"
WIN_FAST = "Reply from 10.10.10.1: bytes=32 time<1ms TTL=64"
WIN_UNREACH = "Reply from 10.10.10.100: Destination host unreachable."
WIN_TIMEOUT = "Request timed out."
LINUX_OK = "64 bytes from 8.8.8.8: icmp_seq=1 ttl=117 time=12.4 ms"

# Real-shaped OPNsense filterlog lines (IPv4 UDP/TCP/ICMP, IPv6)
FL_BLOCK_ICMP = (
    "<134>1 2026-10-28T14:00:00-05:00 OPNsense.internal filterlog 12345 - "
    "[meta sequenceId=\"1\"] 87,,,0123456789abcdef,em3,match,block,in,4,0x0,,64,"
    "1234,0,none,1,icmp,60,10.10.30.101,10.10.10.1,request,1,1"
)
FL_PASS_DNS = (
    "<134>1 2026-10-28T14:00:01-05:00 OPNsense.internal filterlog 12345 - "
    "[meta sequenceId=\"2\"] 85,,,fedcba9876543210,em3,match,pass,in,4,0x0,,128,"
    "4321,0,DF,17,udp,62,10.10.30.101,10.10.30.1,50238,53,42"
)
FL_BLOCK_TCP = (
    "<134>1 2026-10-28T14:00:02-05:00 OPNsense.internal filterlog 1 - - "
    "88,,,aaaa,em2,match,block,in,4,0x0,,64,9,0,DF,6,tcp,60,10.10.20.101,"
    "192.168.50.1,51000,443,0,S,1,,,"
)
FL_V6 = (
    "<134>1 2026-10-28T14:00:03-05:00 OPNsense.internal filterlog 1 - - "
    "90,,,bbbb,em1,match,pass,in,6,0x00,0x00000,255,ICMPv6,58,32,fe80::1,ff02::1"
)


class PingParse(unittest.TestCase):
    def test_windows_reply(self):
        self.assertEqual(checks.parse_ping_rtt(WIN_OK), 27.0)

    def test_windows_sub_ms(self):
        self.assertEqual(checks.parse_ping_rtt(WIN_FAST), 0.5)

    def test_linux_reply(self):
        self.assertEqual(checks.parse_ping_rtt(LINUX_OK), 12.4)

    def test_no_reply_variants(self):
        # "Destination host unreachable" has a Reply line but no time= value;
        # it must count as down.
        self.assertIsNone(checks.parse_ping_rtt(WIN_UNREACH))
        self.assertIsNone(checks.parse_ping_rtt(WIN_TIMEOUT))

    def test_loopback_live(self):
        up, rtt = checks.ping("127.0.0.1")
        if not up:
            self.skipTest("ping binary unavailable in this environment")
        self.assertIsNotNone(rtt)


class FilterlogParse(unittest.TestCase):
    def test_blocked_icmp(self):
        ev = syslog_listener.parse_filterlog(FL_BLOCK_ICMP)
        self.assertEqual(
            (ev["iface"], ev["action"], ev["proto"], ev["src"], ev["dst"]),
            ("em3", "block", "icmp", "10.10.30.101", "10.10.10.1"),
        )
        self.assertIsNone(ev["dst_port"])

    def test_passed_dns_has_ports(self):
        ev = syslog_listener.parse_filterlog(FL_PASS_DNS)
        self.assertEqual(ev["action"], "pass")
        self.assertEqual((ev["src_port"], ev["dst_port"]), (50238, 53))

    def test_blocked_tcp(self):
        ev = syslog_listener.parse_filterlog(FL_BLOCK_TCP)
        self.assertEqual((ev["iface"], ev["proto"], ev["dst_port"]), ("em2", "tcp", 443))

    def test_ipv6_and_garbage_skipped(self):
        self.assertIsNone(syslog_listener.parse_filterlog(FL_V6))
        self.assertIsNone(syslog_listener.parse_filterlog("sshd: accepted password"))
        self.assertIsNone(syslog_listener.parse_filterlog("filterlog: 1,2,3"))


class FakeDnsServer:
    """UDP server answering any A query; rcode configurable."""

    def __init__(self, rcode=0, delay=0.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.rcode, self.delay = rcode, delay
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        self.sock.settimeout(3)
        try:
            data, addr = self.sock.recvfrom(512)
        except socket.timeout:
            return
        time.sleep(self.delay)
        tid = data[:2]
        flags = struct.pack(">H", 0x8180 | self.rcode)
        self.sock.sendto(tid + flags + data[4:], addr)

    def close(self):
        self.sock.close()


class DnsLookup(unittest.TestCase):
    def _lookup(self, srv):
        # dns_lookup_ms hardcodes port 53; patch socket.sendto target port.
        real = socket.socket.sendto

        def redirect(sock, data, addr):
            # Only redirect queries aimed at port 53; the fake server's own
            # replies go through this same patched method and must be left alone.
            if addr[1] == 53:
                addr = ("127.0.0.1", srv.port)
            return real(sock, data, addr)

        socket.socket.sendto = redirect
        try:
            return checks.dns_lookup_ms("127.0.0.1", "google.com", timeout_s=1)
        finally:
            socket.socket.sendto = real

    def test_success_returns_ms(self):
        srv = FakeDnsServer(delay=0.05)
        ms = self._lookup(srv)
        srv.close()
        self.assertIsNotNone(ms)
        self.assertGreaterEqual(ms, 40)

    def test_nxdomain_is_failure(self):
        srv = FakeDnsServer(rcode=3)
        self.assertIsNone(self._lookup(srv))
        srv.close()

    def test_timeout_is_failure(self):
        srv = FakeDnsServer(delay=2)
        self.assertIsNone(self._lookup(srv))
        srv.close()

    def test_query_packet_shape(self):
        tid, pkt = checks._build_dns_query("google.com")
        self.assertEqual(struct.unpack(">H", pkt[:2])[0], tid)
        self.assertIn(b"\x06google\x03com\x00", pkt)


class Storage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "t.db")
        self.conn = db.connect(self.path)

    def test_device_upsert_is_idempotent(self):
        a = db.upsert_device(self.conn, "gw", "10.10.10.1", 10)
        b = db.upsert_device(self.conn, "gw", "10.10.10.2", 10)
        self.assertEqual(a, b)
        row = self.conn.execute("SELECT ip FROM devices").fetchone()
        self.assertEqual(row["ip"], "10.10.10.2")

    def test_report_math(self):
        did = db.upsert_device(self.conn, "gw", "10.10.10.1", 10)
        now = time.time()
        for up, rtt in [(True, 10.0), (True, 20.0), (False, None), (True, 30.0)]:
            db.record_device_check(self.conn, did, up, rtt, ts=now)
        # an old row outside the window must be ignored
        db.record_device_check(self.conn, did, False, None, ts=now - 10 * 3600)
        r = report.device_summary(self.conn, now - 3600)[0]
        self.assertEqual(r["checks"], 4)
        self.assertAlmostEqual(r["uptime_pct"], 75.0)
        self.assertAlmostEqual(r["avg_rtt"], 20.0)

    def test_internet_loss_and_dns(self):
        now = time.time()
        db.record_internet_check(self.conn, "8.8.8.8", True, 100.0, 40.0, ts=now)
        db.record_internet_check(self.conn, "8.8.8.8", False, None, None, ts=now)
        r = report.internet_summary(self.conn, now - 60)[0]
        self.assertAlmostEqual(r["loss_pct"], 50.0)
        self.assertAlmostEqual(r["avg_dns"], 40.0)

    def test_empty_device_has_null_uptime(self):
        db.upsert_device(self.conn, "new", "10.10.10.9", 10)
        r = report.device_summary(self.conn, time.time() - 60)[0]
        self.assertEqual(r["checks"], 0)
        self.assertIsNone(r["uptime_pct"])


class SyslogIntegration(unittest.TestCase):
    def test_udp_to_db(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "s.db")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        stop = threading.Event()
        syslog_listener.start(path, "127.0.0.1", port, stop)
        time.sleep(0.3)
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for line in (FL_BLOCK_ICMP, FL_PASS_DNS, FL_V6, "noise"):
            tx.sendto(line.encode(), ("127.0.0.1", port))
        time.sleep(0.5)
        stop.set()
        conn = db.connect(path)
        rows = report.firewall_summary(conn, 0)
        got = {(r["iface"], r["action"]): r["n"] for r in rows}
        self.assertEqual(got, {("em3", "block"): 1, ("em3", "pass"): 1})


class RunnerCycle(unittest.TestCase):
    def test_run_once_writes_rows(self):
        tmp = tempfile.mkdtemp()
        cfg = {
            "db_path": os.path.join(tmp, "r.db"),
            "interval_seconds": 1,
            "devices": [{"name": "loop", "ip": "127.0.0.1", "vlan": 1}],
            "internet": {"ping_targets": ["127.0.0.1"]},
            "syslog": {"enabled": False},
        }
        conn = db.connect(cfg["db_path"])
        ids = {"loop": db.upsert_device(conn, "loop", "127.0.0.1", 1)}
        runner.run_once(conn, cfg, ids)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM device_checks").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM internet_checks").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
