"""Back up the OPNsense configuration over its API.

    python opnsense_backup.py --config backup.json           # daily job
    python opnsense_backup.py --config backup.json --check   # test credentials only
    python opnsense_backup.py --status --max-age-hours 48    # exit 1 if stale
    python opnsense_backup.py --redact-only config.xml       # sanitize a manual export
    python opnsense_backup.py --print-fingerprint https://10.10.10.1

What one run does:
  1. Downloads config.xml from the firewall (HTTP basic auth with an API key).
  2. Checks it really is an OPNsense config, not a login page or an error.
  3. Saves a full copy outside the repo, but only if it changed since the last one.
  4. Deletes old full copies (keeps the newest few, plus anything under keep_days).
  5. Writes a redacted copy, with every secret stripped, that is safe to commit.
  6. Records the result in status.json and (optionally) warns a Discord webhook on failure.

Standard library only, Python 3.9+.
"""
import argparse
import base64
import hashlib
import hmac
import http.client
import json
import os
import re
import socket
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
DEFAULTS = {
    "url": "https://10.10.10.1",
    "endpoint": "/api/core/backup/download/this",
    "api_key": "",
    "api_secret": "",
    "tls_fingerprint": "",     # SHA-256 of the firewall's certificate (best option)
    "ca_file": "",             # or a PEM file that signed it
    "verify_tls": True,        # false = accept any certificate (not recommended)
    "backup_dir": "~/opnsense-backups",
    "keep_days": 30,
    "keep_min": 5,
    "redacted_path": "../config-backups/config-redacted.xml",
    "discord_webhook": "",
    "timeout_s": 20,
}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
TS_FORMAT = "%Y%m%d-%H%M%S"


class BackupError(Exception):
    """Something failed in a way the operator should see."""


class RedactionError(BackupError):
    """The redacted copy still looked like it contained a secret."""


# --- configuration ---------------------------------------------------------

