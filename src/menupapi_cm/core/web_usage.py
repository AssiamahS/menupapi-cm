import json
import os
import urllib.request

COOKIE_PATH = os.path.expanduser("~/.claude_cookie.txt")

API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://claude.ai/settings/usage",
    "Origin": "https://claude.ai",
}

_cached_org_id = None


def _read_cookie():
    if not os.path.exists(COOKIE_PATH):
        return None
    with open(COOKIE_PATH, "r") as f:
        cookie = f.read().strip()
    return cookie if cookie else None


def _get_org_id(cookie):
    global _cached_org_id
    if _cached_org_id:
        return _cached_org_id
    try:
        req = urllib.request.Request(
            "https://claude.ai/api/organizations",
            headers={"Cookie": cookie, **API_HEADERS},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            orgs = json.loads(resp.read())
        _cached_org_id = orgs[0]["uuid"] if isinstance(orgs, list) else orgs["uuid"]
        return _cached_org_id
    except Exception:
        return None


def fetch_usage_data():
    """Fetch real usage from claude.ai API. Returns dict or None."""
    cookie = _read_cookie()
    if not cookie:
        return None
    try:
        org_id = _get_org_id(cookie)
        if not org_id:
            return None
        req = urllib.request.Request(
            f"https://claude.ai/api/organizations/{org_id}/usage",
            headers={"Cookie": cookie, **API_HEADERS},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None
