"""Tests for AudioVisualizerWorker (divoom_gui/audio_visualizer.py).

The class scans real audio hardware via pyaudio inside a background thread
(`_run`). We inject a fake `pyaudio.PyAudio` (patched at the exact
`pyaudio.PyAudio` call site — only the real device/stream I/O is faked) so the
device-scan and FFT/level-computation logic runs for real against canned
sample buffers, without touching real hardware. numpy is real (pure, no
hardware dependency) — only the audio backend is faked.

pyaudio is an optional dep (needs the native PortAudio lib) and is absent in
CI, so skip the whole module when it can't be imported — the tests monkeypatch
`pyaudio.PyAudio`, which requires the module to exist.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pyaudio")

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from divoom_gui.audio_visualizer import AudioVisualizerWorker  # noqa: E402

CHUNK = 512


def _sine_chunk(n=CHUNK, freq=440.0, rate=44100, amp=8000):
    t = np.arange(n)
    samples = (amp * np.sin(2 * np.pi * freq * t / rate)).astype(np.int16)
    return samples.tobytes()


class FakeStream:
    def __init__(self, reads):
        # reads: list of callables/values consumed one per .read() call
        self._reads = list(reads)
        self.stop_calls = 0
        self.close_calls = 0
        self.stop_stream_raises = False
        self.close_raises = False

    def read(self, chunk, exception_on_overflow=False):
        item = self._reads.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item()
        return item

    def stop_stream(self):
        self.stop_calls += 1
        if self.stop_stream_raises:
            raise RuntimeError("stop_stream boom")

    def close(self):
        self.close_calls += 1
        if self.close_raises:
            raise RuntimeError("close boom")


class FakePyAudio:
    """Fake pyaudio.PyAudio(); configure devices via class-level hooks set per-test."""
    devices = []  # list of dicts with "name"
    open_stream = None  # FakeStream to return from .open()
    open_raises = None
    device_count_raises = False
    device_info_raises_at = None  # index that raises when queried
    terminate_calls = []

    def __init__(self):
        pass

    def get_device_count(self):
        if FakePyAudio.device_count_raises:
            raise RuntimeError("device count boom")
        return len(FakePyAudio.devices)

    def get_device_info_by_index(self, i):
        if FakePyAudio.device_info_raises_at == i:
            raise RuntimeError(f"device info boom at {i}")
        return FakePyAudio.devices[i]

    def open(self, **kwargs):
        if FakePyAudio.open_raises:
            raise FakePyAudio.open_raises
        return FakePyAudio.open_stream

    def terminate(self):
        FakePyAudio.terminate_calls.append(True)


@pytest.fixture(autouse=True)
def _reset_fake_pyaudio():
    FakePyAudio.devices = []
    FakePyAudio.open_stream = None
    FakePyAudio.open_raises = None
    FakePyAudio.device_count_raises = False
    FakePyAudio.device_info_raises_at = None
    FakePyAudio.terminate_calls = []
    yield


def test_init_state():
    w = AudioVisualizerWorker()
    assert w.active is False
    assert w.levels == [0.0] * 10
    assert w.loopback_active is False
    assert w.device_name == "None"
    assert w.peak_history == 1000.0
    assert w.thread is None
    assert w.stream is None
    assert w.p is None


def test_stop_without_start_is_a_noop():
    w = AudioVisualizerWorker()
    w.stop()  # must not raise
    assert w.active is False


def test_start_sets_active_and_spawns_thread(monkeypatch):
    w = AudioVisualizerWorker()
    calls = []

    def fake_run(self):
        calls.append(1)
        time.sleep(0.05)

    monkeypatch.setattr(AudioVisualizerWorker, "_run", fake_run)
    w.start()
    assert w.active is True
    assert w.thread is not None
    thread_first = w.thread
    # Calling start() again while active must not spawn a second thread.
    w.start()
    assert w.thread is thread_first
    w.thread.join(timeout=1)
    w.stop()
    assert calls == [1]


def test_run_no_loopback_device_found(monkeypatch):
    """No device name matches a loopback keyword -> visualizer disables itself
    and returns early (lines ~78-82), without ever calling p.open()."""
    monkeypatch.setattr("pyaudio.PyAudio", FakePyAudio)
    FakePyAudio.devices = [{"name": "Built-in Microphone"}, {"name": "Built-in Output"}]

    w = AudioVisualizerWorker()
    w._run()  # run synchronously — no real device I/O since PyAudio is faked

    assert w.loopback_active is False
    assert w.device_name == "None"


def test_run_device_scan_exception_falls_back_to_no_device(monkeypatch):
    """get_device_count() raising is caught; device_index stays None -> same
    early-return path as 'no device found' (covers the outer except at ~75-76)."""
    monkeypatch.setattr("pyaudio.PyAudio", FakePyAudio)
    FakePyAudio.device_count_raises = True

    w = AudioVisualizerWorker()
    w._run()

    assert w.loopback_active is False
    assert w.device_name == "None"


def test_run_skips_device_that_raises_then_finds_loopback(monkeypatch):
    """One device's get_device_info_by_index raises (inner except at ~73-74);
    scanning continues and finds the loopback device at the next index."""
    monkeypatch.setattr("pyaudio.PyAudio", FakePyAudio)
    FakePyAudio.devices = [{"name": "raises"}, {"name": "BlackHole 2ch"}]
    FakePyAudio.device_info_raises_at = 0
    FakePyAudio.open_raises = RuntimeError("stop here")  # short-circuit after scan

    w = AudioVisualizerWorker()
    w._run()

    assert w.loopback_active is True
    assert w.device_name == "BlackHole 2ch"


def test_run_stream_open_failure_is_caught(monkeypatch):
    """p.open() raising is caught and logged; _run returns cleanly (~98-100)."""
    monkeypatch.setattr("pyaudio.PyAudio", FakePyAudio)
    FakePyAudio.devices = [{"name": "Loopback Audio"}]
    FakePyAudio.open_raises = OSError("device busy")

    w = AudioVisualizerWorker()
    w._run()  # must not raise

    assert w.loopback_active is True
    assert w.device_name == "Loopback Audio"
    assert w.stream is None


def test_run_full_capture_loop_computes_levels(monkeypatch):
    """Happy path: loopback found, stream opens, the FFT/level-computation loop
    runs over canned sample buffers (a short read then a full-CHUNK read),
    including one transient read error (exercises the except/backoff at
    ~149-150), and updates self.levels / self.peak_history for real."""
    monkeypatch.setattr("pyaudio.PyAudio", FakePyAudio)
    FakePyAudio.devices = [{"name": "SoundSource Loopback"}]

    w = AudioVisualizerWorker()

    def short_read():
        # len(samples) != CHUNK -> exercises the non-hoisted np.hanning() path.
        return _sine_chunk(n=256)

    def final_read():
        w.active = False  # let the while loop exit after this iteration
        return _sine_chunk(n=CHUNK, freq=220.0, amp=12000)

    stream = FakeStream(reads=[
        RuntimeError("transient overflow"),  # -> except: time.sleep(0.05)
        b"",  # falsy read -> `if not data: continue` (line ~126)
        short_read,
        final_read,
    ])
    FakePyAudio.open_stream = stream

    w.active = True
    w._run()  # runs to completion synchronously (active flips False mid-loop)

    assert w.loopback_active is True
    assert w.device_name == "SoundSource Loopback"
    assert len(w.levels) == 10
    assert all(0.0 <= lvl <= 100.0 for lvl in w.levels)
    assert any(lvl > 0.0 for lvl in w.levels), "expected non-zero energy from the sine input"
    assert w.peak_history != 1000.0, "peak AGC should have tracked away from the initial value"


def test_stop_closes_stream_and_terminates_pyaudio(monkeypatch):
    monkeypatch.setattr("pyaudio.PyAudio", FakePyAudio)
    FakePyAudio.devices = [{"name": "BlackHole"}]

    w = AudioVisualizerWorker()

    def one_read():
        w.active = False
        return _sine_chunk()

    stream = FakeStream(reads=[one_read])
    FakePyAudio.open_stream = stream
    w.active = True
    w._run()

    assert w.stream is stream
    w.stop()
    assert stream.stop_calls == 1
    assert stream.close_calls == 1
    assert FakePyAudio.terminate_calls == [True]
    assert w.stream is None
    assert w.p is None


def test_stop_swallows_stream_and_terminate_exceptions(monkeypatch):
    """stop() must not raise even if stream.stop_stream()/close() or
    p.terminate() blow up (both wrapped in bare except: pass)."""
    monkeypatch.setattr("pyaudio.PyAudio", FakePyAudio)
    FakePyAudio.devices = [{"name": "BlackHole"}]

    w = AudioVisualizerWorker()

    def one_read():
        w.active = False
        return _sine_chunk()

    stream = FakeStream(reads=[one_read])
    stream.stop_stream_raises = True
    stream.close_raises = True
    FakePyAudio.open_stream = stream
    w.active = True
    w._run()

    class RaisingTerminate:
        pass

    # monkeypatch terminate() on the live PyAudio instance to raise
    w.p.terminate = lambda: (_ for _ in ()).throw(RuntimeError("terminate boom"))

    w.stop()  # must not raise
    assert w.stream is None
    assert w.p is None
