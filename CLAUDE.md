# WUMS — Webcomic Update Monitoring System

## What This Is

A single-file Discord bot (`monitor.py`) that monitors webcomics for updates and pings subscribed users. Supports two detection methods: HTML hash comparison (page content changes) and RSS feed GUID tracking.

## Working in This Codebase

### Rebuild & Restart After Changes

```bash
cd /home/docker/wums
docker compose up -d --build
docker logs wums -f
```

Data in `./data/` is mounted at `/app/data` and is never affected by rebuilds.

### Local Dev Without Docker

```bash
pip install requests discord.py feedparser
python monitor.py
```

Falls back to `./data` automatically if `/app/data` doesn't exist.

## Architecture

Everything lives in `monitor.py`. There are no other source files. Data is stored in two JSON files:

| File | Contents |
|------|----------|
| `/app/data/comics.json` | Comic definitions (id, name, url, type, color, enabled, show_caption) |
| `/app/data/subscriptions.json` | User subscriptions `{user_id: [comic_id, ...]}` |

State between monitor loop iterations is stored as **attributes on the `monitor_comics` task function itself** (e.g. `monitor_comics.sabrina_previous_hash`). This is in-memory only — state resets on restart, so the first check after a restart always establishes a new baseline rather than firing a false notification.

## Comic Types

**`html`** — fetches the page, SHA-256 hashes the full HTML, fires on any change. Prone to false positives from ads/dynamic content. Notification says "maybe" an update.

**`rss`** — tracks the `guid` of the latest feed entry, fires when it changes. More reliable. Supports optional caption extraction from entry content/description.

## Key Conventions

### Comic IDs Are the Primary Key

The `comic_id` string (e.g. `"sabrina"`, `"twokinds"`) is how everything is keyed — in `comics.json`, `subscriptions.json`, and all slash command parameters. Keep them lowercase, no spaces.

### Colors Are Stored as `0xRRGGBB` Strings

`parse_color()` normalizes all input formats (`#RRGGBB`, `RRGGBB`, named presets) to `"0xRRGGBB"`. Stored as strings in JSON and cast with `int(comic['color'], 16)` when building embeds. Don't change this pattern.

### Admin Check Pattern

All admin commands follow this exact pattern — don't skip it:

```python
if not is_admin(interaction.user.id):
    await interaction.response.send_message("❌ ...", ephemeral=True)
    return
```

Admin user IDs come from `ADMIN_USER_IDS` env var (comma-separated).

### Adding a New Slash Command

User-facing commands go after the `# User slash commands` comment. Admin commands go after `# Admin slash commands`. No guild isolation needed — this bot is single-channel.

## What to Watch Out For

- **`monitor_started` flag** — prevents the monitor loop from starting twice on Discord reconnects. Don't remove it.
- **HTML monitoring is noisy** — sites with ads, counters, or dynamic content will change hash constantly. Prefer RSS when available.
- **`SEND_TEST_NOTIFICATION` and `SEND_STARTUP_RSS_NOTIFICATIONS`** — both default to `false` in production (`docker-compose.yml`). Leave them off unless actively testing; `SEND_STARTUP_RSS_NOTIFICATIONS=true` will spam every subscriber on restart.
- **`show_caption` only applies to RSS comics** — `togglecaption` enforces this, but keep it in mind when reading comic config.
- **No persistence of monitor state** — restarting the container resets all hash/GUID baselines. The first check after restart is always a no-op (establishes baseline), so no false notifications fire on restart.

## Environment Variables

```
DISCORD_BOT_TOKEN          Bot token
DISCORD_CHANNEL_ID         Channel for all notifications
ADMIN_USER_IDS             Comma-separated Discord user IDs with admin access
CHECK_INTERVAL             Seconds between checks (default: 7200)
SEND_TEST_NOTIFICATION     Send startup embed (default: false)
SEND_STARTUP_RSS_NOTIFICATIONS  Notify all subscribers of current RSS entries on startup (default: false)
```

## Command Reference

**User:**
- `/subscribe` — pick comics to subscribe to (dropdown, ephemeral)
- `/unsubscribe` — pick comics to unsubscribe from (dropdown, ephemeral)
- `/subscriptions` — list your current subscriptions

**Admin:**
- `/addcomic` — add a comic (id, name, url, type, color)
- `/removecomic` — remove a comic and clean up its subscriptions
- `/togglecomic` — enable/disable a comic without removing it
- `/togglecaption` — show/hide RSS entry captions in notifications
- `/listcomics` — view all comics and their status
- `/inspectcomic` — preview what a notification would look like (useful when adding new comics)
