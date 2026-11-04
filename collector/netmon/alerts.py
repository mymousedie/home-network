"""Critical-condition alerts with Discord notifications.

Run once per collection cycle (the runner does this). Each critical
condition gets one alert row while it lasts, so Discord gets one message
when it starts and one when it clears, not one per check.

Notifications that fail to send stay pending and are retried next cycle.
That matters for "internet down": Discord is unreachable until the link
comes back, at which point a single "was down from X to Y" message goes out.
"""
import time
from datetime import datetime

from . import db, notify, status


def critical_conditions(conn, cfg, now=None):
    """Return {key: (title, detail)} for everything that is critical right now."""
    out = {}
    for d in status.device_statuses(conn, cfg, now):
        if d["status"] == "offline" and d["alerts_enabled"]:
            vlan = f" on VLAN {d['vlan']}" if d["vlan"] is not None else ""
            out[f"device:{d['name']}"] = (
                f"{d['name']} is offline",
                f"{d['name']} ({d['ip']}){vlan}: {d['reason']}.",
            )
    inet = status.internet_status(conn, cfg, now)
    if inet["all_targets_down"]:
        targets = ", ".join(t["target"] for t in inet["targets"])
        out["internet"] = ("Internet is down", f"No reply from any ping target ({targets}).")
    if inet["dns_failing"]:
        out["dns"] = ("DNS is failing", f"Resolver {inet['dns']['server']} is not answering lookups.")
    return out


def evaluate(conn, cfg, now=None, send=notify.send_discord):
    """Open/resolve alerts, then flush pending notifications.
    Returns a list of human-readable change lines for the runner to print."""
    now = now or time.time()
    conditions = critical_conditions(conn, cfg, now)
    open_rows = {
        r["key"]: r for r in conn.execute("SELECT * FROM alerts WHERE resolved_ts IS NULL")
    }
    changes = []
    with db.transaction(conn):
        for key, (title, detail) in conditions.items():
            if key not in open_rows:
                conn.execute(
                    "INSERT INTO alerts(key, severity, title, detail, opened_ts) "
                    "VALUES (?, 'critical', ?, ?, ?)",
                    (key, title, detail, now),
                )
                changes.append(f"ALERT  {title}")
        for key, row in open_rows.items():
            if key not in conditions:
                conn.execute("UPDATE alerts SET resolved_ts=? WHERE id=?", (now, row["id"]))
                changes.append(f"CLEAR  {row['title']}")
    flush_notifications(conn, cfg, send)
    return changes


def _fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_duration(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else (f"{m}m {s}s" if m else f"{s}s")


def flush_notifications(conn, cfg, send=notify.send_discord):
    settings = status.alert_settings(cfg)
    url = notify.webhook_url(settings)
    pending = conn.execute(
        "SELECT * FROM alerts WHERE notified_open=0 "
        "OR (resolved_ts IS NOT NULL AND notified_resolved=0) ORDER BY id"
    ).fetchall()
    if not pending:
        return
    if not url:
        with db.transaction(conn):
            conn.execute("UPDATE alerts SET notified_open=2 WHERE notified_open=0")
            conn.execute(
                "UPDATE alerts SET notified_resolved=2 "
                "WHERE resolved_ts IS NOT NULL AND notified_resolved=0"
            )
        return

    mention = settings.get("discord_mention", "")
    for a in pending:
        resolved = a["resolved_ts"] is not None
        if resolved and not settings["notify_recovery"] and a["notified_open"] != 0:
            _mark(conn, a["id"], resolved=2)
            continue
        if resolved and a["notified_open"] == 0:
            # Never got the "down" message out (often because the internet
            # itself was down), so send one combined message instead.
            ok, _ = send(
                url,
                f"🟢 Recovered: {a['title']}",
                f"{a['detail']}\nDown for {_fmt_duration(a['resolved_ts'] - a['opened_ts'])}.",
                color=notify.GREEN,
                fields=[("Started", _fmt_ts(a["opened_ts"])), ("Ended", _fmt_ts(a["resolved_ts"]))],
            )
            if not ok:
                return
            _mark(conn, a["id"], opened=1, resolved=1)
        elif a["notified_open"] == 0:
            ok, _ = send(
                url,
                f"🔴 {a['title']}",
                a["detail"],
                color=notify.RED,
                mention=mention,
                fields=[("Since", _fmt_ts(a["opened_ts"])), ("Severity", a["severity"])],
            )
            if not ok:
                return  # likely no internet; retry everything next cycle
            _mark(conn, a["id"], opened=1)
        else:
            ok, _ = send(
                url,
                f"🟢 Resolved: {a['title']}",
                f"Back to normal after {_fmt_duration(a['resolved_ts'] - a['opened_ts'])}.",
                color=notify.GREEN,
            )
            if not ok:
                return
            _mark(conn, a["id"], resolved=1)


def _mark(conn, alert_id, opened=None, resolved=None):
    with db.transaction(conn):
        if opened is not None:
            conn.execute("UPDATE alerts SET notified_open=? WHERE id=?", (opened, alert_id))
        if resolved is not None:
            conn.execute("UPDATE alerts SET notified_resolved=? WHERE id=?", (resolved, alert_id))
