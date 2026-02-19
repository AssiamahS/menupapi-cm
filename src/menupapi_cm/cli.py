#!/usr/bin/env python3
"""MenuPapi CM — CLI entry point.

Commands:
    cm              Run the live usage monitor
    cm setup        Install Claude.ai cookie for real API access
    cm doctor       Check cookie status and connectivity
    cm help         Show help
"""

import sys

from menupapi_cm.setup import run_setup
from menupapi_cm.doctor import run_doctor
from menupapi_cm.monitor import run_monitor


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

        if cmd in ("setup", "login", "--setup"):
            run_setup()
            return

        if cmd in ("doctor", "status", "--doctor"):
            run_doctor()
            return

        if cmd in ("help", "--help", "-h"):
            print("""
🔥 MenuPapi CM (Claude Monitor) v1.0.0

Usage:
  cm              Launch live usage monitor
  cm setup        Install Claude.ai cookie for real API data
  cm doctor       Check cookie health + API connectivity
  cm help         Show this help

Monitor Controls:
  1 / 2 / 3       Show last 3 / 5 / 10 sessions
  T               Open inline terminal
  Q               Quit

Setup:
  Run 'cm setup' to paste your Claude.ai cookie.
  This enables real 5-hour and weekly reset countdown.

  Cookie source: Claude.ai → DevTools → Network →
  Click any API request → Copy 'cookie' header

GitHub: https://github.com/AssiamahS/menupapi-cm
""")
            return

        if cmd in ("version", "--version", "-v"):
            from menupapi_cm import __version__
            print(f"menupapi-cm {__version__}")
            return

        print(f"Unknown command: {cmd}")
        print("Run 'cm help' for usage.")
        return

    run_monitor()


if __name__ == "__main__":
    main()
