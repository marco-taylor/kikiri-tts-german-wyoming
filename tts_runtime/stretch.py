"""Persistent per-response native SoundTouch state, tempo only, no resampling."""

import ctypes
import os
import numpy as np


class Stretcher:
    def __init__(self, factor):
        self.factor = factor
        self.tempo = 1 / factor
        self.input_frames = 0
        self.output_frames = 0
        self.flushed = False
        self.lib = ctypes.CDLL(
            os.getenv("KIKIRI_SOUNDTOUCH_LIB", "/usr/local/lib/libkikiri_soundtouch.so")
        )
        pointer = ctypes.POINTER(ctypes.c_float)
        self.lib.st_create.argtypes = [ctypes.c_double]
        self.lib.st_create.restype = ctypes.c_void_p
        self.lib.st_put.argtypes = [ctypes.c_void_p, pointer, ctypes.c_uint]
        self.lib.st_put.restype = ctypes.c_int
        self.lib.st_receive.argtypes = [ctypes.c_void_p, pointer, ctypes.c_uint]
        self.lib.st_receive.restype = ctypes.c_uint
        self.lib.st_flush.argtypes = [ctypes.c_void_p]
        self.lib.st_flush.restype = ctypes.c_int
        self.lib.st_destroy.argtypes = [ctypes.c_void_p]
        self.lib.st_destroy.restype = None
        self.lib.st_error.restype = ctypes.c_char_p
        self.handle = self.lib.st_create(self.tempo)
        if not self.handle:
            raise RuntimeError(self.lib.st_error().decode())
        self.buffer = np.empty(960, dtype=np.float32)

    def drain(self):
        while True:
            count = self.lib.st_receive(
                self.handle,
                self.buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                len(self.buffer),
            )
            if not count:
                return
            self.output_frames += count
            yield (
                np.clip(
                    np.floor(self.buffer[:count].astype(np.float64) * 32768),
                    -32768,
                    32767,
                )
                .astype("<i2")
                .tobytes()
            )

    def feed(self, pcm):
        if self.flushed:
            raise RuntimeError("Input after SoundTouch flush")
        if len(pcm) % 2:
            raise ValueError("Incomplete PCM16 frame")
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        for offset in range(0, len(audio), 960):
            part = np.ascontiguousarray(audio[offset : offset + 960])
            self.input_frames += len(part)
            if self.lib.st_put(
                self.handle,
                part.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                len(part),
            ):
                raise RuntimeError(self.lib.st_error().decode())
            yield from self.drain()

    def finish(self):
        if self.flushed:
            raise RuntimeError("Double SoundTouch flush")
        self.flushed = True
        if self.lib.st_flush(self.handle):
            raise RuntimeError(self.lib.st_error().decode())
        yield from self.drain()

    def close(self):
        if self.handle:
            self.lib.st_destroy(self.handle)
            self.handle = None
