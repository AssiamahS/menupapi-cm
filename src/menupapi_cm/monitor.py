#!/usr/bin/env python3
"""MenuPapi CM — Live usage monitor.

Self-contained Rich dashboard that shows:
  • Real Claude.ai usage from API (if cookie installed)
  • Local JSONL token data from ~/.claude/projects
  • Session grouping with keyword labels
  • Inline terminal command runner
  • Keyboard shortcuts for view toggling

Controls:
  1 / 2 / 3  →  Show 3 / 5 / 10 sessions
  T          →  Toggle inline terminal
  Q          →  Quit
"""

import json
import os
import subprocess
import sys
import threading
import time
import tty
import termios
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from select import select
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
COOKIE_PATH = os.path.expanduser("~/.claude_cookie.txt")

CLAUDE_DATA_PATHS = [
    Path("~/.claude/projects").expanduser(),
    Path("~/.config/claude/projects").expanduser(),
]

USAGE_JSONL_PATHS = [
    os.path.expanduser("~/.claude/code/usage/usage.jsonl"),
    os.path.expanduser("~/Library/Application Support/Claude/code/usage/usage.jsonl"),
]

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


# ─────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────
@dataclass
class UsageEntry:
    timestamp: datetime
    input_tokens: int
    output_tokens: int
    keyword: Optional[str] = None
    model: str = ""


# ─────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────
console = Console()
last_n_display = 3
stop_listen = False
terminal_mode = False
command_input = ""
command_history: List[str] = []
command_output: List[Dict[str, Any]] = []


# ─────────────────────────────────────────────
# Local data reader (self-contained)
# ─────────────────────────────────────────────
def _find_data_path() -> Optional[Path]:
    """Find Claude projects data directory."""
    for p in CLAUDE_DATA_PATHS:
        if p.exists() and p.is_dir():
            return p
    return None


def _load_entries_from_jsonl(hours=24) -> List[UsageEntry]:
    """Load usage entries from Claude JSONL files."""
    entries: List[UsageEntry] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Try project-based JSONL files
    data_path = _find_data_path()
    if data_path:
        for jsonl_file in data_path.rglob("*.jsonl"):
            entries.extend(_parse_jsonl_file(jsonl_file, cutoff))

    # Also try the usage.jsonl direct path
    for path_str in USAGE_JSONL_PATHS:
        p = Path(path_str)
        if p.exists():
            entries.extend(_parse_jsonl_file(p, cutoff))

    # Deduplicate by (timestamp, input_tokens, output_tokens)
    seen = set()
    unique = []
    for e in entries:
        key = (e.timestamp.isoformat(), e.input_tokens, e.output_tokens)
        if key not in seen:
            seen.add(key)
            unique.append(e)

    unique.sort(key=lambda e: e.timestamp)
    return unique


def _parse_jsonl_file(path: Path, cutoff: datetime) -> List[UsageEntry]:
    """Parse a single JSONL file into UsageEntry objects."""
    entries = []
    user_messages: Dict[str, str] = {}

    try:
        lines_data = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    lines_data.append(data)

                    # Collect user messages for keyword extraction
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
                            user_messages[uuid] = text[:100]

                except (json.JSONDecodeError, Exception):
                    continue

        for data in lines_data:
            entry = _map_entry(data, cutoff, user_messages)
            if entry:
                entries.append(entry)

    except Exception:
        pass

    return entries


def _map_entry(data: Dict, cutoff: datetime, user_messages: Dict[str, str]) -> Optional[UsageEntry]:
    """Map a raw JSON dict to a UsageEntry."""
    # Parse timestamp
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

    # Extract tokens
    input_tokens = 0
    output_tokens = 0

    # Try direct fields
    if "input_tokens" in data:
        input_tokens = int(data.get("input_tokens", 0) or 0)
        output_tokens = int(data.get("output_tokens", 0) or 0)
    else:
        # Try nested usage block
        usage = data.get("usage", {})
        if isinstance(usage, dict):
            input_tokens = int(usage.get("input_tokens", 0) or 0)
            output_tokens = int(usage.get("output_tokens", 0) or 0)

        # Try costUSD-style entries
        if input_tokens == 0 and output_tokens == 0:
            message = data.get("message", {})
            if isinstance(message, dict):
                msg_usage = message.get("usage", {})
                if isinstance(msg_usage, dict):
                    input_tokens = int(msg_usage.get("input_tokens", 0) or 0)
                    output_tokens = int(msg_usage.get("output_tokens", 0) or 0)

    if input_tokens == 0 and output_tokens == 0:
        return None

    # Extract keyword
    keyword = data.get("keyword")
    if not keyword:
        # Try to get from linked user message
        parent_uuid = data.get("parentUuid", "")
        text = user_messages.get(parent_uuid, "")
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
            keyword = " ".join(words[:4]) if len(words) <= 5 else " ".join(words[:3])
            if len(keyword) > 40:
                keyword = keyword[:37] + "..."

    model = ""
    if "model" in data:
        model = data["model"]
    elif isinstance(data.get("message"), dict):
        model = data["message"].get("model", "")

    return UsageEntry(
        timestamp=ts,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        keyword=keyword,
        model=model,
    )


