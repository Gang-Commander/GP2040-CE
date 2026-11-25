"""Candidate models of how SF6 turns controller reads into frames, and the
motion matcher. Used for predictions (report) and by the simulator (self-test).

Models (what one frame's input is):
  single : one read per frame at a fixed point in the frame (SF5-style)
  strict : 3 reads at random moments, ONE of them (random) is used
  queue  : 3 reads at random moments; every read that differs from the last
           registered state is queued, and each frame consumes one queued state
           ("a polled input is (mostly) guaranteed to be used for a frame")
"""
from __future__ import annotations

import random

from .core import FRAME_MS, U, D, L, R, mirror

MODELS = ["single", "strict", "queue"]
MODEL_LABEL = {
    "single": "1フレーム1回（スト5方式）",
    "strict": "3回読み・1つだけランダムに使う（厳しい想定）",
    "queue": "3回読み・拾った入力は順に全部使う（甘い想定）",
}


def state_at(timeline: list[tuple[float, int]], t: float) -> int:
    s = 0
    for tt, st in timeline:
        if tt > t:
            break
        s = st
    return s


def frames_from(timeline: list[tuple[float, int]], model: str, t0: float, t1: float, rng: random.Random) -> list[int]:
    """Per-frame registered states between t0 and t1 under `model`."""
    out: list[int] = []
    phase = rng.random() * FRAME_MS
    queue: list[int] = []
    last = state_at(timeline, t0)
    k = 0
    while True:
        start = t0 + phase + k * FRAME_MS
        if start > t1:
            break
        if model == "single":
            out.append(state_at(timeline, start + FRAME_MS * 0.5))
        else:
            reads = sorted(start + rng.random() * FRAME_MS for _ in range(3))
            states = [state_at(timeline, t) for t in reads]
            if model == "strict":
                out.append(states[rng.randrange(3)])
            else:  # queue
                for st in states:
                    if st != (queue[-1] if queue else last):
                        queue.append(st)
                if queue:
                    last = queue.pop(0)
                out.append(last)
        k += 1
    return out


def runs(frames: list[int]) -> list[tuple[int, int, int]]:
    """(state, first_frame, last_frame) per run."""
    r: list[list[int]] = []
    for i, s in enumerate(frames):
        if r and r[-1][0] == s:
            r[-1][2] = i
        else:
            r.append([s, i, i])
    return [tuple(x) for x in r]


# ---------------------------------------------------------------------------
# Motion matcher, scanning backwards from the button frame the way SF games
# do: the last element must be within `buf` frames of the button (0..buf), each
# earlier element within `buf` frames before the frame where the next one was
# found (1..buf), and on a different state than that frame (so 333 is not 323).
# Optional elements may be skipped.
# ---------------------------------------------------------------------------
def hasF(s): return bool(s & R) and not (s & L)
def hasDn(s): return bool(s & D)
def eq(x): return lambda s: s == x


MOTIONS = {
    # name: (elements [(predicate, optional)], buffer frames, extra frames for the first gap)
    "sa":    ([(eq(D), False), (eq(D | R), True), (eq(R), False), (eq(D), False), (eq(D | R), False), (eq(R), False)], 10, 2),
    "dp":    ([(hasF, False), (hasDn, False), (hasF, False)], 7, 0),
    "hado":  ([(eq(D), False), (eq(D | R), False), (eq(R), False)], 11, 0),
    "tatsu": ([(eq(D), False), (eq(D | L), False), (eq(L), False)], 11, 0),
}
PRIORITY = ["sa", "dp", "hado", "tatsu"]


def matches(frames: list[int], elems, buf: int, first_extra: int = 0) -> bool:
    pos = len(frames) - 1          # button frame
    first = True
    for k in range(len(elems) - 1, -1, -1):
        pred, optional = elems[k]
        lim = buf + (first_extra if k == 0 else 0)
        lo = max(0, pos - lim)
        hi = pos if first else pos - 1
        found = -1
        for i in range(hi, lo - 1, -1):
            if pred(frames[i]) and (first or frames[i] != frames[pos]):
                found = i
                break
        if found < 0:
            if optional:
                continue
            return False
        pos, first = found, False
    return True


def detect(frames_facing_right: list[int], buffers: dict[str, int] | None = None) -> str:
    for name in PRIORITY:
        elems, buf, extra = MOTIONS[name]
        if buffers and name in buffers:
            buf = buffers[name]
        if matches(frames_facing_right[-60:], elems, buf, extra):
            return name
    return "normal"


# ---------------------------------------------------------------------------
# Prediction for experiment A: P(the d-ms diagonal shows up in the history)
# ---------------------------------------------------------------------------
def predict_A(d_ms: float, model: str, n: int = 4000, seed: int = 1) -> float:
    rng = random.Random(seed)
    hit = 0
    for _ in range(n):
        t2 = 100.0
        tl = [(0.0, 0), (t2, D), (t2 + 120, D | R), (t2 + 120 + d_ms, R), (t2 + 240 + d_ms, 0)]
        fr = frames_from(tl, model, 0.0, t2 + 400 + d_ms, rng)
        if (D | R) in fr:
            hit += 1
    return hit / n
