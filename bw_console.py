"""English-only console messages for System Console / headless scripts."""

from __future__ import annotations

import sys


def info_en(message: str) -> None:
    print(f"[BW] {message}", flush=True)
    sys.stdout.flush()
