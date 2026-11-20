"""Playback timeline: pure logic, no Qt, no wall clock.

The UI owns the timer and calls ``advance(dt)``; everything else (looping,
speed, scrubbing, stepping, A-B loop range, frame lookup) lives here so it is
testable. Time is in seconds relative to the first frame (0 .. duration).
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np

MIN_SPEED, MAX_SPEED = 0.1, 4.0


class PlaybackTimeline:
    def __init__(self, timestamps: Sequence[float], loop: bool = True, speed: float = 1.0,
                 playing: bool = True):
        ts = np.asarray(timestamps, dtype=np.float64)
        if ts.size:
            ts = np.maximum.accumulate(ts - ts[0])   # relative + monotonic
        self.timestamps = ts
        self.loop = loop
        self.playing = playing and ts.size > 0
        self.reverse = False
        self._speed = 1.0
        self.set_speed(speed)
        self.time = 0.0
        self._range: Optional[Tuple[float, float]] = None

    # ------------------------------------------------------------------ state
    @property
    def n_frames(self) -> int:
        return int(self.timestamps.size)

    @property
    def duration(self) -> float:
        return float(self.timestamps[-1]) if self.n_frames else 0.0

    @property
    def speed(self) -> float:
        return self._speed

    def set_speed(self, speed: float) -> float:
        """Clamped to [0.1, 4]; direction is controlled by ``reverse``."""
        self._speed = float(min(MAX_SPEED, max(MIN_SPEED, abs(speed))))
        return self._speed

    @property
    def loop_range(self) -> Tuple[float, float]:
        return self._range if self._range else (0.0, self.duration)

    def set_loop_range(self, start: Optional[float], end: Optional[float]) -> None:
        """A-B loop; ``None, None`` clears it. Values are clamped and ordered."""
        if start is None or end is None:
            self._range = None
            return
        a, b = sorted((min(max(start, 0.0), self.duration), min(max(end, 0.0), self.duration)))
        self._range = (a, b) if b > a else None
        self.time = min(max(self.time, self.loop_range[0]), self.loop_range[1])

    # ---------------------------------------------------------------- control
    def toggle(self) -> bool:
        if self.n_frames == 0:
            return False
        if not self.playing:
            a, b = self.loop_range
            edge = a if self.reverse else b
            if not self.loop and self.time == edge:   # restart after reaching the end
                self.time = b if self.reverse else a
        self.playing = not self.playing
        return self.playing

    def advance(self, dt: float) -> int:
        """Move by ``dt`` wall seconds (scaled by speed). Returns current frame index."""
        if self.playing and self.n_frames:
            a, b = self.loop_range
            t = self.time + dt * self._speed * (-1.0 if self.reverse else 1.0)
            if self.loop:
                span = b - a
                t = a + ((t - a) % span) if span > 0 else a
            else:
                if t >= b or t <= a:
                    self.playing = False
                t = min(max(t, a), b)
            self.time = t
        return self.index

    def seek(self, t: float) -> int:
        self.time = min(max(float(t), 0.0), self.duration)
        return self.index

    def seek_frame(self, i: int) -> int:
        if self.n_frames == 0:
            return 0
        i = min(max(int(i), 0), self.n_frames - 1)
        self.time = float(self.timestamps[i])
        return i

    def step(self, delta: int = 1) -> int:
        """Single-frame step; pauses playback (like every editor)."""
        self.playing = False
        return self.seek_frame(self.index + delta)

    # ----------------------------------------------------------------- lookup
    @property
    def index(self) -> int:
        """Frame whose timestamp is the latest one <= current time."""
        if self.n_frames == 0:
            return 0
        return int(max(0, np.searchsorted(self.timestamps, self.time, side="right") - 1))

    @property
    def position(self) -> Tuple[int, int, float]:
        """(frame i, next frame j, alpha in [0,1]) for optional interpolation."""
        i = self.index
        if i >= self.n_frames - 1:
            return i, i, 0.0
        t0, t1 = self.timestamps[i], self.timestamps[i + 1]
        return i, i + 1, float((self.time - t0) / (t1 - t0)) if t1 > t0 else 0.0
