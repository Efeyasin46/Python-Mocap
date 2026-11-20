import numpy as np
import pytest

from core.playback import MAX_SPEED, MIN_SPEED, PlaybackTimeline

TS = [10.0 + i / 10 for i in range(11)]   # 11 frames, 1.0 s, absolute start 10 s


def tl(**kw):
    return PlaybackTimeline(TS, **kw)


def test_times_are_relative_and_duration():
    t = tl()
    assert t.duration == pytest.approx(1.0) and t.n_frames == 11 and t.index == 0


def test_advance_and_index_lookup():
    t = tl()
    assert t.advance(0.25) == 2            # 0.25 s -> frame at 0.2
    i, j, a = t.position
    assert (i, j) == (2, 3) and a == pytest.approx(0.5)


def test_loop_wraps_without_snapping_to_zero():
    t = tl()
    t.advance(1.25)
    assert t.time == pytest.approx(0.25) and t.playing


def test_no_loop_stops_at_end_and_toggle_restarts():
    t = tl(loop=False)
    t.advance(5.0)
    assert not t.playing and t.time == pytest.approx(1.0) and t.index == 10
    assert t.toggle() is True and t.time == 0.0


def test_speed_clamped_and_applied():
    t = tl()
    assert t.set_speed(100) == MAX_SPEED and t.set_speed(0) == MIN_SPEED
    t.set_speed(2.0)
    t.advance(0.1)
    assert t.time == pytest.approx(0.2)


def test_reverse_loops_backwards():
    t = tl()
    t.reverse = True
    t.advance(0.1)
    assert t.time == pytest.approx(0.9)


def test_step_pauses_and_clamps():
    t = tl()
    assert t.step(1) == 1 and not t.playing
    assert t.step(-5) == 0 and t.step(99) == 10


def test_seek_clamps():
    t = tl()
    t.seek(-3); assert t.time == 0.0
    t.seek(9); assert t.time == pytest.approx(1.0)
    assert t.seek_frame(4) == 4 and t.time == pytest.approx(0.4)


def test_ab_loop_range():
    t = tl()
    t.set_loop_range(0.7, 0.3)                    # given backwards -> ordered
    assert t.loop_range == pytest.approx((0.3, 0.7)) and t.time == pytest.approx(0.3)
    t.advance(0.5)                                # 0.3 + 0.5 = 0.8 -> wraps inside 0.3..0.7
    assert 0.3 <= t.time <= 0.7 and t.time == pytest.approx(0.4)
    t.set_loop_range(None, None)
    assert t.loop_range == (0.0, pytest.approx(1.0))


def test_empty_timeline_is_safe():
    t = PlaybackTimeline([])
    assert t.n_frames == 0 and t.advance(1.0) == 0 and t.toggle() is False
    assert t.seek_frame(3) == 0 and t.position == (0, 0, 0.0) and not t.playing


def test_single_frame_and_duplicate_timestamps():
    assert PlaybackTimeline([5.0]).advance(1.0) == 0
    t = PlaybackTimeline([0, 0.1, 0.1, 0.2])
    t.seek(0.1)
    assert t.index == 2 and t.position[2] == pytest.approx(0.0)   # no divide-by-zero


def test_non_monotonic_timestamps_are_repaired():
    t = PlaybackTimeline([0, 0.2, 0.1, 0.3])
    assert (np.diff(t.timestamps) >= 0).all()
