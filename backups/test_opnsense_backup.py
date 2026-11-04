import base64, hashlib, json, tempfile, threading, unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import opnsense_backup as ob

SAMPLE = b"""<?xml version="1.0"?>
<opnsense>
  <system>
    <hostname>fw</hostname>
    <user><name>root</name><password>$2y$10$abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456</password>
      <apikeys><item><key>APIKEYVALUE</key><secret>APISECRETVALUE</secret></item></apikeys></user>
  </system>
  <cert><descr>web</descr><crt>CERTDATA</crt><prv>PRIVDATA</prv></cert>
  <snmpd><rocommunity>public</rocommunity></snmpd>
  <interfaces><lan><if>em1</if><ipaddr>10.10.10.1</ipaddr></lan></interfaces>
</opnsense>"""


class Handler(BaseHTTPRequestHandler):
    body = SAMPLE
    status = 200
    seen_auth = None

    def do_GET(self):
        Handler.seen_auth = self.headers.get("Authorization")
        self.send_response(Handler.status)
        self.end_headers()
        self.wfile.write(Handler.body)

    def log_message(self, *a):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        Handler.body, Handler.status, Handler.seen_auth = SAMPLE, 200, None
        self.srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.cfg = dict(ob.DEFAULTS, url=f"http://127.0.0.1:{self.srv.server_port}",
                        api_key="k", api_secret="s", backup_dir=str(self.tmp / "b"),
                        redacted_path=str(self.tmp / "red" / "c.xml"))

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()


class Fetch(Base):
    def test_ok_and_basic_auth(self):
        self.assertEqual(ob.fetch_config(self.cfg), SAMPLE)
        self.assertEqual(Handler.seen_auth, "Basic " + base64.b64encode(b"k:s").decode())

    def test_errors(self):
        for code, word in ((401, "refused"), (403, "refused"), (404, "endpoint"), (500, "500")):
            Handler.status = code
            with self.assertRaisesRegex(ob.BackupError, word):
                ob.fetch_config(self.cfg)

    def test_missing_credentials(self):
        with self.assertRaises(ob.BackupError):
            ob.fetch_config(dict(self.cfg, api_key=""))

    def test_refuses_plain_http_remote(self):
        with self.assertRaisesRegex(ob.BackupError, "plain http"):
            ob.fetch_config(dict(self.cfg, url="http://10.10.10.1"))

    def test_unreachable(self):
        self.srv.shutdown()
        with self.assertRaises(ob.BackupError):
            ob.fetch_config(self.cfg)

    def test_fingerprint(self):
        der = b"certbytes"
        fp = hashlib.sha256(der).hexdigest()
        self.assertTrue(ob.fingerprint_matches(der, fp.upper()))
        self.assertTrue(ob.fingerprint_matches(der, ":".join(fp[i:i+2] for i in range(0, 64, 2))))
        self.assertFalse(ob.fingerprint_matches(der, "00" * 32))


class Validate(unittest.TestCase):
    def test_validate(self):
        self.assertEqual(ob.validate_config(SAMPLE).tag, "opnsense")
        for bad in (b"<html><body>login</body></html>", b"not xml", b""):
            with self.assertRaises(ob.BackupError):
                ob.validate_config(bad)


class Redact(unittest.TestCase):
    def test_secrets_removed_and_structure_kept(self):
        out, n = ob.redact(SAMPLE)
        text = out.decode()
        for secret in ("$2y$10$", "APIKEYVALUE", "APISECRETVALUE", "CERTDATA", "PRIVDATA", "public"):
            self.assertNotIn(secret, text)
        for kept in ("<hostname>fw</hostname>", "10.10.10.1", "em1"):
            self.assertIn(kept, text)
        self.assertGreaterEqual(n, 5)

    def test_idempotent(self):
        once, _ = ob.redact(SAMPLE)
        twice, _ = ob.redact(once)
        self.assertEqual(once, twice)

    def test_leak_scan_fails_closed(self):
        leaky = b"<opnsense><system><notes>-----BEGIN RSA PRIVATE KEY-----\nabc</notes></system></opnsense>"
        with self.assertRaises(ob.RedactionError):
            ob.redact(leaky)
        hash_in_odd_tag = (b"<opnsense><x><thing>$2y$10$" + b"a" * 53 + b"</thing></x></opnsense>")
        with self.assertRaises(ob.RedactionError):
            ob.redact(hash_in_odd_tag)


