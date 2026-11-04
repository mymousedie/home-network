"""Turn raw check rows into a current status for each device and for the
internet link. Shared by the alert engine (collector) and the API, so the
dashboard and Discord always agree on what "down" means.

Device / internet status values:
    online    replying normally
    degraded  replying, but with recent loss, high latency, or a single miss
    offline   (devices) no reply for `down_after_failures` checks in a row
    down      (internet) every ping target, or DNS, failing that many checks
    unknown   no checks yet, or the collector has stopped writing
"""
import time

DEFAULT_ALERTS = {
    "down_after_failures": 3,   # consecutive misses before it's critical
    "recent_checks": 10,        # window for loss% / avg RTT
    "rtt_warn_ms": 150,
    "loss_warn_pct": 20,
    "notify_recovery": True,
    "discord_webhook_url": "",  # prefer NETMON_DISCORD_WEBHOOK in collector/.env
    "discord_mention": "",      # e.g. "@here" or "<@your-user-id>" to get a phone push
}


def alert_settings(cfg):
    s = dict(DEFAULT_ALERTS)
    s.update(cfg.get("alerts") or {})
    return s


def stale_after_s(cfg):
    # Three missed collection cycles means the collector isn't running.
    return max(3 * cfg.get("interval_seconds", 30), 90)


def _consecutive_failures(recent):
    n = 0
    for up, _rtt in recent:
        if up:
            break
        n += 1
    return n


def _window_stats(recent):
    if not recent:
        return None, None
    loss = 100.0 * sum(1 for up, _ in recent if not up) / len(recent)
    rtts = [rtt for up, rtt in recent if up and rtt is not None]
    return loss, (sum(rtts) / len(rtts) if rtts else None)


def classify(recent, settings):
    """recent: newest-first list of (up, rtt_ms). Returns (status, reason)."""
    if not recent:
        return "unknown", "no checks yet"
    fails = _consecutive_failures(recent)
    loss, avg_rtt = _window_stats(recent)
    if fails >= settings["down_after_failures"]:
        return "offline", f"no reply for {fails} checks in a row"
    if fails:
        return "degraded", f"missed the last {fails} check(s)"
    if loss >= settings["loss_warn_pct"]:
        return "degraded", f"{loss:.0f}% packet loss over the last {len(recent)} checks"
    if avg_rtt is not None and avg_rtt > settings["rtt_warn_ms"]:
        return "degraded", f"high latency ({avg_rtt:.0f} ms avg)"
    return "online", "replying normally"


def device_statuses(conn, cfg, now=None):
    now = now or time.time()
    s = alert_settings(cfg)
    stale = stale_after_s(cfg)
    alert_off = {d["name"] for d in cfg.get("devices", []) if d.get("alert") is False}
    out = []
    for d in conn.execute("SELECT id, name, ip, vlan FROM devices ORDER BY vlan, name"):
        rows = conn.execute(
            "SELECT ts, up, rtt_ms FROM device_checks WHERE device_id=? "
            "ORDER BY ts DESC, id DESC LIMIT ?",
            (d["id"], s["recent_checks"]),
        ).fetchall()
        recent = [(bool(r["up"]), r["rtt_ms"]) for r in rows]
        status, reason = classify(recent, s)
        last_ts = rows[0]["ts"] if rows else None
        if last_ts is not None and now - last_ts > stale:
            status, reason = "unknown", "no recent checks (is the collector running?)"
        last_seen = conn.execute(
            "SELECT MAX(ts) AS t FROM device_checks WHERE device_id=? AND up=1", (d["id"],)
        ).fetchone()["t"]
        loss, avg_rtt = _window_stats(recent)
        out.append({
            "id": d["id"],
            "name": d["name"],
            "ip": d["ip"],
            "vlan": d["vlan"],
            "status": status,
            "reason": reason,
            "consecutive_failures": _consecutive_failures(recent),
            "rtt_ms": recent[0][1] if recent else None,
            "avg_rtt_ms": avg_rtt,
            "loss_pct": loss,
            "last_check_ts": last_ts,
            "last_seen_ts": last_seen,
            "alerts_enabled": d["name"] not in alert_off,
        })
    return out


def internet_status(conn, cfg, now=None):
    now = now or time.time()
    s = alert_settings(cfg)
    inet = cfg.get("internet", {})
    targets = inet.get("ping_targets", [])
    n = s["recent_checks"]

    per_target = []
    all_down = bool(targets)
    any_degraded = False
    last_ts = None
    for t in targets:
        rows = conn.execute(
            "SELECT ts, up, rtt_ms FROM internet_checks WHERE target=? "
            "ORDER BY ts DESC, id DESC LIMIT ?",
            (t, n),
        ).fetchall()
        recent = [(bool(r["up"]), r["rtt_ms"]) for r in rows]
        st, reason = classify(recent, s)
        loss, avg = _window_stats(recent)
        if rows:
            last_ts = max(last_ts or 0, rows[0]["ts"])
        all_down = all_down and st == "offline"
        any_degraded = any_degraded or st in ("degraded", "offline")
        per_target.append({
            "target": t,
            "status": st,
            "reason": reason,
            "up_now": recent[0][0] if recent else None,
            "rtt_ms": recent[0][1] if recent else None,
            "avg_rtt_ms": avg,
            "loss_pct": loss,
        })

    # DNS timing is stored on the first target's row each cycle (see runner).
    dns = None
    dns_failing = False
    if targets and inet.get("dns_server") and inet.get("dns_name"):
        rows = conn.execute(
            "SELECT dns_ms FROM internet_checks WHERE target=? ORDER BY ts DESC, id DESC LIMIT ?",
            (targets[0], n),
        ).fetchall()
        fails = 0
        for r in rows:
            if r["dns_ms"] is not None:
                break
            fails += 1
        ok = [r["dns_ms"] for r in rows if r["dns_ms"] is not None]
        dns_failing = fails >= s["down_after_failures"]
        any_degraded = any_degraded or fails > 0
        dns = {
            "server": inet["dns_server"],
            "name": inet["dns_name"],
            "ms": rows[0]["dns_ms"] if rows else None,
            "avg_ms": sum(ok) / len(ok) if ok else None,
            "consecutive_failures": fails,
        }

    if last_ts is None:
        status, reason = "unknown", "no internet checks yet"
    elif now - last_ts > stale_after_s(cfg):
        status, reason = "unknown", "no recent checks (is the collector running?)"
    elif all_down:
        status, reason = "down", "all ping targets unreachable"
    elif dns_failing:
        status, reason = "down", f"DNS resolver {inet['dns_server']} not answering"
    elif any_degraded:
        status, reason = "degraded", "some loss, latency, or DNS misses"
    else:
        status, reason = "online", "all targets replying"

    return {
        "status": status,
        "reason": reason,
        "all_targets_down": all_down,
        "dns_failing": dns_failing,
        "targets": per_target,
        "dns": dns,
        "last_check_ts": last_ts,
    }