# ─────────────────────────────────────────────
# Claude.ai API (real usage data)
# ─────────────────────────────────────────────
_cached_org_id: Optional[str] = None


def _get_org_id(cookie: str) -> Optional[str]:
    """Get org ID, with caching to avoid repeated calls."""
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


def fetch_web_usage() -> Optional[Dict]:
    """Fetch real usage data from claude.ai API.

    Returns dict with five_hour and seven_day data, or None on failure.
    """
    if not os.path.exists(COOKIE_PATH):
        return None
    try:
        with open(COOKIE_PATH) as f:
            cookie = f.read().strip()
        if not cookie:
            return None

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


def _format_reset_delta(resets_at_str: str) -> str:
    """Convert ISO resets_at string to 'Xh Ym' countdown."""
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


# ─────────────────────────────────────────────
# Session grouping
# ─────────────────────────────────────────────
def _group_entries_by_session(entries: List[UsageEntry], gap_minutes=5) -> List[Dict]:
    """Group entries into sessions based on time gaps."""
    if not entries:
        return []

    sessions = []
    current: Dict[str, Any] = {
        "entries": [],
        "start_time": None,
        "end_time": None,
        "total_tokens": 0,
        "keywords": [],
    }

    for entry in entries:
        ts = entry.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        if current["start_time"]:
            gap = (ts - current["end_time"]).total_seconds() / 60
            if gap > gap_minutes:
                sessions.append(current.copy())
                current = {
                    "entries": [],
                    "start_time": None,
                    "end_time": None,
                    "total_tokens": 0,
                    "keywords": [],
                }

        if not current["start_time"]:
            current["start_time"] = ts

        current["end_time"] = ts
        current["entries"].append(entry)
        current["total_tokens"] += entry.input_tokens + entry.output_tokens

        if entry.keyword and entry.keyword not in current["keywords"]:
            current["keywords"].append(entry.keyword)

    if current["entries"]:
        sessions.append(current)

    return sessions


# ─────────────────────────────────────────────
# Terminal command runner
# ─────────────────────────────────────────────
def _execute_command(cmd: str):
    """Execute a shell command and store output."""
    global command_output

    if not cmd.strip():
        return

    command_history.append(cmd)
    if len(command_history) > 50:
        command_history.pop(0)

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd=os.path.expanduser("~"),
        )
        output_text = result.stdout or result.stderr or "[Command completed]"
        command_output.append({
            "command": cmd,
            "output": output_text,
            "returncode": result.returncode,
            "timestamp": datetime.now(),
        })
    except subprocess.TimeoutExpired:
        command_output.append({
            "command": cmd,
            "output": "[ERROR] Timed out after 30s",
            "returncode": -1,
            "timestamp": datetime.now(),
        })
    except Exception as e:
        command_output.append({
            "command": cmd,
            "output": f"[ERROR] {e}",
            "returncode": -1,
            "timestamp": datetime.now(),
        })

    if len(command_output) > 20:
        command_output.pop(0)


# ─────────────────────────────────────────────
# Keyboard listener
# ─────────────────────────────────────────────
def _listen_for_keys():
    """Background thread for keyboard input."""
    global last_n_display, stop_listen, terminal_mode, command_input

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:
        while not stop_listen:
            if sys.stdin in select([sys.stdin], [], [], 0.1)[0]:
                ch = sys.stdin.read(1)

                if terminal_mode:
                    if ch == '\x1b':  # ESC
                        terminal_mode = False
                        command_input = ""
                    elif ch in ('\r', '\n'):  # Enter
                        if command_input.strip():
                            _execute_command(command_input)
                        command_input = ""
                    elif ch == '\x7f':  # Backspace
                        command_input = command_input[:-1]
                    elif ch.isprintable():
                        command_input += ch
                else:
                    if ch == "1":
                        last_n_display = 3
                    elif ch == "2":
                        last_n_display = 15
                    elif ch == "3":
                        last_n_display = 30
                    elif ch.lower() == "t":
                        terminal_mode = True
                        command_input = ""
                    elif ch.lower() == "q":
                        stop_listen = True
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


