"""The test rig: something that takes inputs and tells us what the game saw.

RealRig  : virtual pad + screen reading (the real SF6 on Windows)
SimRig   : a simulated game following one of the candidate models — used to
           check that the experiments and the report recover a known answer.
"""
from __future__ import annotations

import random

from . import core
from .core import Config
from .inject import Injector, Step, play
from . import models


class Rig:
    inj: Injector

    def play(self, steps: list[Step]):
        return play(self.inj, steps)

    def read_attempt(self) -> list[int]:
        raise NotImplementedError

    def start_recording(self) -> None:
        pass

    def finish_recording(self, t_button: float) -> tuple[str, float]:
        raise NotImplementedError


class RealRig(Rig):
    def __init__(self, cfg: Config, need_history: bool = True, need_outcome: bool = False) -> None:
        from .inject import VGamepadInjector
        from .screen import Screen
        from . import history, outcome
        core.boost_timer_resolution()
        self.cfg, self.history, self.outcome = cfg, history, outcome
        self.inj = VGamepadInjector()
        self.screen = Screen()
        self.tpl = history.load_templates() if need_history else None
        self.centroids = outcome.load_model() if need_outcome else None
        self.rec = None

    def read_attempt(self) -> list[int]:
        return self.history.last_attempt(self.history.read_rows(self.cfg, self.screen, self.tpl))

    def start_recording(self) -> None:
        from .screen import Recorder
        self.rec = Recorder(self.cfg.action_rect).start()

    def finish_recording(self, t_button: float) -> tuple[str, float]:
        frames = self.rec.stop()
        sig = self.outcome.signature(frames, t_button)
        return self.outcome.classify(sig, self.centroids)


class _RecordingInjector(Injector):
    def __init__(self) -> None:
        self.timeline: list[tuple[float, int]] = [(0.0, 0)]
        self.presses: list[float] = []
        self._btn = False

    def set(self, dirs: int, buttons: tuple[str, ...] = ()) -> float:
        t = core.now_ms()
        if dirs != self.timeline[-1][1]:
            self.timeline.append((t, dirs))
        pressed = any(b != "BACK" for b in buttons)
        if pressed and not self._btn:
            self.presses.append(t)
        self._btn = pressed
        return t


class SimRig(Rig):
    def __init__(self, model: str, buffers: dict[str, int] | None = None, seed: int = 7) -> None:
        core.use_clock(core.VirtualClock())
        self.model, self.buffers = model, buffers
        self.rng = random.Random(seed)
        self.inj = _RecordingInjector()
        self._mark = 0.0

    def _frames(self, t1: float) -> list[int]:
        return models.frames_from(self.inj.timeline, self.model, self._mark, t1, self.rng)

    def read_attempt(self) -> list[int]:
        fr = self._frames(core.now_ms())
        self._mark = core.now_ms()
        hist = [s for s, _, _ in models.runs(fr)]
        return _strip(hist)

    def finish_recording(self, t_button: float) -> tuple[str, float]:
        fr = self._frames(t_button)  # up to the frame in which the button is pressed
        self._mark = core.now_ms()
        return models.detect(fr, self.buffers), 1.0


def _strip(hist_oldest_first: list[int]) -> list[int]:
    """Directions of the last non-neutral stretch (same as history.last_attempt)."""
    out: list[int] = []
    for s in reversed(hist_oldest_first):
        if s == 0:
            if out:
                break
            continue
        out.append(s)
    return list(reversed(out))
