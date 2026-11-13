"""Kill switch: stop all automated replies immediately, without a restart or deployment.

    python -m scripts.kill_switch on "reason for switching off"
    python -m scripts.kill_switch off
    python -m scripts.kill_switch status

While the switch is on, every ticket is still classified, searched and routed, but nothing is
auto-answered: tickets that would have been answered are escalated with their context packet,
and the decision log records the rule `kill_switch`. The pipeline checks the switch file on every
ticket, so the change takes effect from the next ticket processed, in the API and in the harness.

The switch is a file (KILL_SWITCH_FILE, default ./storage/KILL_SWITCH). Anyone with write access to
the deployment can operate it, including by hand: creating the file switches it on, deleting it
switches it off.
"""
from __future__ import annotations

import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.config import get_settings


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("on", "off", "status"):
        print(__doc__)
        return 2
    path = Path(get_settings().kill_switch_file)
    action = argv[0]

    if action == "on":
        reason = " ".join(argv[1:]) or "no reason given"
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path.write_text(f"switched on at {stamp} by {getpass.getuser()}: {reason}\n", encoding="utf-8")
        print(f"Kill switch ON. Automated replies stop from the next ticket. ({path})")
    elif action == "off":
        if path.exists():
            path.unlink()
            print("Kill switch OFF. Automated replies resume from the next ticket.")
        else:
            print("Kill switch was already off.")
    else:
        if path.exists():
            print(f"ON  - {path.read_text(encoding='utf-8').strip()}")
        else:
            print(f"OFF - no switch file at {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
