# 🔥 MenuPapi CM

**Real Claude.ai usage monitor with accurate 5-hour + weekly reset countdown.**

Track your Claude Code token usage with a live terminal dashboard. Get real-time session reset timers — no more guessing when your limit refreshes.

## Install

```bash
pip install menupapi-cm
```

## Quick Start

```bash
# Launch the monitor (works immediately in estimate mode)
cm

# Enable real Claude.ai API data (recommended)
cm setup

# Check cookie health
cm doctor

# Show help
cm help
```

## What You Get

```
✦ ✧ MENUPAPI CLAUDE MONITOR ✦ ✧
💰 Tokens Used: ████████░░░░░░░░  12,450 / 19,000
🕒 Last 47 messages          📌 Current session  34% used
🧮 Tokens Remaining: 6,550   📨 Messages: 47
🧠 Tokens Spent: 12,450      ⏱ Resets in 2h 41m  34% used
                              📅 Weekly resets in 3d 3h  24% used
```

## Setup (Real API Mode)

By default, `cm` estimates reset times from local logs. To get **exact** reset countdown from Claude.ai:

```bash
cm setup
```

This will prompt you to paste your Claude.ai cookie header. Here's how to get it:

1. Open **https://claude.ai/settings/usage** in Chrome
2. Open **DevTools** (`Cmd+Option+I`) → **Network** tab
3. Click **"Refresh usage limits"** on the page
4. In Network tab, click the request to `/api/organizations/.../usage`
5. Go to **Headers** → **Request Headers** → copy the `cookie` value
6. Paste it when `cm setup` prompts you

### ⚠️ Cookie Expiration

The `cf_clearance` token (Cloudflare) expires periodically. When it does, `cm` falls back to estimate mode automatically. Just re-run `cm setup` to refresh.

### �� Cookie Security

- Your cookie is stored locally at `~/.claude_cookie.txt`
- File permissions are set to `600` (owner-only read/write)
- **Never paste your cookie into GitHub issues or public channels**
- The cookie is only sent to `claude.ai` API endpoints

## Monitor Controls

| Key | Action |
|-----|--------|
| `1` | Show last 3 sessions |
| `2` | Show last 5 sessions |
| `3` | Show last 10 sessions |
| `T` | Toggle inline terminal |
| `Q` | Quit |

## Commands

| Command | Description |
|---------|-------------|
| `cm` | Launch live usage monitor |
| `cm setup` | Install Claude.ai cookie for real API data |
| `cm doctor` | Check cookie health + API connectivity |
| `cm help` | Show help |
| `cm version` | Show version |

## Requirements

- Python 3.9+
- macOS or Linux
- Claude Code (for local usage data)

## License

MIT — by [Sylvester Assiamah](https://github.com/AssiamahS)
