"""Screen capture (mss) and the one-time region setup (OpenCV selectROI)."""
from __future__ import annotations

import threading

import numpy as np

from .core import now_ms


class Screen:
    def __init__(self) -> None:
        try:
            import mss
        except ImportError as e:  # pragma: no cover
            raise SystemExit("mss が見つかりません。README の手順で `pip install mss` を実行してください。") from e
        self.mss = mss.mss()

    def grab(self, rect: list[int] | None = None) -> np.ndarray:
        """Grayscale image of rect (x, y, w, h), or the whole primary monitor."""
        if rect is None:
            mon = self.mss.monitors[1]
        else:
            x, y, w, h = rect
            mon = {"left": x, "top": y, "width": w, "height": h}
        img = np.asarray(self.mss.grab(mon))[:, :, :3]
        return img[:, :, ::-1].copy()  # BGRA -> RGB

    @staticmethod
    def gray(img: np.ndarray) -> np.ndarray:
        import cv2
        return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


class Recorder:
    """Grabs one region as fast as possible in a background thread."""

    def __init__(self, rect: list[int], scale: float = 0.25) -> None:
        self.rect, self.scale = rect, scale
        self.frames: list[tuple[float, np.ndarray]] = []
        self._stop = threading.Event()
        self._th: threading.Thread | None = None

    def _run(self) -> None:
        import cv2
        import mss
        sct = mss.mss()  # mss objects are per-thread
        x, y, w, h = self.rect
        mon = {"left": x, "top": y, "width": w, "height": h}
        while not self._stop.is_set():
            img = np.asarray(sct.grab(mon))[:, :, :3]
            t = now_ms()
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            g = cv2.resize(g, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
            self.frames.append((t, g))

    def start(self) -> "Recorder":
        self.frames = []
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()
        return self

    def stop(self) -> list[tuple[float, np.ndarray]]:
        self._stop.set()
        if self._th:
            self._th.join()
        return self.frames


def select_rect(img: np.ndarray, title: str) -> list[int]:
    """Let the user drag a rectangle on img. Returns [x, y, w, h]."""
    import cv2
    print(f"  → 「{title}」をマウスで囲み、Enter で確定（やり直しは c）")
    r = cv2.selectROI(title, img[:, :, ::-1], showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(title)
    return [int(v) for v in r]
