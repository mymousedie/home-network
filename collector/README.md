# netmon — home-lab network collector, API and alerts (Phases 3-4)

Stdlib-only Python collector (no `pip install` needed, Python 3.9+) that runs on
the Windows host and stores network health data in SQLite.

| Signal | How | Table |
|---|---|---|
| Device up/down + RTT | ICMP ping each device every interval | `device_checks` |
| Internet health | Ping targets (loss, RTT) + timed DNS lookup against the OPNsense resolver | `internet_checks` |
| Firewall activity | OPNsense remote syslog (UDP) → parsed `filterlog` lines | `fw_events` |

## Run

```powershell
cd collector
copy config.example.json config.json    # edit devices / IPs as needed
python -m netmon.runner --config config.json          # runs until Ctrl+C
python -m netmon.runner --config config.json --once   # one cycle, then exit
python -m netmon.report --db netmon.db --hours 24     # text summary
```

## Receiving firewall logs from OPNsense

1. **System → Settings → Logging → Remote** → add a destination:
   transport UDP, host = the Windows host's Trusted-VLAN IP (e.g. `10.10.10.100`),
   port `5514`, applications `filter`.
2. Allow inbound UDP 5514 in Windows Defender Firewall for Python.
3. Tick **Log** on each firewall rule you want counted. Rules without it
   produce no `filterlog` lines, so an empty table is not proof of no traffic.

Both RFC 3164 and RFC 5424 syslog formats are handled. IPv6 entries are skipped for now.

## Tests

```
python -m unittest tests.test_netmon -v
```

33 tests cover ping output parsing (Windows and Linux), filterlog parsing,
DNS timing against a fake server, SQLite storage and report math, a UDP-to-DB
syslog integration test, a full collection cycle, status classification, the
alert engine (open/clear/retry while offline), and the API. The API tests are
skipped if FastAPI isn't installed.

## Phase 4: dashboard, API, and Discord alerts

```powershell
cd collector
pip install -r requirements-api.txt
copy env.example .env            # paste your Discord webhook URL into .env
python -m netmon.runner --config config.json   # terminal 1: collector + alerts
python -m netmon.api --config config.json      # terminal 2: http://127.0.0.1:8000
```

The API serves the built dashboard from `../dashboard/dist`
(`cd dashboard && npm install && npm run build`). For live UI development, run
`npm run dev` in `dashboard/` instead; Vite proxies `/api` to port 8000.

**Statuses.** A device that misses one or two pings is *degraded*. After
`alerts.down_after_failures` misses in a row (default 3, so about 90 s) it is
*offline*. The internet is *down* when every ping target fails that many times
in a row, or when the DNS resolver stops answering. Switch port tiles combine the
two: *disconnected*, *no internet*, *degraded*, or *OK*. Map a port to a
device with `switch.ports[].device` in `config.json`. Ports with no mapped
device show *not monitored*. To watch the test laptops on ports 3-5, give
them DHCP reservations and add them to `devices`.

**Discord alerts.** Create a webhook (channel settings → Integrations →
Webhooks) and put it in `collector/.env` as `NETMON_DISCORD_WEBHOOK`. Keep it
out of `config.json`, which is committed. Each critical condition sends one
message when it starts and one when it clears. `discord_mention` (e.g.
`@here`) makes Discord push it to your phone. Set `"alert": false` on a
device to keep it on the dashboard without alerting. A message that can't be
sent (Discord is unreachable while the internet is down) is retried every
cycle, and goes out as a single "was down from X to Y" message once the link
is back. Use **Alerts → Send test message** in the dashboard to check the
webhook.

## Layout

```
netmon/db.py              schema + write helpers (SQLite, WAL)
netmon/checks.py          ping + DNS timing
netmon/syslog_listener.py filterlog parser + UDP listener thread
netmon/runner.py          collection loop (entry point)
netmon/report.py          summary queries (text report)
netmon/status.py          online/degraded/offline classification (shared)
netmon/alerts.py          critical alert engine, run each cycle by the runner
netmon/notify.py          Discord webhook sender + .env loader
netmon/api.py             FastAPI JSON API + serves dashboard/dist
```
