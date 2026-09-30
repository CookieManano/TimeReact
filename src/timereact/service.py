"""Manage time observations and timers for both the CLI and MCP server."""

import json
import math
from uuid import uuid4

from .clock import Clock, Sample, elapsed, parse_deadline, timestamp, zone
from .store import Store


def identifier(value: str, name: str, limit: int = 128) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} 必须是非空字符串，最多 {limit} 个字符")
    return value


class TimeService:
    def __init__(self, store: Store, clock: Clock | None = None) -> None:
        self.store = store
        self.clock = clock or Clock()

    def _context(self, now: Sample, timezone_name: str) -> dict:
        return {
            "sampled_at": timestamp(now.wall),
            "local_time": timestamp(now.wall, timezone_name),
            "timezone": timezone_name,
            "clock_source": self.clock.source,
            "includes_suspend": self.clock.includes_suspend,
            "supports_background_wakeup": False,
        }

    def get_time_context(self, session_id: str, timezone_name: str = "Asia/Shanghai") -> dict:
        identifier(session_id, "session_id")
        zone(timezone_name)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self.clock.sample()
            row = db.execute("SELECT * FROM observations WHERE session_id = ?", (session_id,)).fetchone()
            previous = None
            if row:
                previous = elapsed(Sample(row["wall"], row["steady"], row["clock_instance"]), now)
                previous["previous_sampled_at"] = timestamp(row["wall"])
            db.execute("INSERT OR REPLACE INTO observations VALUES (?, ?, ?, ?)",
                       (session_id, now.wall, now.steady, now.instance))
        return {**self._context(now, timezone_name), "session_id": session_id,
                "since_previous_observation": previous}

    def start_timer(self, session_id: str, label: str = "任务", duration_seconds: float | None = None,
                    deadline_at: str | None = None) -> dict:
        identifier(session_id, "session_id")
        identifier(label, "label", 200)
        if duration_seconds is not None and deadline_at is not None:
            raise ValueError("duration_seconds 与 deadline_at 只能指定一个")
        if duration_seconds is not None:
            if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)):
                raise ValueError("duration_seconds 必须是有限的非负数字")
            if not math.isfinite(duration_seconds) or duration_seconds < 0:
                raise ValueError("duration_seconds 必须是有限的非负数字")
        deadline = parse_deadline(deadline_at) if deadline_at is not None else None
        now = self.clock.sample()
        if duration_seconds is not None:
            deadline = now.wall + duration_seconds
        if deadline is not None:
            try:
                timestamp(deadline)
            except (ValueError, OverflowError, OSError) as exc:
                raise ValueError("截止时间超出支持的日期范围") from exc
        timer_id = uuid4().hex
        with self.store.connect() as db:
            db.execute("INSERT INTO timers VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                       (timer_id, session_id, label, now.wall, now.steady, now.instance,
                        duration_seconds, deadline))
            row = self._find(db, session_id, timer_id)
        return self._snapshot(row, now)

    @staticmethod
    def _find(db, session_id: str, timer_id: str):
        row = db.execute("SELECT * FROM timers WHERE id = ? AND session_id = ?",
                         (timer_id, session_id)).fetchone()
        if row is None:
            raise ValueError("此会话中未找到该计时器")
        return row

    def _snapshot(self, row, now: Sample) -> dict:
        if row["stopped_json"]:
            frozen = json.loads(row["stopped_json"])
            return {**frozen, "sampled_at": timestamp(now.wall)}
        measurement = elapsed(Sample(row["start_wall"], row["start_steady"], row["clock_instance"]), now)
        # Check expiry before rounding so small budgets still expire correctly.
        same_instance = row["clock_instance"] == now.instance
        raw_elapsed = max(0, now.steady - row["start_steady"] if same_instance else now.wall - row["start_wall"])
        remaining = None
        mode = "stopwatch"
        if row["budget_seconds"] is not None:
            remaining = row["budget_seconds"] - raw_elapsed
            mode = "duration"
        elif row["deadline_wall"] is not None:
            remaining = row["deadline_wall"] - now.wall
            mode = "deadline"
        return {
            "timer_id": row["id"], "session_id": row["session_id"], "label": row["label"],
            "mode": mode, "status": "expired" if remaining is not None and remaining <= 0 else "running",
            "started_at": timestamp(row["start_wall"]), "sampled_at": timestamp(now.wall),
            "deadline_at": timestamp(row["deadline_wall"]) if row["deadline_wall"] is not None else None,
            "budget_seconds": row["budget_seconds"],
            "remaining_seconds": round(max(0, remaining), 3) if remaining is not None else None,
            "overdue_seconds": round(max(0, -remaining), 3) if remaining is not None else 0.0,
            **measurement,
            "clock_source": self.clock.source,
            "includes_suspend": self.clock.includes_suspend,
            "supports_background_wakeup": False,
        }

    def get_timer(self, session_id: str, timer_id: str) -> dict:
        identifier(session_id, "session_id")
        identifier(timer_id, "timer_id")
        with self.store.connect() as db:
            row = self._find(db, session_id, timer_id)
        return self._snapshot(row, self.clock.sample())

    def list_timers(self, session_id: str, limit: int = 50) -> dict:
        identifier(session_id, "session_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 200:
            raise ValueError("limit 必须是 1 到 200 的整数")
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM timers WHERE session_id = ? ORDER BY start_wall DESC, id LIMIT ?",
                              (session_id, limit + 1)).fetchall()
        now = self.clock.sample()
        return {"session_id": session_id, "sampled_at": timestamp(now.wall),
                "timers": [self._snapshot(row, now) for row in rows[:limit]],
                "has_more": len(rows) > limit}

    def cancel_timer(self, session_id: str, timer_id: str) -> dict:
        identifier(session_id, "session_id")
        identifier(timer_id, "timer_id")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._find(db, session_id, timer_id)
            now = self.clock.sample()
            result = self._snapshot(row, now)
            if row["stopped_json"] is None:
                result.update(status="cancelled", cancelled_at=timestamp(now.wall), remaining_seconds=None, overdue_seconds=0.0)
                db.execute("UPDATE timers SET stopped_json = ? WHERE id = ? AND session_id = ?",
                           (json.dumps(result, allow_nan=False), timer_id, session_id))
        return result
