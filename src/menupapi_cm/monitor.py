"""
MenuPapi CM — Live usage + token monitor.

Reads real token data from ~/.claude/projects JSONL files.
Shows real Claude.ai session reset data via cookie API.
Falls back to estimate mode if cookie missing.

Press:
  1 = last 3 sessions
  2 = last 5
  3 = last 10
  h = hide/show sessions
  q = quit
"""

import json
import os
import select
import sys
import termios
import time
import tty
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

from menupapi_cm.core.web_usage import fetch_usage_data
from menupapi_cm.core.formatters import format_reset_delta, normalize_utilization


console = Console()

# Where Claude Code stores usage data
CLAUDE_DATA_PATHS = [
    Path("~/.claude/projects").expanduser(),
    Path("~/.config/claude/projects").expanduser(),
]


# ─────────────────────────────────────────
# Local JSONL reader
# ─────────────────────────────────────────
def _find_data_path():
    for p in CLAUDE_DATA_PATHS:
        if p.exists() and p.is_dir():
            return p
    return None


def _load_entries(hours=24):
    """Load usage entries from Claude JSONL files."""
    entries = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    data_path = _find_data_path()
    if not data_path:
        return entries

    for jsonl_file in data_path.rglob("*.jsonl"):
        entries.extend(_parse_file(jsonl_file, cutoff))

    # Deduplicate
    seen = set()
    unique = []
    for e in entries:
        key = (e["ts"].isoformat(), e["in"], e["out"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda e: e["ts"])
    return unique


def _parse_file(path, cutoff):
    entries = []
    user_msgs = {}
    lines_data = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    lines_data.append(data)
                    if data.get("type") == "user":
                        uuid = data.get("uuid", "")
                        msg = data.get("message", {})
                        content = msg.get("content", "") if isinstance(msg, dict) else ""
                        text = ""
                        if isinstance(content, str):
                            text = content
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "")
                                    break
                        if uuid and text:
                            user_msgs[uuid] = text[:80]
                except Exception:
                    continue

        for data in lines_data:
            e = _map_entry(data, cutoff, user_msgs)
            if e:
                entries.append(e)
    except Exception:
        pass
    return entries


def _map_entry(data, cutoff, user_msgs):
    ts_str = data.get("timestamp")
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return None
    if ts < cutoff:
        return None

    inp = 0
    out = 0
    if "input_tokens" in data:
        inp = int(data.get("input_tokens", 0) or 0)
        out = int(data.get("output_tokens", 0) or 0)
    else:
        usage = data.get("usage", {})
        if isinstance(usage, dict):
            inp = int(usage.get("input_tokens", 0) or 0)
            out = int(usage.get("output_tokens", 0) or 0)
        if inp == 0 and out == 0:
            msg = data.get("message", {})
            if isinstance(msg, dict):
                mu = msg.get("usage", {})
                if isinstance(mu, dict):
                    inp = int(mu.get("input_tokens", 0) or 0)
                    out = int(mu.get("output_tokens", 0) or 0)
    if inp == 0 and out == 0:
        return None

    keyword = data.get("keyword")
    if not keyword:
        parent = data.get("parentUuid", "")
        text = user_msgs.get(parent, "")
        if not text:
            msg = data.get("message", {})
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            break
        if text:
            words = text.strip().split()
            keyword = " ".join(words[:4])
            if len(keyword) > 40:
                keyword = keyword[:37] + "..."

    return {"ts": ts, "in": inp, "out": out, "keyword": keyword or ""}


# ─────────────────────────────────────────
# Session grouping
# ─────────────────────────────────────────
def _group_sessions(entries, gap_minutes=5):
    if not entries:
        return []
    sessions = []
    cur = {"entries": [], "start": None, "end": None, "tokens": 0, "keywords": []}

    for e in entries:
        if cur["start"] and (e["ts"] - cur["end"]).total_seconds() / 60 > gap_minutes:
            sessions.append(cur)
            cur = {"entries": [], "start": None, "end": None, "tokens": 0, "keywords": []}
        if not cur["start"]:
            cur["start"] = e["ts"]
        cur["end"] = e["ts"]
        cur["entries"].append(e)
        cur["tokens"] += e["in"] + e["out"]
        if e["keyword"] and e["keyword"] not in cur["keywords"]:
            cur["keywords"].append(e["keyword"])

    if cur["entries"]:
        sessions.append(cur)
    return sessions


# ─────────────────────────────────────────
# UI
# ─────────────────────────────────────────
mode = "1"
visible = True


