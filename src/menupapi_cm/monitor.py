"""
MenuPapi CM — Live usage + token monitor.

Combines:
- Claude.ai REAL session reset data (5-hour + weekly) via cookie API
- Local token usage history (~/.claude_message_history.json)

Press:
  1 = last session/messages view
  2 = last 3
  3 = last 10
  h = hide/show
  q = quit
"""

import os
import sys
import time
import json
import select
import termios
import tty
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn

from menupapi_cm.core.web_usage import fetch_usage_data
from menupapi_cm.core.formatters import format_reset_delta, normalize_utilization


console = Console()


HISTORY_FILE = Path.home() / ".claude_message_history.json"


def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def summarize_tokens(messages):
    if not messages:
        return {
            "total_used": 0,
            "total_after": 0,
            "count": 0,
            "avg_used": 0,
        }

    total_used = sum(m.get("tokens_used", 0) for m in messages)
    last_after = messages[-1].get("tokens_after", 0)
    count = len(messages)
    avg_used = total_used / count if count else 0

    return {
        "total_used": total_used,
        "total_after": last_after,
        "count": count,
        "avg_used": avg_used,
    }


def render_panel(mode="1", visible=True):
    web = fetch_usage_data()
    messages = load_history()

    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column("k", style="bold cyan", width=16)
    table.add_column("v", style="bold white")

    # Claude Web API Usage
    if web:
        five_hour = web.get("five_hour") or {}
        seven_day = web.get("seven_day") or {}

        s_util = normalize_utilization(five_hour.get("utilization"))
        w_util = normalize_utilization(seven_day.get("utilization"))

        s_reset = format_reset_delta(five_hour.get("resets_at"))
        w_reset = format_reset_delta(seven_day.get("resets_at"))

        table.add_row("\u23f1 Session", f"Resets in {s_reset}   {s_util}% used")
        table.add_row("\U0001f4c5 Weekly", f"Resets in {w_reset}   {w_util}% used")
        mode_str = "REAL MODE"
    else:
        table.add_row("\u23f1 Session", "Estimate mode (cookie missing/invalid)")
        table.add_row("\U0001f4c5 Weekly", "Estimate mode")
        mode_str = "ESTIMATE MODE"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    table.add_row("\U0001f552 Now", now)
    table.add_row("\U0001f451 Mode", mode_str)

    table.add_row("", "")
    table.add_row("\u2501" * 8, "\u2501" * 36)

    # Token Usage History
    if not visible:
        table.add_row("\U0001f9e0 Tokens", "[dim]Hidden (press h)[/dim]")
        return Panel(table, title="MENUPAPI CM", border_style="green")

    if not messages:
        table.add_row("\U0001f9e0 Tokens", "[yellow]No token history found yet[/yellow]")
        table.add_row("Hint", f"[dim]{HISTORY_FILE} missing[/dim]")
        return Panel(table, title="MENUPAPI CM", border_style="green")

    # Mode selection for history window
    if mode == "1":
        window = messages[-1:]
        title = "Last Message"
    elif mode == "2":
        window = messages[-3:]
        title = "Last 3 Messages"
    else:
        window = messages[-10:]
        title = "Last 10 Messages"

    stats = summarize_tokens(window)

    table.add_row("\U0001f4cc View", title)
    table.add_row("\U0001f4e8 Messages", str(stats["count"]))
    table.add_row("\U0001f4b0 Tokens Used", f'{stats["total_used"]:,}')
    table.add_row("\U0001f9ee Avg/Msg", f'{stats["avg_used"]:.1f}')
    table.add_row("\U0001f4ca Tokens After", f'{stats["total_after"]:,}')

    table.add_row("", "")
    table.add_row("Recent", "\u2501" * 36)

    # Show previews
    for i, msg in enumerate(window[::-1], 1):
        ts = msg.get("timestamp", "")
        tokens_used = msg.get("tokens_used", 0)
        preview = msg.get("preview", "")

        try:
            t = datetime.fromisoformat(ts).strftime("%H:%M:%S")
        except Exception:
            t = "??:??:??"

        preview = preview.replace("\n", " ").strip()
        if len(preview) > 60:
            preview = preview[:60] + "..."

        table.add_row(
            f"#{i}",
            f"[white]{t}[/white]  [green]{tokens_used:,}[/green] tokens  [dim]{preview}[/dim]",
        )

    table.add_row("", "")
    table.add_row(
        "Keys",
        "[dim]1=last \u2022 2=3 msgs \u2022 3=10 msgs \u2022 h=hide \u2022 q=quit[/dim]",
    )

    return Panel(table, title="MENUPAPI CM", border_style="green")


def run_monitor():
    console.print("\n[bold green]MENUPAPI CM starting...[/bold green]\n")
    console.print("[dim]Press q to quit[/dim]\n")

    mode = "1"
    visible = True

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)

        with Live(render_panel(mode, visible), refresh_per_second=2, console=console) as live:
            while True:
                if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                    key = sys.stdin.read(1)

                    if key == "q":
                        break
                    elif key == "1":
                        mode = "1"
                    elif key == "2":
                        mode = "2"
                    elif key == "3":
                        mode = "3"
                    elif key == "h":
                        visible = not visible

                live.update(render_panel(mode, visible))
                time.sleep(0.3)

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    console.print("\n[bold red]Exiting.[/bold red]\n")