def load_config(path):
    cfg = dict(DEFAULTS)
    p = Path(path)
    if p.is_file():
        with p.open(encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    cfg["api_key"] = os.environ.get("OPNSENSE_API_KEY") or cfg["api_key"]
    cfg["api_secret"] = os.environ.get("OPNSENSE_API_SECRET") or cfg["api_secret"]
    cfg["discord_webhook"] = os.environ.get("NETMON_DISCORD_WEBHOOK") or cfg["discord_webhook"]
    base = p.resolve().parent if p.is_file() else Path.cwd()
    if cfg["redacted_path"] and not Path(cfg["redacted_path"]).is_absolute():
        cfg["redacted_path"] = str((base / cfg["redacted_path"]).resolve())
    return cfg


# --- fetching --------------------------------------------------------------

def normalize_fingerprint(text):
    return re.sub(r"[^0-9a-f]", "", text.lower())


def fingerprint_matches(der_cert, expected):
    actual = hashlib.sha256(der_cert).hexdigest()
    return hmac.compare_digest(actual, normalize_fingerprint(expected))


def _tls_context(cfg):
    if cfg["tls_fingerprint"] or not cfg["verify_tls"]:
        # Chain validation is replaced by the fingerprint check (or skipped).
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if cfg["ca_file"]:
        return ssl.create_default_context(cafile=cfg["ca_file"])
    return ssl.create_default_context()


def fetch_config(cfg):
    """Download config.xml and return its bytes."""
    if not cfg["api_key"] or not cfg["api_secret"]:
        raise BackupError("api_key / api_secret missing (set them in backup.json or the "
                          "OPNSENSE_API_KEY / OPNSENSE_API_SECRET environment variables)")
    u = urllib.parse.urlsplit(cfg["url"])
    host = u.hostname
    if not host:
        raise BackupError(f"bad url: {cfg['url']!r}")
    timeout = cfg["timeout_s"]
    if u.scheme == "https":
        conn = http.client.HTTPSConnection(host, u.port or 443, timeout=timeout,
                                           context=_tls_context(cfg))
    elif u.scheme == "http":
        if host not in LOCAL_HOSTS:
            raise BackupError("refusing plain http to a non-local host: the API secret "
                              "would cross the network unencrypted")
        conn = http.client.HTTPConnection(host, u.port or 80, timeout=timeout)
    else:
        raise BackupError(f"unsupported url scheme: {u.scheme!r}")

    try:
        try:
            conn.connect()
        except ssl.SSLCertVerificationError as exc:
            raise BackupError(
                f"TLS certificate not trusted ({exc.verify_message}). Pin it with "
                f"tls_fingerprint (see --print-fingerprint) or set ca_file."
            ) from exc
        except (OSError, ssl.SSLError) as exc:
            raise BackupError(f"cannot connect to {host}: {exc}") from exc

        # Check the certificate BEFORE sending the credentials.
        if u.scheme == "https" and cfg["tls_fingerprint"]:
            der = conn.sock.getpeercert(binary_form=True)
            if not fingerprint_matches(der, cfg["tls_fingerprint"]):
                raise BackupError("certificate fingerprint does not match tls_fingerprint; "
                                  "refusing to send credentials (wrong host, or the firewall "
                                  "certificate was regenerated)")

        token = base64.b64encode(f"{cfg['api_key']}:{cfg['api_secret']}".encode()).decode()
        conn.request("GET", cfg["endpoint"], headers={
            "Authorization": f"Basic {token}",
            "User-Agent": "opnsense-backup/1.0",
            "Accept": "application/xml, text/xml, */*",
        })
        resp = conn.getresponse()
        body = resp.read(MAX_BYTES + 1)
    except (OSError, http.client.HTTPException) as exc:
        raise BackupError(f"request failed: {exc}") from exc
    finally:
        conn.close()

    if resp.status in (401, 403):
        raise BackupError(f"HTTP {resp.status}: the API key was refused. Check the key and "
                          f"secret, and that the user has the Backups / Configuration "
                          f"History privilege")
    if resp.status == 404:
        raise BackupError(f"HTTP 404: no such endpoint ({cfg['endpoint']}). The path differs "
                          f"between OPNsense versions; set `endpoint` in backup.json")
    if resp.status != 200:
        raise BackupError(f"HTTP {resp.status} from the firewall")
    if len(body) > MAX_BYTES:
        raise BackupError("response larger than 20 MB; refusing to store it")
    return body


def validate_config(body):
    """Raise unless `body` is an OPNsense config.xml. Returns the parsed root."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise BackupError(f"response is not XML (a login page or error?): {exc}") from exc
    if root.tag != "opnsense":
        raise BackupError(f"unexpected XML root <{root.tag}>, expected <opnsense>")
    return root


# --- redaction -------------------------------------------------------------

# Any element whose tag contains one of these, or equals one of the exact names,
# has its value (and children) replaced. Deliberately broad: losing a harmless
# value from the public copy costs little, leaking a secret costs a lot.
SENSITIVE_SUBSTRINGS = (
    "password", "passwd", "secret", "privkey", "private", "psk", "pre-shared",
    "preshared", "apikey", "api_key", "token", "community", "authorizedkeys",
    "otp", "bindpw", "shared_key", "sharedkey", "passphrase", "hash", "seed",
)
SENSITIVE_EXACT = {"key", "prv", "crt", "csr", "pass", "tls", "tlsauth"}

# Last line of defence: if any of these survive redaction, nothing is written.
LEAK_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"-----BEGIN CERTIFICATE-----"),
    re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{50,}"),            # bcrypt
    re.compile(r"\$[156]\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{20,}"),  # crypt(3)
]


def _is_sensitive(tag):
    t = tag.lower()
    return t in SENSITIVE_EXACT or any(s in t for s in SENSITIVE_SUBSTRINGS)


def _redact(el):
    count = 0
    for child in list(el):
        if _is_sensitive(child.tag):
            if (child.text or "").strip() or len(child):
                for grandchild in list(child):
                    child.remove(grandchild)
                child.text = "REDACTED"
                count += 1
            continue
        count += _redact(child)
    return count


def redact(body):
    """Return (redacted_xml_bytes, number_of_values_redacted)."""
    root = validate_config(body)
    n = _redact(root)
    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):
        ET.indent(tree)
    out = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    text = out.decode("utf-8")
    for pat in LEAK_PATTERNS:
        if pat.search(text):
            raise RedactionError(
                f"redacted copy still matches a secret pattern ({pat.pattern[:30]}...); "
                f"not writing it. Add the offending tag to SENSITIVE_SUBSTRINGS."
            )
    return out, n


# --- storage ---------------------------------------------------------------

def _parse_ts(path):
    m = re.fullmatch(r"config-(\d{8}-\d{6})\.xml", path.name)
    if not m:
        return None
    return datetime.strptime(m.group(1), TS_FORMAT).replace(tzinfo=timezone.utc)


def list_backups(bdir):
    """Newest first: [(timestamp, path)]."""
    items = [(ts, p) for p in Path(bdir).glob("config-*.xml") if (ts := _parse_ts(p))]
    return sorted(items, key=lambda x: x[0], reverse=True)


def _atomic_write(path, data, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    if private:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)


def rotate(bdir, keep_days, keep_min, now):
    """Delete full backups older than keep_days, always keeping the newest keep_min."""
    deleted = []
    for i, (ts, p) in enumerate(list_backups(bdir)):
        if i < keep_min:
            continue
        if now - ts > timedelta(days=keep_days):
            p.unlink()
            deleted.append(p.name)
    return deleted


def write_status(bdir, **fields):
    path = Path(bdir) / "status.json"
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    data.update(fields)
    _atomic_write(path, json.dumps(data, indent=2).encode())


# --- the job ---------------------------------------------------------------

def run(cfg, now=None, fetch=None):
    now = now or datetime.now(timezone.utc)
    fetch = fetch or fetch_config
    body = fetch(cfg)
    validate_config(body)
    digest = hashlib.sha256(body).hexdigest()

    bdir = Path(cfg["backup_dir"]).expanduser()
    bdir.mkdir(parents=True, exist_ok=True)
    backups = list_backups(bdir)
    changed = not backups or hashlib.sha256(backups[0][1].read_bytes()).hexdigest() != digest
    saved = None
    if changed:
        saved = f"config-{now.strftime(TS_FORMAT)}.xml"
        _atomic_write(bdir / saved, body, private=True)
    deleted = rotate(bdir, cfg["keep_days"], cfg["keep_min"], now)

    result = {"changed": changed, "saved": saved, "bytes": len(body), "sha256": digest,
              "deleted": deleted, "redacted_path": None, "redacted_count": 0,
              "redaction_error": None}
    if cfg.get("redacted_path"):
        try:
            red, n = redact(body)
            target = Path(cfg["redacted_path"])
            if not target.is_file() or target.read_bytes() != red:
                _atomic_write(target, red)
            result.update(redacted_path=str(target), redacted_count=n)
        except RedactionError as exc:
            result["redaction_error"] = str(exc)

    write_status(bdir, last_success_ts=now.timestamp(), last_success=now.isoformat(),
                 sha256=digest, bytes=len(body), last_error=result["redaction_error"],
                 last_change=(now.isoformat() if changed else None) or None)
    return result


def notify(cfg, text):
    hook = cfg.get("discord_webhook")
    if not hook:
        return False
    req = urllib.request.Request(
        hook, data=json.dumps({"content": text}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "opnsense-backup/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception as exc:  # noqa: BLE001 - a dead webhook must not hide the real error
        print(f"notification failed: {exc}", file=sys.stderr)
        return False


def print_fingerprint(url):
    u = urllib.parse.urlsplit(url)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((u.hostname, u.port or 443), timeout=10) as raw:
        with ctx.wrap_socket(raw, server_hostname=u.hostname) as tls:
            der = tls.getpeercert(binary_form=True)
    fp = hashlib.sha256(der).hexdigest()
    return ":".join(fp[i:i + 2] for i in range(0, len(fp), 2))


def main(argv=None):
    ap = argparse.ArgumentParser(description="OPNsense config backup")
    ap.add_argument("--config", default=str(Path(__file__).with_name("backup.json")))
    ap.add_argument("--check", action="store_true", help="download and validate only")
    ap.add_argument("--status", action="store_true", help="show the last successful backup")
    ap.add_argument("--max-age-hours", type=float, default=48)
    ap.add_argument("--redact-only", metavar="FILE", help="sanitize an exported config.xml")
    ap.add_argument("--out", help="output path for --redact-only")
    ap.add_argument("--print-fingerprint", metavar="URL")
    args = ap.parse_args(argv)

    if args.print_fingerprint:
        print(print_fingerprint(args.print_fingerprint))
        return 0

    if args.redact_only:
        src = Path(args.redact_only)
        red, n = redact(src.read_bytes())
        out = Path(args.out) if args.out else src.with_name(src.stem + "-redacted.xml")
        out.write_bytes(red)
        print(f"redacted {n} values -> {out}")
        return 0

    cfg = load_config(args.config)

    if args.status:
        sp = Path(cfg["backup_dir"]).expanduser() / "status.json"
        if not sp.is_file():
            print("no backup has ever completed")
            return 1
        st = json.loads(sp.read_text(encoding="utf-8"))
        age_h = (datetime.now(timezone.utc).timestamp() - st["last_success_ts"]) / 3600
        print(f"last success {age_h:.1f} h ago ({st['last_success']})")
        return 0 if age_h <= args.max_age_hours else 1

    try:
        if args.check:
            body = fetch_config(cfg)
            validate_config(body)
            print(f"OK: downloaded {len(body):,} bytes of valid OPNsense config")
            return 0
        r = run(cfg)
    except BackupError as exc:
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        notify(cfg, f"OPNsense config backup FAILED: {exc}")
        return 1

    print("saved " + r["saved"] if r["changed"] else "config unchanged since last backup")
    if r["deleted"]:
        print(f"removed {len(r['deleted'])} old backup(s)")
    if r["redacted_path"]:
        print(f"redacted copy ({r['redacted_count']} values hidden): {r['redacted_path']}")
    if r["redaction_error"]:
        print(f"REDACTION FAILED, nothing written to the repo: {r['redaction_error']}",
              file=sys.stderr)
        notify(cfg, f"OPNsense backup saved, but the redacted copy failed: {r['redaction_error']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
