"""Keep Windows out of modern standby while the experiment queue runs.

The first B1 simulation took 65 minutes of wall clock for 375 seconds of CPU:
the machine entered modern standby at 20:25 and left it at 21:25, and the run
simply stopped for the hour in between.  Kernel-Power events 506/507 in the
System log are the record of it.  Over an 80-run queue that is the difference
between finishing overnight and not finishing at all.

This asks Windows not to idle-sleep, using the documented mechanism rather than
by changing the user's power plan, so nothing has to be undone afterwards: the
request lives only as long as this process and is released when it exits.  The
display is deliberately not held awake -- the screen may still switch off.

It stops on its own when the queue writes its finished marker, or after
``--max-hours``, whichever comes first, so a forgotten instance cannot hold the
machine awake indefinitely.

Usage:
    python keep_awake.py --log results/all.log --until "ALL EXPERIMENTS FINISHED"
"""
from __future__ import annotations

import argparse
import ctypes
import time
from pathlib import Path

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=Path("results/all.log"))
    parser.add_argument("--until", default="ALL EXPERIMENTS FINISHED")
    parser.add_argument("--max-hours", type=float, default=12.0)
    args = parser.parse_args()

    kernel32 = ctypes.windll.kernel32
    if not kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
        raise SystemExit("SetThreadExecutionState failed")
    print(f"holding the system awake until {args.log} contains "
          f"{args.until!r} (at most {args.max_hours} h)", flush=True)

    deadline = time.time() + args.max_hours * 3600
    try:
        while time.time() < deadline:
            try:
                if args.until in args.log.read_text(encoding="utf-8", errors="ignore"):
                    print("marker found; releasing", flush=True)
                    return 0
            except FileNotFoundError:
                pass
            time.sleep(30)
        print("max-hours reached; releasing", flush=True)
        return 0
    finally:
        # ES_CONTINUOUS on its own clears the request.
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)


if __name__ == "__main__":
    raise SystemExit(main())