class Run(Base):
    def test_save_dedupe_and_redacted(self):
        t0 = datetime(2026, 11, 4, 3, 0, tzinfo=timezone.utc)
        r1 = ob.run(self.cfg, now=t0)
        self.assertTrue(r1["changed"])
        self.assertEqual(len(ob.list_backups(self.cfg["backup_dir"])), 1)
        self.assertTrue(Path(self.cfg["redacted_path"]).is_file())
        r2 = ob.run(self.cfg, now=t0 + timedelta(days=1))
        self.assertFalse(r2["changed"])
        self.assertEqual(len(ob.list_backups(self.cfg["backup_dir"])), 1)
        Handler.body = SAMPLE.replace(b"<hostname>fw", b"<hostname>fw2")
        self.assertTrue(ob.run(self.cfg, now=t0 + timedelta(days=2))["changed"])
        self.assertEqual(len(ob.list_backups(self.cfg["backup_dir"])), 2)
        st = json.loads((Path(self.cfg["backup_dir"]) / "status.json").read_text())
        self.assertIn("last_success_ts", st)

    def test_html_response_not_saved(self):
        Handler.body = b"<html>login</html>"
        with self.assertRaises(ob.BackupError):
            ob.run(self.cfg)
        self.assertFalse(list(Path(self.cfg["backup_dir"]).glob("config-*")) if Path(self.cfg["backup_dir"]).exists() else [])

    def test_redaction_failure_blocks_repo_copy_but_keeps_backup(self):
        Handler.body = b"<opnsense><a>-----BEGIN PRIVATE KEY-----</a></opnsense>"
        r = ob.run(self.cfg)
        self.assertTrue(r["redaction_error"])
        self.assertFalse(Path(self.cfg["redacted_path"]).exists())
        self.assertEqual(len(ob.list_backups(self.cfg["backup_dir"])), 1)

    def test_main_returns_nonzero_on_redaction_failure(self):
        Handler.body = b"<opnsense><a>-----BEGIN PRIVATE KEY-----</a></opnsense>"
        c = self.tmp / "c.json"
        c.write_text(json.dumps({k: self.cfg[k] for k in ("url", "api_key", "api_secret", "backup_dir", "redacted_path")}))
        self.assertEqual(ob.main(["--config", str(c)]), 1)


class Rotate(unittest.TestCase):
    def test_rotation(self):
        d = Path(tempfile.mkdtemp())
        now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        for days in (0, 1, 10, 40, 50, 60, 70):
            (d / f"config-{(now - timedelta(days=days)).strftime(ob.TS_FORMAT)}.xml").write_text("x")
        (d / "unrelated.xml").write_text("keep")
        ob.rotate(d, keep_days=30, keep_min=5, now=now)
        left = [p.name for _, p in ob.list_backups(d)]
        self.assertEqual(len(left), 5)          # keep_min protects the 5 newest
        ob.rotate(d, keep_days=30, keep_min=3, now=now)
        self.assertEqual(len(ob.list_backups(d)), 3)  # 0,1,10 days
        self.assertTrue((d / "unrelated.xml").exists())


class Status(Base):
    def test_status_exit_codes(self):
        c = self.tmp / "c.json"
        c.write_text(json.dumps({"backup_dir": self.cfg["backup_dir"]}))
        self.assertEqual(ob.main(["--config", str(c), "--status"]), 1)
        ob.run(self.cfg)
        self.assertEqual(ob.main(["--config", str(c), "--status"]), 0)
        ob.write_status(self.cfg["backup_dir"], last_success_ts=0, last_success="old")
        self.assertEqual(ob.main(["--config", str(c), "--status"]), 1)

    def test_redact_only(self):
        src = self.tmp / "in.xml"; src.write_bytes(SAMPLE)
        out = self.tmp / "out.xml"
        self.assertEqual(ob.main(["--redact-only", str(src), "--out", str(out)]), 0)
        self.assertNotIn("APIKEYVALUE", out.read_text())


if __name__ == "__main__":
    unittest.main()
