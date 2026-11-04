"""Discord webhook notifications. Standard library only.

The webhook URL is a secret (anyone holding it can post to your channel), so
keep it out of config.json, which is committed. Put it in collector/.env:

    NETMON_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...

`alerts.discord_webhook_url` in the config also works if you'd rather.
"""
import json
import os
import urllib.error
import urllib.request

RED = 0xE5484D
GREEN = 0x30A46C
BLUE = 0x3E63DD


def load_env_file(path):
    """Minimal KEY=VALUE loader. Existing environment variables win."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def webhook_url(settings):
    return os.environ.get("NETMON_DISCORD_WEBHOOK") or settings.get("discord_webhook_url") or ""


def send_discord(url, title, description, color=RED, mention="", fields=None, timeout=5):
    """Post one embed. Returns (ok, error_message)."""
    body = {
        "username": "netmon",
        "content": mention or None,
        "allowed_mentions": {"parse": ["everyone", "users", "roles"]},
        "embeds": [{
            "title": title,
            "description": description,
            "color": color,
            "fields": [{"name": k, "value": str(v), "inline": True} for k, v in (fields or [])],
        }],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        # Discord's edge rejects the default Python-urllib user agent.
        headers={"Content-Type": "application/json", "User-Agent": "netmon/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300, None
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read(200).decode(errors='replace')}"
    except (urllib.error.URLError, OSError) as e:
        return False, str(getattr(e, "reason", e))
