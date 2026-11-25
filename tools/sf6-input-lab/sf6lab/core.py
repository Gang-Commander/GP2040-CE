"""Shared definitions: directions, timing, config."""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict

# Direction bits (same as GP2040-CE): 1=UP 2=DOWN 4=LEFT 8=RIGHT
U, D, L, R = 1, 2, 4, 8
NUMPAD = {0: "5", U: "8", D: "2", L: "4", R: "6", U | L: "7", U | R: "9", D | L: "1", D | R: "3"}
FROM_NUMPAD = {v: k for k, v in NUMPAD.items()}
FRAME_MS = 1000.0 / 60.0


def mirror(s: int) -> int:
    return (s & (U | D)) | (R if s & L else 0) | (L if s & R else 0)


def seq(text: str) -> list[int]:
    """'236' -> [D, D|R, R]"""
    return [FROM_NUMPAD[c] for c in text]


# ---------------------------------------------------------------------------
# Precise clock. time.sleep() on Windows is ~1-15 ms coarse, so we sleep until
# ~2 ms before the target and then busy-wait on perf_counter (sub-0.1 ms).
# ---------------------------------------------------------------------------
class RealClock:
    def now(self) -> float:
        return time.perf_counter_ns() / 1e6

    def wait_until(self, t_ms: float) -> None:
        while True:
            remaining = t_ms - self.now()
            if remaining <= 0:
                return
            if remaining > 2.5:
                time.sleep((remaining - 2.0) / 1000.0)
            # else: spin


class VirtualClock:
    """Used by the simulator: time only moves when someone waits."""
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def wait_until(self, t_ms: float) -> None:
        self.t = max(self.t, t_ms)


clock = RealClock()


def use_clock(c) -> None:
    global clock
    clock = c


def now_ms() -> float:
    return clock.now()


def wait_until(t_ms: float) -> None:
    clock.wait_until(t_ms)


def boost_timer_resolution() -> None:
    """Windows: 1 ms scheduler tick + high process priority. No-op elsewhere."""
    if sys.platform != "win32":
        return
    import ctypes
    ctypes.windll.winmm.timeBeginPeriod(1)
    HIGH_PRIORITY_CLASS = 0x00000080
    ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), HIGH_PRIORITY_CLASS)


# ---------------------------------------------------------------------------
# Config (screen regions etc.), stored next to the script as JSON.
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HERE, "data")


@dataclass
class Config:
    # Input history: rectangle around the NEWEST row's direction icon (x, y, w, h)
    icon_rect: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    # Offset in pixels from the newest row to the next older row (x, y)
    row_step: list[int] = field(default_factory=lambda: [0, 0])
    rows: int = 10
    # Area in front of the player character, used to tell which move came out
    action_rect: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    # XInput buttons (vgamepad names without the XUSB_GAMEPAD_ prefix)
    attack_button: str = "X"          # Classic default: Light Punch = X / Square
    reset_button: str = "BACK"        # Training mode "reset position" (check your mapping)
    match_threshold: float = 0.6

    @staticmethod
    def path() -> str:
        return os.path.join(DATA_DIR, "config.json")

    @classmethod
    def load(cls) -> "Config":
        if os.path.exists(cls.path()):
            with open(cls.path(), encoding="utf-8") as f:
                return cls(**json.load(f))
        return cls()

    def save(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(self.path(), "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
