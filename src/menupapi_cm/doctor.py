import os

from menupapi_cm.core.web_usage import COOKIE_PATH, fetch_usage_data
from menupapi_cm.core.formatters import format_reset_delta, normalize_utilization


def run_doctor():
    print()
    print("🧪 MENUPAPI-CM Doctor")
    print("=" * 40)
    print()

    passed = 0
    failed = 0

    # Check 1: cookie file exists
    if not os.path.exists(COOKIE_PATH):
        print(f"❌ Missing cookie file: {COOKIE_PATH}")
        print("   Fix: cm setup")
        print()
        return
    print(f"✅ Cookie file exists: {COOKIE_PATH}")
    passed += 1

    # Check 2: permissions
    try:
        perms = oct(os.stat(COOKIE_PATH).st_mode & 0o777)
        if perms == "0o600":
            print(f"✅ Permissions: {perms} (secure)")
            passed += 1
        else:
            print(f"⚠️  Permissions: {perms} (should be 0o600)")
            print(f"   Fix: chmod 600 {COOKIE_PATH}")
            failed += 1
    except Exception:
        pass

    # Check 3: read cookie content
    with open(COOKIE_PATH) as f:
        cookie = f.read().strip()

    if not cookie:
        print("❌ Cookie file is EMPTY")
        failed += 1
        _summary(passed, failed)
        return
    print(f"✅ Cookie length: {len(cookie)} chars")
    passed += 1

    # Check 4: sessionKey present
    if "sessionKey=" in cookie:
        print("✅ sessionKey: present")
        passed += 1
    else:
        print("❌ sessionKey: MISSING")
        failed += 1

    # Check 5: cf_clearance present
    if "cf_clearance=" in cookie:
        print("✅ cf_clearance: present")
        passed += 1
    else:
        print("⚠️  cf_clearance: MISSING (may cause 403)")
        failed += 1

    # Check 6: API test
    print()
    print("Testing Claude usage API...")
    usage = fetch_usage_data()

    if not usage:
        print("❌ API call failed.")
        print("   Likely: sessionKey or cf_clearance expired")
        print("   Fix: re-copy cookie from browser DevTools")
        failed += 1
        _summary(passed, failed)
        return

    print("✅ Claude usage API working")
    passed += 1

    # Show stats
    five = usage.get("five_hour") or {}
    seven = usage.get("seven_day") or {}
    s_pct = normalize_utilization(five.get("utilization"))
    w_pct = normalize_utilization(seven.get("utilization"))
    s_reset = format_reset_delta(five.get("resets_at"))
    w_reset = format_reset_delta(seven.get("resets_at"))

    print()
    print("�� Current Usage:")
    print(f"   ⏱  5-hour:  {s_pct}% used — resets in {s_reset}")
    print(f"   📅  Weekly:  {w_pct}% used — resets in {w_reset}")

    _summary(passed, failed)


def _summary(passed, failed):
    total = passed + failed
    print()
    if failed == 0:
        print(f"🎯 All {total} checks passed.")
    else:
        print(f"⚠️  {passed}/{total} passed, {failed} failed")
    print()
