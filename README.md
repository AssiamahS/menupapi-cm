# MENUPAPI-CM (cm)

A lightweight terminal monitor that shows your **Claude Code 5-hour reset timer** and utilization.

Unlike most monitors, this supports **REAL Claude web session reset data** by pulling:

```
https://claude.ai/api/organizations/{org_id}/usage
```

If cookies are missing, it runs instantly in **estimate mode**.

---

## Install

```bash
pip install menupapi-cm
```

## Run

```bash
cm
```

## Features

- Shows real `five_hour.utilization` and `five_hour.resets_at`
- Shows real `seven_day.utilization` and `seven_day.resets_at`
- Works instantly without setup (estimate mode)
- Optional "real mode" using cookie file
- Includes `cm setup` and `cm doctor`

## Usage

```bash
# Run monitor
cm

# Setup real usage mode
cm setup

# Diagnose cookie + API access
cm doctor
```

## Enable REAL MODE (Claude Web API)

Cookie stored here:

```
~/.claude_cookie.txt
```

Permissions required:

```bash
chmod 600 ~/.claude_cookie.txt
```

Example cookie file format (ONE line only):

```
sessionKey=sk-ant-sid02-xxxxx; cf_clearance=xxxxx; lastActiveOrg=xxxxxxxx
```

## Works Out The Box

This tool cannot auto-grab browser cookies safely.
Auto-extracting cookies from Chrome would become malware-adjacent.

So the correct UX is:

- `cm` runs immediately in estimate mode
- `cm setup` enables real mode
- `cm doctor` validates cookie + prints fix steps

## Build + Publish (for maintainer)

```bash
# Build
python3 -m build

# Upload to PyPI
python3 -m twine upload dist/*
```

## Author

**Sylvester Assiamah** — The Menu Papi
