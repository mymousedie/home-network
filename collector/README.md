# netmon — home-lab network collector (Phase 3)

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

19 tests cover ping output parsing (Windows and Linux), filterlog parsing,
DNS timing against a fake server, SQLite storage and report math, a UDP-to-DB
syslog integration test, and a full collection cycle.

## Layout

```
netmon/db.py              schema + write helpers (SQLite, WAL)
netmon/checks.py          ping + DNS timing
netmon/syslog_listener.py filterlog parser + UDP listener thread
netmon/runner.py          collection loop (entry point)
netmon/report.py          summary queries (reused by the Phase 4 API)
```