def render():
    entries = _load_entries(hours=24)
    web = fetch_usage_data()

    total_tokens = sum(e["in"] + e["out"] for e in entries)
    total_messages = len(entries)
    limit = 45000
    remaining = max(0, limit - total_tokens)
    pct = min(total_tokens / limit, 1.0)
    pct_int = int(pct * 100)

    # ── Top: Token bar ──
    if web:
        five = web.get("five_hour") or {}
        seven = web.get("seven_day") or {}
        s_pct = normalize_utilization(five.get("utilization"))
        w_pct = normalize_utilization(seven.get("utilization"))
        s_resets_at = five.get("resets_at")
        w_resets_at = seven.get("resets_at")
        s_reset = format_reset_delta(s_resets_at)
        w_reset = format_reset_delta(w_resets_at)

        if s_resets_at and s_pct > 0:
            session_str = f"\u23f1 Resets in {s_reset}  {s_pct}% used"
        elif s_pct == 0:
            session_str = "\u23f1 5h available  0% used (fresh session)"
        else:
            session_str = f"\u23f1 {s_pct}% used"

        if w_resets_at:
            weekly_str = f"\U0001f4c5 Weekly resets in {w_reset}  {w_pct}% used"
        else:
            weekly_str = f"\U0001f4c5 Weekly  {w_pct}% used"
        pct_int = s_pct
    else:
        session_str = "\u23f1 Estimate mode (run cm setup for real data)"
        weekly_str = "\U0001f4c5 Estimate mode"

    progress = Progress(
        TextColumn("\U0001f4b0 Tokens Used:"),
        BarColumn(bar_width=40),
        TextColumn(f"{total_tokens:,} / {limit:,}"),
        expand=False,
    )
    progress.add_task("", total=1.0, completed=pct)

    tbl = Table.grid(expand=True)
    tbl.add_row(
        f"\U0001f552 Last {total_messages} messages",
        f"\U0001f4cc Current session  {pct_int}% used",
    )
    tbl.add_row(
        f"\U0001f9ee Tokens Remaining: {remaining:,}",
        f"\U0001f4e8 Messages: {total_messages}",
    )
    tbl.add_row(
        f"[cyan]\U0001f9e0 Tokens Spent (Total):[/cyan] {total_tokens:,}",
        f"[green]{session_str}[/green]",
    )
    tbl.add_row("", f"[yellow]{weekly_str}[/yellow]")

    usage_panel = Panel(
        Group(progress, tbl),
        title="\u2726 \u2727 MENUPAPI CLAUDE MONITOR \u2726 \u2727",
        border_style="green",
    )

    # ── Bottom: Sessions ──
    if not visible:
        return Group(usage_panel)

    sessions = _group_sessions(entries, gap_minutes=5)
    if not sessions:
        return Group(
            usage_panel,
            Panel("[yellow]No sessions found[/yellow]", title="\U0001f9e0 Sessions", border_style="yellow"),
        )

    num_map = {"1": 3, "2": 5, "3": 10}
    n = num_map.get(mode, 3)
    recent = sessions[-n:]

    lines = []
    total_all = 0
    for idx, s in enumerate(recent, 1):
        st = s["start"].strftime("%H:%M:%S")
        et = s["end"].strftime("%H:%M:%S")
        dur = (s["end"] - s["start"]).total_seconds() / 60
        tok = s["tokens"]
        msgs = len(s["entries"])
        kw = s["keywords"][0] if s["keywords"] else "Session"

        if tok > 10000:
            tc = "red"
        elif tok > 5000:
            tc = "yellow"
        else:
            tc = "green"

        lines.append(
            f"[bold cyan]Session {idx}:[/bold cyan] [{st} - {et}] "
            f"([{tc}]{tok:,} tokens[/{tc}], {msgs} msgs, {dur:.1f}m)"
        )
        lines.append(f"  [dim italic]\u2192 {kw}[/dim italic]")
        total_all += tok

    avg = total_all / len(recent) if recent else 0
    lines.append("\u2500" * 60)
    lines.append(f"[bold]Total:[/bold] {total_all:,} tokens across {len(recent)} sessions")
    lines.append(f"[bold]Avg/session:[/bold] {avg:.0f} tokens")
    lines.append("[dim]1=3 \u2022 2=5 \u2022 3=10 sessions \u2022 h=hide \u2022 q=quit[/dim]")

    sessions_panel = Panel(
        "\n".join(lines),
        title=f"\U0001f9e0 Recent Sessions (last {len(recent)})",
        border_style="cyan",
    )

    return Group(usage_panel, sessions_panel)


def run_monitor():
    global mode, visible

    console.print("\n[bold green]MENUPAPI CM starting...[/bold green]\n")
    console.print("[dim]1|2|3 sessions \u2022 h=hide \u2022 q=quit[/dim]\n")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)
        with Live(render(), refresh_per_second=0.5, console=console) as live:
            while True:
                if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1)
                    if key == "q":
                        break
                    elif key in ("1", "2", "3"):
                        mode = key
                    elif key == "h":
                        visible = not visible

                live.update(render())
                time.sleep(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    console.print("\n[bold red]Exiting.[/bold red]\n")
