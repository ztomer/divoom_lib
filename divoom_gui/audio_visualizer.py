"""AudioVisualizerWorker — system-loopback capture + FFT for the EQ visualizer.

Split out of media_sync.py to keep it under 500 LOC (REVIEW §1). Pure helper; the
MediaSyncMixin imports it.
"""
import logging
import threading
import time  # used by the read-loop error backoff (was NameError → killed the thread)

logger = logging.getLogger("divoom_gui")


class AudioVisualizerWorker:
    """Helper worker to scan audio devices, capture system loopback/mic, and run FFT analysis."""
    def __init__(self):
        self.p = None
        self.stream = None
        self.active = False
        self.thread = None
        self.levels = [0.0] * 10
        self.loopback_active = False
        self.device_name = "None"
        self.peak_history = 1000.0

    def start(self):
        if self.active:
            return
        self.active = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.active = False
        if self.thread:
            self.thread.join(timeout=0.5)
            self.thread = None
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.p:
            try:
                self.p.terminate()
            except Exception:
                pass
            self.p = None

    def _run(self):
        import pyaudio
        import numpy as np
        
        self.p = pyaudio.PyAudio()
        
        # Scan devices to locate loopback driver (e.g. BlackHole, Loopback, Soundflower, SoundSource, ACE)
        device_index = None
        self.loopback_active = False
        self.device_name = "None"
        
        try:
            device_count = self.p.get_device_count()
            for i in range(device_count):
                try:
                    dev_info = self.p.get_device_info_by_index(i)
                    name = dev_info.get("name", "")
                    if any(k in name.lower() for k in ["blackhole", "loopback", "soundflower", "soundsource", "ace"]):
                        device_index = i
                        self.loopback_active = True
                        self.device_name = name
                        break
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Audio scan error: {e}")
            
        if device_index is None:
            logger.warning("No virtual loopback audio device detected (BlackHole, SoundSource, ACE, Loopback, etc.). Visualizer disabled to avoid microphone fallback.")
            self.loopback_active = False
            self.device_name = "None"
            return

        CHUNK = 512
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100
        
        try:
            self.stream = self.p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=CHUNK
            )
        except Exception as e:
            logger.error(f"Failed to open PyAudio stream on {self.device_name}: {e}")
            return

        logger.info(f"Audio Visualizer started on device {self.device_name} (Loopback={self.loopback_active})")
        
        ranges = [
            (1, 2),    # Sub-bass
            (2, 4),    # Bass
            (4, 7),    # Low-mid
            (7, 11),   # Mid
            (11, 16),  # Mid
            (16, 24),  # High-mid
            (24, 35),  # High-mid
            (35, 50),  # High
            (50, 75),  # High
            (75, 110)  # Presence/Brilliance
        ]

        # Hoist the Hann window out of the ~86 Hz capture loop — len(samples) is
        # CHUNK every normal iteration, so recomputing np.hanning(CHUNK) each frame
        # was pure wasted work. Fall back only for a rare short final read.
        window_full = np.hanning(CHUNK)

        while self.active:
            try:
                data = self.stream.read(CHUNK, exception_on_overflow=False)
                if not data:
                    continue

                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                if len(samples) == 0:  # pragma: no cover - defensive: unreachable given
                    continue          # non-empty `data` already passed `if not data` above

                window = window_full if len(samples) == CHUNK else np.hanning(len(samples))
                fft_data = np.fft.rfft(samples * window)
                fft_mag = np.abs(fft_data)
                
                new_levels = []
                for start, end in ranges:
                    val = np.mean(fft_mag[start:end]) if end <= len(fft_mag) else 0.0
                    new_levels.append(float(val))
                
                # Dynamic peak AGC tracking
                peak = max(new_levels)
                self.peak_history = 0.95 * self.peak_history + 0.05 * peak
                norm_factor = max(self.peak_history, 800.0)
                
                for i in range(10):
                    scaled = min(100.0, (new_levels[i] / norm_factor) * 100.0)
                    self.levels[i] = 0.6 * scaled + 0.4 * self.levels[i]
            except Exception:
                time.sleep(0.05)
