"""Which move came out, from how the screen in front of the player changes.

For each move the tool first performs a clean reference input a few times and
stores the average "change signature": per 33 ms bin after the button, the mean
absolute pixel change in a 3x3 grid of the action area. A trial is classified
as the move whose signature is closest (cosine similarity). The super freeze,
a rising uppercut, a travelling fireball and a spinning kick all leave clearly
different signatures; a light punch barely changes anything.
"""
from __future__ import annotations

import os

import numpy as np

from .core import DATA_DIR

BINS, BIN_MS, GRID = 30, 33.3, 3
MOVES = ["normal", "hado", "dp", "tatsu", "sa"]
LABEL = {"normal": "通常技", "hado": "波動拳", "dp": "昇竜拳", "tatsu": "竜巻旋風脚", "sa": "真空波動拳"}


def signature(frames: list[tuple[float, np.ndarray]], t_button: float) -> np.ndarray:
    base = None
    for t, g in frames:
        if t <= t_button:
            base = g
    if base is None and frames:
        base = frames[0][1]
    sig = np.zeros((BINS, GRID, GRID), dtype=np.float32)
    cnt = np.zeros(BINS)
    for t, g in frames:
        b = int((t - t_button) // BIN_MS)
        if b < 0 or b >= BINS:
            continue
        diff = np.abs(g.astype(np.float32) - base.astype(np.float32))
        h, w = diff.shape
        for i in range(GRID):
            for j in range(GRID):
                sig[b, i, j] += diff[i * h // GRID:(i + 1) * h // GRID, j * w // GRID:(j + 1) * w // GRID].mean()
        cnt[b] += 1
    cnt[cnt == 0] = 1
    sig /= cnt[:, None, None]
    return sig.ravel()


def model_path() -> str:
    return os.path.join(DATA_DIR, "outcome_model.npz")


def save_model(centroids: dict[str, np.ndarray]) -> None:
    np.savez(model_path(), **centroids)


def load_model() -> dict[str, np.ndarray]:
    z = np.load(model_path())
    return {k: z[k] for k in z.files}


def classify(sig: np.ndarray, centroids: dict[str, np.ndarray]) -> tuple[str, float]:
    def cos(a, b):
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    scores = {k: cos(sig, c) for k, c in centroids.items()}
    best = max(scores, key=scores.get)
    return best, scores[best]
