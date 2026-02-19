#!/usr/bin/env python3
"""MenuPapi CM — Doctor / health check.

Checks:
  • Cookie file exists
  • Cookie contains sessionKey
  • Cookie contains cf_clearance
  • API connectivity (org fetch + usage fetch)
  • Current usage stats
"""

import json
import os
import urllib.request
from datetime import datetime, timezone

COOKIE_PATH = os.path.expanduser("~/.claude_cookie.txt")

HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://claude.ai/settings/usage",
    "Origin": "https://claude.ai",
}


def run_doctor():
    """Run health checks on cookie and API connectivity."""
    print()
    print("🩺 MenuPapi CM Doctor")
    print("=" * 40)
    print()

    passed = 0
    failed = 0

    # Check 1: Cookie file exists
    if os.path.exists(COOKIE_PATH):
        print(f"  ✅ Cookie file exists: {COOKIE_PATH}")
        passed += 1
    else:
        print(f"  ❌ Cookie file NOT found: {COOKIE_PATH}")
        print("     Run 'cm setup' to create it.")
        failed += 1
        _print_summary(passed, failed)
        return

    # Check 2: File permissions
    mode = oct(os.stat(COOKIE_PATH).st_mode)[-3:]
    if mode == "600":
        print(f"  ✅ File permissions: {mode} (secure)")
        passed += 1
    else:
        print(f"  ⚠️  File permissions: {mode} (should be 600)")
        print(f"     Run: chmod 600 {COOKIE_PATH}")
        failed += 1

    # Check 3: Read cookie
    with open(COOKIE_PATH) as f:
        cookie = f.read().strip()

    if not cookie:
        print("  ❌ Cookie file is EMPTY")
        failed += 1
        _print_summary(passed, failed)
        return

    print(f"  ✅ Cookie length: {len(cookie)} chars")
    passed += 1

    # Check 4: sessionKey present
    if "sessionKey=" in cookie:
        # Extract and show first/last chars
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("sessionKey="):
                val = part.split("=", 1)[1]
                print(f"  ✅ sessionKey: {val[:20]}...{val[-10:]}")
                break
        passed += 1
    else:
        print("  ❌ sessionKey= NOT found in cookie")
        failed += 1

    # Check 5: cf_clearance present
    if "cf_clearance=" in cookie:
        print("  ✅ cf_clearance: present (Cloudflare token)")
        passed += 1
    else:
        print("  ⚠️  cf_clearance: MISSING (may cause 403 errors)")
        print("     Re-copy cookie from DevTools to include it")
        failed += 1

    # Check 6: API connectivity
    print()
    print("  🔍 Testing API connectivity...")

    try:
        headers = {"Cookie": cookie, **HEADERS_BASE}
        req = urllib.request.Request(
            "https://claude.ai/api/organizations",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            orgs = json.loads(resp.read())
        org_id = orgs[0]["uuid"] if isinstance(orgs, list) else orgs["uuid"]
        print(f"  ✅ Organizations API: OK (org={org_id[:8]}...)")
        passed += 1
    except Exception as e:
        print(f"  ❌ Organizations API: FAILED ({e})")
        failed += 1
        _print_summary(passed, failed)
        return

    # Check 7: Usage API
    try:
        req2 = urllib.request.Request(
            f"https://claude.ai/api/organizations/{org_id}/usage",
            headers=headers,
        )
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            usage = json.loads(resp2.read())
        print("  ✅ Usage API: OK")
        passed += 1

        # Show current stats
        five = usage.get("five_hour", {})
        seven = usage.get("seven_day", {})

        s_util = five.get("utilization", 0)
        w_util = seven.get("utilization", 0)
        s_pct = int(s_util) if s_util > 1 else int(s_util * 100)
        w_pct = int(w_util) if w_util > 1 else int(w_util * 100)

        s_reset = _format_delta(five.get("resets_at", ""))
        w_reset = _format_delta(seven.get("resets_at", ""))

        print()
        print("  📊 Current Usage:")
        print(f"     ⏱  5-hour:  {s_pct}% used — resets in {s_reset}")
        print(f"     📅  Weekly:  {w_pct}% used — resets in {w_reset}")

    except Exception as e:
        print(f"  ❌ Usage API: FAILED ({e})")
        failed += 1

    _print_summary(passed, failed)


def _format_delta(resets_at):
    try:
        reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        delta = reset_dt - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "now"
        hrs = int(delta.total_seconds() // 3600)
        mins = int((delta.total_seconds() % 3600) // 60)
        return f"{hrs}h {mins}m"
    except Exception:
        return "?"


def _print_summary(passed, failed):
    total = passed + failed
    print()
    if failed == 0:
        print(f"  🎯 All {total} checks passed! You're good to go.")
    else:
        print(f"  ⚠️  {passed}/{total} checks passed, {failed} failed")
    print()
