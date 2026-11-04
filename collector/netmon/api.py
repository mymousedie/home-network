"""JSON API over the collector's SQLite database, plus the built React
dashboard. Needs FastAPI (pip install -r requirements-api.txt); the
collector itself stays stdlib-only.

    python -m netmon.api --config config.json --port 8000

Endpoints (`hours` = look-back window):
    GET  /api/health
    GET  /api/overview?hours=1           internet, VLANs + devices, switch ports, alerts
    GET  /api/timeseries/internet?hours=6
    GET  /api/timeseries/devices?hours=6
    GET  /api/timeseries/firewall?hours=6   pass/block per bucket
    GET  /api/firewall/events?hours=24&vlan=&action=&q=&limit=&offset=
    GET  /api/firewall/top?hours=24&action=block&by=src
    GET  /api/alerts?state=all&limit=100
    POST /api/notifications/test         send a test Discord message

Only the collector writes measurements and alerts; the API reads them.
"""
import argparse
import os
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, notify, runner, status

MAX_HOURS = 24 * 30
TARGET_POINTS = 60  # roughly how many buckets a chart gets


def _bucket_seconds(hours):
    return max(30, int(hours * 3600 / TARGET_POINTS))


def _rows(cursor):
    return [dict(r) for r in cursor.fetchall()]


def _port_status(device, internet):
    """What a switch port tile shows: the device's own state, plus whether
    the network can reach the internet right now."""
    if device is None:
        return "unmonitored", "no device mapped to this port"
    if device["status"] == "offline":
        return "disconnected", device["reason"]
    if device["status"] == "unknown":
        return "unknown", device["reason"]
    if internet["status"] == "down":
        return "no_internet", f"device reachable, but {internet['reason']}"
    if device["status"] == "degraded":
        return "degraded", device["reason"]
    return "ok", "connected"


