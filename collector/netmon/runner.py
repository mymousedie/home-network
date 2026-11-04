"""Collector entry point.

    python -m netmon.runner --config config.json

Every interval it pings each configured device and the internet targets,
times a DNS lookup, and stores the results. If syslog is enabled, a
background thread also records OPNsense firewall log events. After each
cycle the alert engine opens/clears critical alerts and posts to Discord.
"""
import argparse
import json
import os
import signal
import sys
import threading

from . import alerts, checks, db, notify, syslog_listener


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg.setdefault("db_path", "netmon.db")
    cfg.setdefault("interval_seconds", 30)
    cfg.setdefault("devices", [])
    cfg.setdefault("internet", {})
    cfg.setdefault("syslog", {"enabled": False})
    # Secrets (Discord webhook) live in a .env next to the config.
    notify.load_env_file(os.path.join(os.path.dirname(os.path.abspath(path)), ".env"))
    return cfg


def run_once(conn, cfg, device_ids):
    for dev in cfg["devices"]:
        up, rtt = checks.ping(dev["ip"])
        db.record_device_check(conn, device_ids[dev["name"]], up, rtt)

    inet = cfg["internet"]
    dns_ms = None
    if inet.get("dns_server") and inet.get("dns_name"):
        dns_ms = checks.dns_lookup_ms(inet["dns_server"], inet["dns_name"])
    for i, target in enumerate(inet.get("ping_targets", [])):
        up, rtt = checks.ping(target)
        # Store the DNS timing once per cycle, on the first target's row.
        db.record_internet_check(conn, target, up, rtt, dns_ms if i == 0 else None)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Home network monitoring collector")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    conn = db.connect(cfg["db_path"])
    device_ids = {
        d["name"]: db.upsert_device(conn, d["name"], d["ip"], d.get("vlan"))
        for d in cfg["devices"]
    }

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    sl = cfg["syslog"]
    if sl.get("enabled") and not args.once:
        syslog_listener.start(
            cfg["db_path"], sl.get("bind", "0.0.0.0"), sl.get("port", 5514), stop
        )
        print(f"syslog listener on {sl.get('bind', '0.0.0.0')}:{sl.get('port', 5514)}")

    print(f"collecting every {cfg['interval_seconds']}s -> {cfg['db_path']} (Ctrl+C to stop)")
    while not stop.is_set():
        run_once(conn, cfg, device_ids)
        try:
            for line in alerts.evaluate(conn, cfg):
                print(line)
        except Exception as e:  # alerting must never stop data collection
            print(f"alert evaluation failed: {e}", file=sys.stderr)
        if args.once:
            break
        stop.wait(cfg["interval_seconds"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
