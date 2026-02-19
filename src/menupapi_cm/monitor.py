"""MenuPapi CM — Live usage monitor.

Shows real Claude.ai usage data if cookie exists,
falls back to estimate mode otherwise.
Press CTRL+C to exit.
"""

import time
from datetime import datetime, timezone

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from menupapi_cm.core.web_usage import fetch_usage_data
from menupapi_cm.core.formatters import format_reset_delta, normalize_utilization


console = Console()


def render_panel():
    web = fetch_usage_data()

    table = Table(show_header=False, box=None)
    table.add_column("k", style="bold cyan")
    table.add_column("v", style="bold white")

    if web:
        five_hour = web.get("five_hour") or {}
        seven_day = web.get("seven_day") or {}

        s_util = normalize_utilization(five_hour.get("utilization"))
        w_util = normalize_utilization(seven_day.get("utilization"))

        s_reset = format_reset_delta(five_hour.get("resets_at"))
        w_reset = format_reset_delta(seven_day.get("resets_at"))

        table.add_row("\u23f1 Session", f"Resets in {s_reset}   {s_util}% used")
        table.add_row("\U0001f4c5 Weekly", f"Resets in {w_reset}   {w_util}% used")
        mode = "REAL MODE"
    else:
        table.add_row("\u23f1 Session", "Estimate mode (cookie missing/invalid)")
        table.add_row("\U0001f4c5 Weekly", "Estimate mode")
        mode = "ESTIMATE MODE"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    table.add_row("\U0001f552 Now", now)
    table.add_row("\U0001f451 Mode", mode)

    return Panel(table, title="MENUPAPI CM", border_style="green")


def run_monitor():
    console.print("\n[bold green]MENUPAPI CM starting...[/bold green]\n")
    console.print("[dim]Press CTRL+C to exit[/dim]\n")

    try:
        with Live(render_panel(), refresh_per_second=0.5, console=console) as live:
            while True:
                live.update(render_panel())
                time.sleep(2)
    except KeyboardInterrupt:
        console.print("\n[bold red]Exiting.[/bold red]\n")
