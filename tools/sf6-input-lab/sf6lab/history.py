"""Reading the training-mode input history from the screen.

Geometry comes from the one-time setup (newest row icon + step to the next row).
Icon templates are learned automatically: the tool holds each direction with the
virtual pad and photographs the newest row, so no manual labelling is needed.
"""
from __future__ import annotations

import os

import numpy as np

from .core import Config, DATA_DIR, NUMPAD, U, D, L, R
from .inject import Injector, Step, play

MARGIN = 4  # px of slack around each icon so small offsets still match
ALL_STATES = [0, U, D, L, R, U | L, U | R, D | L, D | R]


def row_rect(cfg: Config, i: int, margin: int = 0) -> list[int]:
    x, y, w, h = cfg.icon_rect
    dx, dy = cfg.row_step
    return [x + dx * i - margin, y + dy * i - margin, w + 2 * margin, h + 2 * margin]


def templates_path() -> str:
    return os.path.join(DATA_DIR, "icons.npz")


def learn_templates(cfg: Config, screen, inj: Injector) -> dict[int, np.ndarray]:
    """Hold each direction for 0.5 s and photograph the newest history row."""
    tpl = {}
    for s in ALL_STATES:
        play(inj, [Step(0, 300), Step(s, 500)])
        tpl[s] = screen.gray(screen.grab(row_rect(cfg, 0)))
        print(f"  {NUMPAD[s]} を記録")
    play(inj, [Step(0, 300)])
    np.savez(templates_path(), **{str(k): v for k, v in tpl.items()})
    return tpl


def load_templates() -> dict[int, np.ndarray]:
    z = np.load(templates_path())
    return {int(k): z[k] for k in z.files}


def classify(crop: np.ndarray, tpl: dict[int, np.ndarray], threshold: float) -> tuple[int | None, float]:
    """Best-matching state for one (margin-padded) row crop; None if nothing matches."""
    import cv2
    best, best_score = None, -1.0
    for s, t in tpl.items():
        if t.std() < 1e-3:  # blank template (e.g. neutral drawn as nothing)
            score = 1.0 - min(1.0, float(crop.std()) / 20.0)
        else:
            score = float(cv2.matchTemplate(crop, t, cv2.TM_CCOEFF_NORMED).max())
        if score > best_score:
            best, best_score = s, score
    return (best if best_score >= threshold else None), best_score


def read_rows(cfg: Config, screen, tpl: dict[int, np.ndarray]) -> list[int | None]:
    """States of the history rows, newest first."""
    out = []
    for i in range(cfg.rows):
        crop = screen.gray(screen.grab(row_rect(cfg, i, MARGIN)))
        out.append(classify(crop, tpl, cfg.match_threshold)[0])
    return out


def last_attempt(rows_newest_first: list[int | None]) -> list[int]:
    """The directions of the last attempt in time order: skip the current
    neutral row(s), then take rows until the neutral that preceded the attempt."""
    i = 0
    while i < len(rows_newest_first) and rows_newest_first[i] == 0:
        i += 1
    got = []
    while i < len(rows_newest_first) and rows_newest_first[i] not in (0, None):
        got.append(rows_newest_first[i])
        i += 1
    return list(reversed(got))
