"""Print a text summary of what the collector has stored.

    python -m netmon.report --db netmon.db --hours 24

This is the same set of queries the React dashboard's API will serve in
Phase 4, so it doubles as a check that the data is useful.
"""
import argparse
import time

from . import db


def device_summary(conn, since):
    return conn.execute(
        """
        SELECT d.name, d.ip, d.vlan,
               COUNT(c.id)                       AS checks,
               100.0 * AVG(c.up)                 AS uptime_pct,
               AVG(c.rtt_ms)                     AS avg_rtt
        FROM devices d LEFT JOIN device_checks c
             ON c.device_id = d.id AND c.ts >= ?
        GROUP BY d.id ORDER BY d.vlan, d.name
        """,
        (since,),
    ).fetchall()


def internet_summary(conn, since):
    return conn.execute(
        """
        SELECT target,
               COUNT(*)                          AS checks,
               100.0 * (1 - AVG(up))             AS loss_pct,
               AVG(rtt_ms)                       AS avg_rtt,
               MAX(rtt_ms)                       AS max_rtt,
               AVG(dns_ms)                       AS avg_dns
        FROM internet_checks WHERE ts >= ? GROUP BY target
        """,
        (since,),
    ).fetchall()


def firewall_summary(conn, since):
    return conn.execute(
        """
        SELECT iface, action, COUNT(*) AS n
        FROM fw_events WHERE ts >= ? GROUP BY iface, action ORDER BY iface, action
        """,
        (since,),
    ).fetchall()


def fmt(v, spec="{:.1f}", none="-"):
    return none if v is None else spec.format(v)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="netmon.db")
    ap.add_argument("--hours", type=float, default=24)
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    since = time.time() - args.hours * 3600
    print(f"== Last {args.hours:g}h ==\n")

    print("Devices")
    print(f"  {'name':<20}{'ip':<16}{'vlan':<6}{'checks':<8}{'uptime%':<9}avg rtt ms")
    for r in device_summary(conn, since):
        print(f"  {r['name']:<20}{r['ip']:<16}{str(r['vlan']):<6}{r['checks']:<8}"
              f"{fmt(r['uptime_pct']):<9}{fmt(r['avg_rtt'])}")

    print("\nInternet health")
    print(f"  {'target':<14}{'checks':<8}{'loss%':<8}{'avg ms':<9}{'max ms':<9}avg dns ms")
    for r in internet_summary(conn, since):
        print(f"  {r['target']:<14}{r['checks']:<8}{fmt(r['loss_pct']):<8}"
              f"{fmt(r['avg_rtt']):<9}{fmt(r['max_rtt']):<9}{fmt(r['avg_dns'])}")

    print("\nFirewall events (logged rules only)")
    rows = firewall_summary(conn, since)
    if not rows:
        print("  none recorded")
    for r in rows:
        print(f"  {r['iface']:<10}{r['action']:<8}{r['n']}")


if __name__ == "__main__":
    main()