def create_app(cfg, dist_dir=None):
    app = FastAPI(title="Home network monitor", version="1.0")
    db_path = cfg["db_path"]
    vlans_cfg = cfg.get("vlans", [])
    wan_iface = cfg.get("wan_iface")
    iface_to_vlan = {v["iface"]: v for v in vlans_cfg if v.get("iface")}

    def iface_label(iface):
        if iface == wan_iface:
            return "WAN"
        v = iface_to_vlan.get(iface)
        return v["name"] if v else iface

    def get_conn():
        conn = db.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    Hours = Query(1.0, gt=0, le=MAX_HOURS, description="look-back window in hours")

    @app.get("/api/health")
    def health(conn=Depends(get_conn)):
        last = conn.execute(
            "SELECT MAX(ts) AS t FROM (SELECT ts FROM device_checks UNION ALL "
            "SELECT ts FROM internet_checks)"
        ).fetchone()["t"]
        age = None if last is None else round(time.time() - last, 1)
        return {
            "ok": True,
            "last_check_ts": last,
            "last_check_age_s": age,
            "collector_stale": age is None or age > status.stale_after_s(cfg),
            "interval_s": cfg.get("interval_seconds", 30),
        }

    @app.get("/api/overview")
    def overview(hours: float = Hours, conn=Depends(get_conn)):
        now = time.time()
        since = now - hours * 3600
        devices = status.device_statuses(conn, cfg, now)
        internet = status.internet_status(conn, cfg, now)
        by_name = {d["name"]: d for d in devices}

        fw_counts = {}
        for r in conn.execute(
            "SELECT iface, action, COUNT(*) AS n FROM fw_events WHERE ts >= ? GROUP BY 1, 2",
            (since,),
        ):
            fw_counts.setdefault(r["iface"], {"pass": 0, "block": 0})[r["action"]] = r["n"]

        known_vlans = {v["id"] for v in vlans_cfg}
        vlans = []
        for v in vlans_cfg + [
            {"id": vid, "name": f"VLAN {vid}", "subnet": None, "iface": None}
            for vid in sorted({d["vlan"] for d in devices if d["vlan"] not in known_vlans},
                              key=lambda x: (x is None, x))
        ]:
            members = [d for d in devices if d["vlan"] == v["id"]]
            states = {d["status"] for d in members}
            vstatus = (
                "offline" if "offline" in states
                else "degraded" if "degraded" in states
                else "unknown" if not members or states == {"unknown"}
                else "online"
            )
            vlans.append({
                **v,
                "status": vstatus,
                "devices": members,
                "firewall": fw_counts.get(v.get("iface"), {"pass": 0, "block": 0}),
            })

        ports = []
        for p in cfg.get("switch", {}).get("ports", []):
            dev = by_name.get(p.get("device")) if p.get("device") else None
            pstatus, reason = _port_status(dev, internet)
            ports.append({**p, "status": pstatus, "reason": reason, "device_info": dev})

        totals = {"pass": 0, "block": 0}
        for c in fw_counts.values():
            totals["pass"] += c.get("pass", 0)
            totals["block"] += c.get("block", 0)

        counts = {k: 0 for k in ("online", "degraded", "offline", "unknown")}
        for d in devices:
            counts[d["status"]] += 1

        settings = status.alert_settings(cfg)
        return {
            "generated_ts": now,
            "hours": hours,
            "internet": internet,
            "devices": devices,
            "device_counts": {**counts, "total": len(devices)},
            "vlans": vlans,
            "switch": {"name": cfg.get("switch", {}).get("name"), "ports": ports},
            "firewall": {**totals, "wan": fw_counts.get(wan_iface, {"pass": 0, "block": 0})},
            "open_alerts": _rows(conn.execute(
                "SELECT * FROM alerts WHERE resolved_ts IS NULL ORDER BY opened_ts DESC"
            )),
            "notifications": {
                "discord_configured": bool(notify.webhook_url(settings)),
                "mention": settings.get("discord_mention") or None,
                "down_after_failures": settings["down_after_failures"],
            },
        }

    @app.get("/api/timeseries/internet")
    def ts_internet(hours: float = Hours, conn=Depends(get_conn)):
        b = _bucket_seconds(hours)
        return {"bucket_s": b, "points": _rows(conn.execute(
            """
            SELECT CAST(ts / :b AS INTEGER) * :b AS ts, target,
                   100.0 * (1 - AVG(up)) AS loss_pct,
                   AVG(rtt_ms)           AS avg_rtt,
                   AVG(dns_ms)           AS avg_dns
            FROM internet_checks WHERE ts >= :since
            GROUP BY 1, target ORDER BY 1
            """,
            {"b": b, "since": time.time() - hours * 3600},
        ))}

    @app.get("/api/timeseries/devices")
    def ts_devices(hours: float = Hours, conn=Depends(get_conn)):
        b = _bucket_seconds(hours)
        return {"bucket_s": b, "points": _rows(conn.execute(
            """
            SELECT CAST(c.ts / :b AS INTEGER) * :b AS ts, d.name AS device,
                   100.0 * AVG(c.up) AS uptime_pct,
                   AVG(c.rtt_ms)     AS avg_rtt
            FROM device_checks c JOIN devices d ON d.id = c.device_id
            WHERE c.ts >= :since GROUP BY 1, d.id ORDER BY 1
            """,
            {"b": b, "since": time.time() - hours * 3600},
        ))}

    @app.get("/api/timeseries/firewall")
    def ts_firewall(hours: float = Hours, vlan: int | None = None, conn=Depends(get_conn)):
        b = _bucket_seconds(hours)
        where, params = _fw_filter(hours, vlan, None, None)
        params["b"] = b
        return {"bucket_s": b, "points": _rows(conn.execute(
            f"""
            SELECT CAST(ts / :b AS INTEGER) * :b AS ts,
                   SUM(action = 'pass')  AS pass,
                   SUM(action = 'block') AS block
            FROM fw_events WHERE {where} GROUP BY 1 ORDER BY 1
            """,
            params,
        ))}

    def _fw_filter(hours, vlan, action, q):
        clauses = ["ts >= :since"]
        params = {"since": time.time() - hours * 3600}
        if vlan is not None:
            if vlan == 0:  # 0 = WAN, which has no VLAN id
                iface = wan_iface
            else:
                v = next((v for v in vlans_cfg if v["id"] == vlan), None)
                if v is None or not v.get("iface"):
                    raise HTTPException(404, f"VLAN {vlan} has no firewall interface")
                iface = v["iface"]
            clauses.append("iface = :iface")
            params["iface"] = iface
        if action:
            clauses.append("action = :action")
            params["action"] = action
        if q:
            clauses.append(
                "(src LIKE :q OR dst LIKE :q OR proto LIKE :q "
                "OR CAST(dst_port AS TEXT) = :qexact OR CAST(src_port AS TEXT) = :qexact)"
            )
            params["q"] = f"%{q}%"
            params["qexact"] = q
        return " AND ".join(clauses), params

    @app.get("/api/firewall/events")
    def fw_events(
        hours: float = Query(24, gt=0, le=MAX_HOURS),
        vlan: int | None = Query(None, description="VLAN id, or 0 for WAN"),
        action: str | None = Query(None, pattern="^(pass|block)$"),
        q: str | None = Query(None, max_length=64, description="IP, protocol or port"),
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        conn=Depends(get_conn),
    ):
        where, params = _fw_filter(hours, vlan, action, q)
        total = conn.execute(f"SELECT COUNT(*) FROM fw_events WHERE {where}", params).fetchone()[0]
        rows = _rows(conn.execute(
            f"SELECT * FROM fw_events WHERE {where} ORDER BY ts DESC, id DESC "
            "LIMIT :limit OFFSET :offset",
            {**params, "limit": limit, "offset": offset},
        ))
        for r in rows:
            r["iface_label"] = iface_label(r["iface"])
            v = iface_to_vlan.get(r["iface"])
            r["vlan"] = v["id"] if v else None
        return {"total": total, "limit": limit, "offset": offset, "rows": rows}

    @app.get("/api/firewall/top")
    def fw_top(
        hours: float = Query(24, gt=0, le=MAX_HOURS),
        action: str = Query("block", pattern="^(pass|block)$"),
        by: str = Query("src", pattern="^(src|dst)$"),
        vlan: int | None = None,
        limit: int = Query(10, ge=1, le=50),
        conn=Depends(get_conn),
    ):
        where, params = _fw_filter(hours, vlan, action, None)
        col = "src" if by == "src" else "dst"  # whitelisted above, safe to inline
        rows = _rows(conn.execute(
            f"""
            SELECT {col} AS addr, iface, COUNT(*) AS n,
                   COUNT(DISTINCT dst_port) AS ports, MAX(ts) AS last_ts
            FROM fw_events WHERE {where}
            GROUP BY {col}, iface ORDER BY n DESC LIMIT :limit
            """,
            {**params, "limit": limit},
        ))
        for r in rows:
            r["iface_label"] = iface_label(r["iface"])
        return {"rows": rows}

    @app.get("/api/alerts")
    def alert_history(
        state: str = Query("all", pattern="^(all|open|resolved)$"),
        limit: int = Query(100, ge=1, le=500),
        conn=Depends(get_conn),
    ):
        where = {"all": "1=1", "open": "resolved_ts IS NULL",
                 "resolved": "resolved_ts IS NOT NULL"}[state]
        return {"alerts": _rows(conn.execute(
            f"SELECT * FROM alerts WHERE {where} ORDER BY opened_ts DESC, id DESC LIMIT ?",
            (limit,),
        ))}

    @app.post("/api/notifications/test")
    def test_notification():
        settings = status.alert_settings(cfg)
        url = notify.webhook_url(settings)
        if not url:
            raise HTTPException(400, "No Discord webhook configured. Set NETMON_DISCORD_WEBHOOK "
                                     "in collector/.env and restart the API.")
        ok, err = notify.send_discord(
            url, "✅ netmon test message",
            "Discord alerts are working. You'll get a message here when a device "
            "goes offline or the internet drops.",
            color=notify.BLUE,
            mention=settings.get("discord_mention", ""),
        )
        if not ok:
            raise HTTPException(502, f"Discord rejected the message: {err}")
        return {"ok": True}

    # --- dashboard (built React app) -----------------------------------------
    dist = Path(dist_dir) if dist_dir else (
        Path(os.environ["NETMON_DASHBOARD"]) if os.environ.get("NETMON_DASHBOARD")
        else Path(__file__).resolve().parents[2] / "dashboard" / "dist"
    )
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_dashboard():
            return {"message": "API is running. Dashboard not built yet: "
                               "cd dashboard && npm install && npm run build. "
                               "API docs at /docs."}

    return app


def main(argv=None):
    import uvicorn

    ap = argparse.ArgumentParser(description="Network monitor API + dashboard")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    uvicorn.run(create_app(runner.load_config(args.config)), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
