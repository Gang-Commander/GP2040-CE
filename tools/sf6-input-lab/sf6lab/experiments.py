"""Experiments. Every trial starts at a random point in the 60 fps cycle so
results are averaged over the game's timing, and conditions are interleaved
(shuffled) so slow drift (CPU load etc.) affects all of them equally.
"""
from __future__ import annotations

import csv
import os
import random
import time

from .core import FRAME_MS, DATA_DIR, NUMPAD, U, D, L, R, now_ms
from .inject import Step

A_DURATIONS = list(range(1, 21)) + [25, 30]


def _csv(name: str) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.csv")


def _jitter(rng: random.Random) -> float:
    return rng.random() * FRAME_MS


def _seq_str(states: list[int]) -> str:
    return "".join(NUMPAD.get(s, "?") for s in states)


# ---------------------------------------------------------------------------
# A: how often a d-ms diagonal shows up in the input history (2 → 3(d) → 6)
# ---------------------------------------------------------------------------
def run_A(rig, n: int, seed: int = 1, out: str | None = None, progress=print) -> str:
    rng = random.Random(seed)
    plan = [d for d in A_DURATIONS for _ in range(n)]
    rng.shuffle(plan)
    path = out or _csv("A")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["exp", "trial", "diag_ms", "seen_seq", "diag_seen"])
        for i, d in enumerate(plan):
            rig.play([Step(0, 450 + _jitter(rng)), Step(D, 120), Step(D | R, d), Step(R, 120), Step(0, 400)])
            got = rig.read_attempt()
            w.writerow(["A", i, d, _seq_str(got), int((D | R) in got)])
            if i % 20 == 0:
                progress(f"  A {i + 1}/{len(plan)}  直近: 3を{d}ms → 入力履歴 {_seq_str(got) or '(読めず)'}")
    return path


# ---------------------------------------------------------------------------
# B: three directions inside one frame (2, 3, 6 for x ms each)
# ---------------------------------------------------------------------------
def run_B(rig, n: int, seed: int = 2, out: str | None = None, progress=print) -> str:
    rng = random.Random(seed)
    plan = [x for x in (3, 5) for _ in range(n)]
    rng.shuffle(plan)
    path = out or _csv("B")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["exp", "trial", "each_ms", "seen_seq"])
        for i, x in enumerate(plan):
            rig.play([Step(0, 450 + _jitter(rng)), Step(D, x), Step(D | R, x), Step(R, 150), Step(0, 400)])
            got = rig.read_attempt()
            w.writerow(["B", i, x, _seq_str(got)])
            if i % 20 == 0:
                progress(f"  B {i + 1}/{len(plan)}  直近: 各{x}ms → {_seq_str(got) or '(読めず)'}")
    return path


# ---------------------------------------------------------------------------
# C: input buffers. One element (or the wait before the button) is stretched
#    to g frames; the move should stop coming out past the buffer.
# ---------------------------------------------------------------------------
SHORT = 50.0  # ms for the other elements (3 frames, comfortably readable)


def c_case(case: str, g: int, attack: str) -> tuple[list[Step], str]:
    long = g * FRAME_MS  # exactly g frames long, so it is read as g frames
    if case.endswith("_btn"):
        # the button lands on the frame after the hold, so hold g-1 frames to
        # make the distance (last direction → button) exactly g frames
        long = (g - 1) * FRAME_MS
    P = (attack,)
    if case == "hado_gap":   # 2 → 3 held g frames → 6+P
        return [Step(D, SHORT), Step(D | R, long), Step(R, 30), Step(R, 80, P)], "hado"
    if case == "hado_btn":   # 2 → 3 → 6 held g frames → P
        return [Step(D, SHORT), Step(D | R, SHORT), Step(R, long), Step(R, 80, P)], "hado"
    if case == "tatsu_gap":  # 2 → 1 held g frames → 4+P
        return [Step(D, SHORT), Step(D | L, long), Step(L, 30), Step(L, 80, P)], "tatsu"
    if case == "dp_gap":     # 6 → 2 held g frames → 3+P
        return [Step(R, SHORT), Step(D, long), Step(D | R, 30), Step(D | R, 80, P)], "dp"
    if case == "dp_btn":     # 6 → 2 → 3 held g frames → P
        return [Step(R, SHORT), Step(D, SHORT), Step(D | R, long), Step(D | R, 80, P)], "dp"
    if case == "sa_gap":     # 236 → 2 held g frames → 36+P
        return [Step(D, SHORT), Step(D | R, SHORT), Step(R, SHORT), Step(D, long), Step(D | R, SHORT), Step(R, 30), Step(R, 80, P)], "sa"
    raise ValueError(case)


C_CASES = {
    "hado_gap": range(6, 16), "hado_btn": range(6, 16), "tatsu_gap": range(6, 16),
    "dp_gap": range(3, 12), "dp_btn": range(3, 12), "sa_gap": range(6, 16),
}


def run_C(rig, n: int, cfg, cases: list[str] | None = None, seed: int = 3, out: str | None = None, progress=print) -> str:
    rng = random.Random(seed)
    cases = cases or list(C_CASES)
    plan = [(c, g) for c in cases for g in C_CASES[c] for _ in range(n)]
    rng.shuffle(plan)
    path = out or _csv("C")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["exp", "trial", "case", "frames", "expected", "got", "score", "ok"])
        for i, (case, g) in enumerate(plan):
            steps, want = c_case(case, g, cfg.attack_button)
            rig.play([Step(0, 300 + _jitter(rng))])
            rig.start_recording()
            log = rig.play(steps + [Step(0, 1100)])
            t_button = next(t for t, _, b in log if b)
            got, score = rig.finish_recording(t_button)
            rig.play([Step(0, 50, (cfg.reset_button,)), Step(0, 900)])  # reset positions
            w.writerow(["C", i, case, g, want, got, f"{score:.3f}", int(got == want)])
            if i % 10 == 0:
                progress(f"  C {i + 1}/{len(plan)}  {case} {g}F → {got}")
    return path


# ---------------------------------------------------------------------------
# Reference inputs for learning what each move looks like on screen
# ---------------------------------------------------------------------------
def reference_steps(move: str, attack: str) -> list[Step]:
    P = (attack,)
    s = SHORT
    return {
        "normal": [Step(0, 30), Step(0, 80, P)],
        "hado": [Step(D, s), Step(D | R, s), Step(R, 30), Step(R, 80, P)],
        "dp": [Step(R, s), Step(D, s), Step(D | R, 30), Step(D | R, 80, P)],
        "tatsu": [Step(D, s), Step(D | L, s), Step(L, 30), Step(L, 80, P)],
        "sa": [Step(D, s), Step(D | R, s), Step(R, s), Step(D, s), Step(D | R, s), Step(R, 30), Step(R, 80, P)],
    }[move]
