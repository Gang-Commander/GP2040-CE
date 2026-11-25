"""Virtual Xbox 360 controller (ViGEmBus via vgamepad) with a precise scheduler."""
from __future__ import annotations

from dataclasses import dataclass

from .core import U, D, L, R, now_ms, wait_until


@dataclass
class Step:
    """Hold `dirs` (+ `buttons`) for `ms` milliseconds."""
    dirs: int
    ms: float
    buttons: tuple[str, ...] = ()


class Injector:
    """Interface. set() applies a state and returns the time (ms) it was sent."""

    def set(self, dirs: int, buttons: tuple[str, ...] = ()) -> float:
        raise NotImplementedError

    def close(self) -> None:
        pass


class VGamepadInjector(Injector):
    def __init__(self) -> None:
        try:
            import vgamepad as vg  # Windows only; installs/uses ViGEmBus
        except ImportError as e:  # pragma: no cover - Windows only
            raise SystemExit("vgamepad が見つかりません。README の手順で `pip install vgamepad` を実行してください。") from e
        self.vg = vg
        self.pad = vg.VX360Gamepad()
        B = vg.XUSB_BUTTON
        self.dir_bits = {U: B.XUSB_GAMEPAD_DPAD_UP, D: B.XUSB_GAMEPAD_DPAD_DOWN,
                         L: B.XUSB_GAMEPAD_DPAD_LEFT, R: B.XUSB_GAMEPAD_DPAD_RIGHT}
        self.set(0)

    def _button(self, name: str) -> int:
        return int(getattr(self.vg.XUSB_BUTTON, "XUSB_GAMEPAD_" + name))

    def set(self, dirs: int, buttons: tuple[str, ...] = ()) -> float:
        mask = 0
        for bit, b in self.dir_bits.items():
            if dirs & bit:
                mask |= int(b)
        for name in buttons:
            mask |= self._button(name)
        # Write the whole report at once so directions and buttons change together.
        self.pad.report.wButtons = mask
        self.pad.update()
        return now_ms()

    def close(self) -> None:  # pragma: no cover - Windows only
        self.set(0)


def play(inj: Injector, steps: list[Step], start_ms: float | None = None) -> list[tuple[float, int, tuple[str, ...]]]:
    """Play steps back to back with precise timing. Returns (sent_ms, dirs, buttons) per step."""
    t = start_ms if start_ms is not None else now_ms() + 5
    log = []
    for st in steps:
        wait_until(t)
        sent = inj.set(st.dirs, st.buttons)
        log.append((sent, st.dirs, st.buttons))
        t += st.ms
    wait_until(t)
    return log
