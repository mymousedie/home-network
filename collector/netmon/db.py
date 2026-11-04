"""SQLite storage for the network monitor.

One file, no server. WAL mode lets the collector write while the future
dashboard API reads.
"""
import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    ip      TEXT NOT NULL,
    vlan    INTEGER
);

CREATE TABLE IF NOT EXISTS device_checks (
    id        INTEGER PRIMARY KEY,
    ts        REAL NOT NULL,          -- unix seconds
    device_id INTEGER NOT NULL REFERENCES devices(id),
    up        INTEGER NOT NULL,       -- 1 = replied, 0 = no reply
    rtt_ms    REAL                    -- NULL when down
);
CREATE INDEX IF NOT EXISTS idx_device_checks_dev_ts ON device_checks(device_id, ts);

CREATE TABLE IF NOT EXISTS internet_checks (
    id        INTEGER PRIMARY KEY,
    ts        REAL NOT NULL,
    target    TEXT NOT NULL,          -- e.g. 8.8.8.8
    up        INTEGER NOT NULL,
    rtt_ms    REAL,
    dns_ms    REAL                    -- NULL when the DNS lookup failed or wasn't run
);
CREATE INDEX IF NOT EXISTS idx_internet_checks_ts ON internet_checks(ts);

CREATE TABLE IF NOT EXISTS fw_events (
    id        INTEGER PRIMARY KEY,
    ts        REAL NOT NULL,
    iface     TEXT,
    action    TEXT,                   -- pass / block
    direction TEXT,                   -- in / out
    proto     TEXT,
    src       TEXT,
    dst       TEXT,
    src_port  INTEGER,
    dst_port  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_fw_events_ts ON fw_events(ts);

-- One row per critical incident. Opened and resolved by netmon.alerts.
-- notified_*: 0 = pending, 1 = sent, 2 = skipped (no webhook configured)
CREATE TABLE IF NOT EXISTS alerts (
    id                INTEGER PRIMARY KEY,
    key               TEXT NOT NULL,      -- e.g. device:IoT gateway, internet, dns
    severity          TEXT NOT NULL,      -- critical
    title             TEXT NOT NULL,
    detail            TEXT,
    opened_ts         REAL NOT NULL,
    resolved_ts       REAL,               -- NULL while still open
    notified_open     INTEGER NOT NULL DEFAULT 0,
    notified_resolved INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(resolved_ts, key);
"""


def connect(path):
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def upsert_device(conn, name, ip, vlan):
    with transaction(conn):
        conn.execute(
            "INSERT INTO devices(name, ip, vlan) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET ip=excluded.ip, vlan=excluded.vlan",
            (name, ip, vlan),
        )
    return conn.execute("SELECT id FROM devices WHERE name=?", (name,)).fetchone()["id"]


def record_device_check(conn, device_id, up, rtt_ms, ts=None):
    with transaction(conn):
        conn.execute(
            "INSERT INTO device_checks(ts, device_id, up, rtt_ms) VALUES (?, ?, ?, ?)",
            (ts or time.time(), device_id, 1 if up else 0, rtt_ms),
        )


def record_internet_check(conn, target, up, rtt_ms, dns_ms, ts=None):
    with transaction(conn):
        conn.execute(
            "INSERT INTO internet_checks(ts, target, up, rtt_ms, dns_ms) VALUES (?, ?, ?, ?, ?)",
            (ts or time.time(), target, 1 if up else 0, rtt_ms, dns_ms),
        )


def record_fw_event(conn, ev, ts=None):
    with transaction(conn):
        conn.execute(
            "INSERT INTO fw_events(ts, iface, action, direction, proto, src, dst, src_port, dst_port) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts or time.time(),
                ev.get("iface"),
                ev.get("action"),
                ev.get("direction"),
                ev.get("proto"),
                ev.get("src"),
                ev.get("dst"),
                ev.get("src_port"),
                ev.get("dst_port"),
            ),
        )
