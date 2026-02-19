#!/usr/bin/env python3
"""MenuPapi CM — Cookie setup wizard.

Guides user to paste their Claude.ai cookie string,
validates it against the API, and saves to ~/.claude_cookie.txt.
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


def _format_delta(resets_at):
    """Convert ISO reset timestamp to 'Xh Ym' countdown."""
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


def _test_cookie(cookie):
    """Test cookie against Claude.ai API.

    Returns (ok, org_id_or_error, usage_json_or_none).
    """
    try:
        # Step 1: get org ID
        headers = {"Cookie": cookie, **HEADERS_BASE}
        req = urllib.request.Request(
            "https://claude.ai/api/organizations",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            orgs = json.loads(resp.read())

        org_id = orgs[0]["uuid"] if isinstance(orgs, list) else orgs["uuid"]

        # Step 2: fetch usage
        req2 = urllib.request.Request(
            f"https://claude.ai/api/organizations/{org_id}/usage",
            headers=headers,
        )
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            usage = json.loads(resp2.read())

        return True, org_id, usage

    except Exception as e:
        return False, str(e), None


def run_setup():
    """Interactive cookie setup wizard."""
    print()
    print("🔥 MenuPapi CM Setup — Enable REAL Claude reset countdown")
    print("=" * 58)
    print()
    print("Claude.ai protects their usage API behind Cloudflare.")
    print("To get real session reset timers, you paste your browser cookie.")
    print()
    print("✅ Steps to get the cookie:")
    print()
    print("  1) Open https://claude.ai/settings/usage in Chrome")
    print("  2) Open DevTools (Cmd+Option+I) → Network tab")
    print("  3) Click 'Refresh usage limits' on the page")
    print("  4) In Network tab, click the request to /api/organizations/.../usage")
    print("  5) Go to Headers → Request Headers → find 'cookie'")
    print("  6) Right-click the cookie value → Copy value")
    print()
    print("Paste the full cookie string below.")
    print("(It should contain sessionKey= and ideally cf_clearance=)")
    print()

    try:
        cookie = input("Cookie: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nSetup cancelled.")
        return

    if not cookie:
        print("\n❌ Empty input. Setup cancelled.")
        return

    if "sessionKey=" not in cookie:
        print("\n❌ Invalid cookie — missing sessionKey=")
        print("You need to copy the full 'cookie' header from DevTools.")
        print("It must contain at least: sessionKey=sk-ant-...")
        return

    # Save cookie
    with open(COOKIE_PATH, "w") as f:
        f.write(cookie)
    os.chmod(COOKIE_PATH, 0o600)

    print()
    print("🔍 Testing cookie against Claude.ai API...")
    print()

    ok, org_id, usage = _test_cookie(cookie)

    if not ok:
        print("❌ Cookie test FAILED.")
        print(f"   Error: {org_id}")
        print()
        print("⚠️  Common fixes:")
        print("   • Make sure cookie includes cf_clearance= (Cloudflare token)")
        print("   • The cf_clearance expires — re-copy from DevTools")
        print("   • Make sure you copied the entire cookie header")
        print()
        print(f"Cookie saved to {COOKIE_PATH} anyway — you can retry with 'cm doctor'")
        return

    # Success — show results
    five_hour = usage.get("five_hour", {})
    seven_day = usage.get("seven_day", {})

    s_util = five_hour.get("utilization", 0)
    w_util = seven_day.get("utilization", 0)
    s_pct = int(s_util) if s_util > 1 else int(s_util * 100)
    w_pct = int(w_util) if w_util > 1 else int(w_util * 100)

    s_reset = _format_delta(five_hour.get("resets_at", ""))
    w_reset = _format_delta(seven_day.get("resets_at", ""))

    print("✅ SUCCESS — Cookie is valid!")
    print(f"   Org ID: {org_id}")
    print()
    print(f"   ⏱  5-hour:  resets in {s_reset}   {s_pct}% used")
    print(f"   📅  Weekly:  resets in {w_reset}   {w_pct}% used")
    print()
    print(f"   Cookie saved to: {COOKIE_PATH}")
    print()
    print("Now run: cm")
    print()