# ─────────────────────────────────────────────
# UI Panels
# ─────────────────────────────────────────────
def _render_usage_panel() -> Panel:
    """Main usage panel with token counts and reset timers."""
    entries = _load_entries_from_jsonl(hours=24)

    if not entries:
        return Panel(
            "No usage data found.\n\n"
            "[dim]Waiting for Claude Code usage data in ~/.claude/projects[/dim]",
            title="📊 MenuPapi Claude Monitor",
            border_style="yellow",
        )

    total_tokens = sum(e.input_tokens + e.output_tokens for e in entries)
    total_messages = len(entries)
    limit = 19000
    remaining = max(0, limit - total_tokens)
    percent = min(total_tokens / limit, 1.0)
    percent_used = int(percent * 100)

    now = datetime.now(timezone.utc)

    # Try real API data first
    web = fetch_web_usage()
    if web:
        five_hour = web.get("five_hour", {})
        seven_day = web.get("seven_day", {})
        s_util = five_hour.get("utilization") or 0
        w_util = seven_day.get("utilization") or 0
        s_pct = int(s_util) if s_util > 1 else int(s_util * 100)
        w_pct = int(w_util) if w_util > 1 else int(w_util * 100)
        s_delta = _format_reset_delta(five_hour.get("resets_at", ""))
        w_delta = _format_reset_delta(seven_day.get("resets_at", ""))
        session_str = f"⏱ Resets in {s_delta}  {s_pct}% used"
        weekly_str = f"📅 Weekly resets in {w_delta}  {w_pct}% used"
        percent_used = s_pct
    else:
        # Fallback: estimate from local logs
        latest_ts = max(
            e.timestamp.replace(tzinfo=timezone.utc)
            if e.timestamp.tzinfo is None else e.timestamp
            for e in entries
        )
        window_start = latest_ts - timedelta(hours=5)
        session_entries = [
            (e.timestamp.replace(tzinfo=timezone.utc)
             if e.timestamp.tzinfo is None else e.timestamp)
            for e in entries
            if (e.timestamp.replace(tzinfo=timezone.utc)
                if e.timestamp.tzinfo is None else e.timestamp) >= window_start
        ]
        if session_entries:
            session_delta = min(session_entries) + timedelta(hours=5) - now
            if session_delta.total_seconds() > 0:
                s_hrs = int(session_delta.total_seconds() // 3600)
                s_mins = int((session_delta.total_seconds() % 3600) // 60)
                session_str = f"⏱ Resets in {s_hrs}h {s_mins}m (est)"
            else:
                session_str = "⏱ Session window passed"
        else:
            session_str = "⏱ No active session"

        try:
            local_tz = ZoneInfo("America/New_York")
        except Exception:
            local_tz = timezone.utc
        now_local = datetime.now(local_tz)
        days_until_sunday = (6 - now_local.weekday()) % 7
        if days_until_sunday == 0 and now_local.hour >= 9:
            days_until_sunday = 7
        next_sunday = now_local.replace(
            hour=9, minute=0, second=0, microsecond=0
        ) + timedelta(days=days_until_sunday)
        weekly_delta = next_sunday - now_local
        w_days = weekly_delta.days
        w_hrs = int((weekly_delta.total_seconds() % 86400) // 3600)
        if w_days > 0:
            weekly_str = f"📅 Weekly resets in {w_days}d {w_hrs}h (est)"
        else:
            weekly_str = f"📅 Weekly resets in {w_hrs}h (est)"

    progress = Progress(
        TextColumn("💰 Tokens Used:"),
        BarColumn(bar_width=40),
        TextColumn(f"{total_tokens:,} / {limit:,}"),
        expand=False,
    )
    progress.add_task("", total=1.0, completed=percent)

    tbl = Table.grid(expand=True)
    tbl.add_row(
        f"🕒 Last {len(entries)} messages",
        f"📌 Current session  {percent_used}% used",
    )
    tbl.add_row(
        f"🧮 Tokens Remaining: {remaining:,}",
        f"📨 Messages: {total_messages}",
    )
    tbl.add_row(
        f"[cyan]🧠 Tokens Spent (Total):[/cyan] {total_tokens:,}",
        f"[green]{session_str}[/green]",
    )
    tbl.add_row("", f"[yellow]{weekly_str}[/yellow]")

    return Panel(
        Group(progress, tbl),
        title="✦ ✧ MENUPAPI CLAUDE MONITOR ✦ ✧",
        border_style="green",
    )


def _render_sessions_panel() -> Panel:
    """Sessions overlay grouped by time gaps."""
    entries = _load_entries_from_jsonl(hours=24)

    if not entries:
        return Panel(
            "⚠️ No token data yet.",
            title="🧠 Recent Sessions",
            border_style="yellow",
        )

    all_sessions = _group_entries_by_session(entries, gap_minutes=5)

    if not all_sessions:
        return Panel(
            "⚠️ No sessions found.",
            title="🧠 Recent Sessions",
            border_style="yellow",
        )

    num_sessions_map = {3: 3, 15: 5, 30: 10}
    num_sessions = num_sessions_map.get(last_n_display, 3)
    recent_sessions = all_sessions[-num_sessions:]

    msgs = []
    total_tokens_all = 0

    for idx, session in enumerate(recent_sessions, start=1):
        start_time = session["start_time"].strftime("%H:%M:%S")
        end_time = session["end_time"].strftime("%H:%M:%S")
        duration = (session["end_time"] - session["start_time"]).total_seconds() / 60
        tokens = session["total_tokens"]
        num_messages = len(session["entries"])

        keyword = session["keywords"][0] if session["keywords"] else "Session"

        if tokens > 10000:
            token_color = "red"
        elif tokens > 5000:
            token_color = "yellow"
        else:
            token_color = "green"

        msgs.append(
            f"[bold cyan]Session {idx}:[/bold cyan] [{start_time} - {end_time}] "
            f"([{token_color}]{tokens:,} tokens[/{token_color}], "
            f"{num_messages} msgs, {duration:.1f}m)"
        )
        msgs.append(f"  [dim italic]→ {keyword}[/dim italic]")
        total_tokens_all += tokens

    avg = total_tokens_all / len(recent_sessions) if recent_sessions else 0

    lines = "\n".join(msgs + [
        "─" * 60,
        f"[bold]Total:[/bold] {total_tokens_all:,} tokens across {len(recent_sessions)} sessions",
        f"[bold]Avg/session:[/bold] {avg:.0f} tokens",
        "[dim]Press 1=3 • 2=5 • 3=10 sessions • T=Terminal • Q=Quit[/dim]",
    ])

    return Panel(
        lines,
        title=f"🧠 Recent Sessions (last {len(recent_sessions)})",
        border_style="cyan",
    )


def _render_terminal_panel() -> Optional[Panel]:
    """Inline terminal panel (only shown when terminal_mode is active)."""
    if not terminal_mode:
        return None

    lines = []
    recent = command_output[-5:] if command_output else []

    if recent:
        lines.append("[bold cyan]Recent Commands:[/bold cyan]")
        lines.append("")
        for item in recent:
            ts = item["timestamp"].strftime("%H:%M:%S")
            cmd = item["command"]
            rc = item["returncode"]
            output = item["output"]

            color = "green" if rc == 0 else "red"
            lines.append(f"[{color}]▶[/{color}] [{ts}] [bold]{cmd}[/bold]")

            for line in output.strip().split("\n")[:10]:
                lines.append(f"  [dim]{line}[/dim]")
            total_lines = len(output.strip().split("\n"))
            if total_lines > 10:
                lines.append(f"  [dim italic]... ({total_lines - 10} more)[/dim italic]")
            lines.append("")
    else:
        lines.append("[dim italic]No commands executed yet.[/dim italic]")
        lines.append("")

    lines.append("─" * 60)
    lines.append(f"[bold yellow]$ {command_input}[/bold yellow]█")
    lines.append("")
    lines.append("[dim]ENTER to run • ESC to exit terminal mode[/dim]")

    return Panel(
        "\n".join(lines),
        title="💻 Terminal",
        border_style="magenta",
    )


def _render_layout() -> Group:
    """Combine all panels."""
    panels = [_render_usage_panel(), _render_sessions_panel()]
    terminal_panel = _render_terminal_panel()
    if terminal_panel:
        panels.append(terminal_panel)
    return Group(*panels)


# ─────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────
def run_monitor():
    """Launch the live dashboard."""
    global stop_listen

    console.clear()
    console.print(
        "[dim]MenuPapi Claude Monitor v1.0.0 — "
        "press 1|2|3 to change view, T for terminal, Q to quit[/dim]\n"
    )

    listener = threading.Thread(target=_listen_for_keys, daemon=True)
    listener.start()

    with Live(_render_layout(), refresh_per_second=0.5, console=console) as live:
        try:
            while not stop_listen:
                live.update(_render_layout())
                time.sleep(3)
        except KeyboardInterrupt:
            stop_listen = True
        finally:
            console.clear()
            console.print("[red]👋 Exiting MenuPapi Claude Monitor.[/red]")
