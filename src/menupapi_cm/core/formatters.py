from datetime import datetime, timezone


def format_reset_delta(resets_at_str):
    if not resets_at_str:
        return "?"
    try:
        reset_dt = datetime.fromisoformat(resets_at_str.replace("Z", "+00:00"))
        delta = reset_dt - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "now"
        hrs = int(delta.total_seconds() // 3600)
        mins = int((delta.total_seconds() % 3600) // 60)
        return f"{hrs}h {mins}m"
    except Exception:
        return "?"


def normalize_utilization(util):
    """Normalize utilization to percent int.

    Claude API returns either 34.0 (already percent) or 0.34 (fraction).
    """
    if util is None:
        return 0
    try:
        util = float(util)
    except Exception:
        return 0
    if util > 1:
        return int(util)
    return int(util * 100)
