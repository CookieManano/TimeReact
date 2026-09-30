"""Read elapsed time with sleep included when supported by the platform."""

import ctypes
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Sample:
    wall: float
    steady: float
    instance: str


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("无效的时区；请使用 Asia/Shanghai 等 IANA 时区名称") from exc


def timestamp(seconds: float, timezone_name: str = "UTC") -> str:
    return datetime.fromtimestamp(seconds, zone(timezone_name)).isoformat(timespec="milliseconds")


def parse_deadline(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("missing timezone")
        return parsed.astimezone(timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError, AttributeError) as exc:
        raise ValueError("截止时间必须包含时区，例如 2026-09-30T18:00:00+08:00") from exc


class Clock:
    def __init__(self) -> None:
        self.instance = uuid4().hex
        self.source = "monotonic"
        self.includes_suspend = False
        self._steady = time.monotonic
        if hasattr(time, "CLOCK_BOOTTIME"):
            self._steady = lambda: time.clock_gettime(time.CLOCK_BOOTTIME)
            self.source = "boottime"
            self.includes_suspend = True
        elif sys.platform == "darwin":
            class Timebase(ctypes.Structure):
                _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]

            library = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            library.mach_timebase_info.argtypes = [ctypes.POINTER(Timebase)]
            library.mach_timebase_info.restype = ctypes.c_int
            library.mach_continuous_time.argtypes = []
            library.mach_continuous_time.restype = ctypes.c_uint64
            info = Timebase()
            if library.mach_timebase_info(ctypes.byref(info)) != 0 or not info.denom:
                raise RuntimeError("无法初始化 macOS 连续时钟")
            ratio = info.numer / info.denom / 1_000_000_000
            self._steady = lambda: library.mach_continuous_time() * ratio
            self.source = "mach_continuous_time"
            self.includes_suspend = True

    def sample(self) -> Sample:
        return Sample(time.time(), self._steady(), self.instance)


def elapsed(start: Sample, end: Sample) -> dict:
    wall_delta = end.wall - start.wall
    same_instance = start.instance == end.instance
    raw = end.steady - start.steady if same_instance else wall_delta
    drift = wall_delta - raw if same_instance else None
    return {
        "elapsed_seconds": round(max(0.0, raw), 3),
        "measurement_basis": "continuous" if same_instance else "wall_clock_recovery",
        "estimated": not same_instance,
        "clock_shift_detected": abs(drift) > 2.0 if drift is not None else raw < 0,
        "wall_clock_drift_seconds": round(drift, 3) if drift is not None else None,
    }
