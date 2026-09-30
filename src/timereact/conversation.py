"""Record message timestamps and resolve relative dates without storing message text."""

import calendar
import json
import re
from datetime import datetime, timedelta
from uuid import uuid4

from .clock import Clock, timestamp, parse_deadline, zone
from .service import identifier
from .store import Store

DAY_OFFSETS = {"前天": -2, "昨天": -1, "今天": 0, "明天": 1, "后天": 2}
WEEK_OFFSETS = {"上周": -1, "本周": 0, "这周": 0, "下周": 1}
MONTH_OFFSETS = {"上个月": -1, "本月": 0, "这个月": 0, "下个月": 1}
VAGUE = {"刚才", "最近", "之前", "以后", "下次", "过一会儿", "稍后"}
REFERENCE_PATTERN = re.compile("|".join(sorted([*DAY_OFFSETS, *WEEK_OFFSETS, *MONTH_OFFSETS, *VAGUE], key=len, reverse=True)))


def resolve(expression: str, anchor_wall: float, timezone_name: str) -> dict:
    expression = expression.strip()
    local = datetime.fromtimestamp(anchor_wall, zone(timezone_name))
    result = {"expression": expression, "anchor_at": timestamp(anchor_wall, timezone_name),
              "timezone": timezone_name, "end_exclusive": True}
    midnight = datetime.combine(local.date(), datetime.min.time(), local.tzinfo)
    if expression in DAY_OFFSETS:
        start = midnight + timedelta(days=DAY_OFFSETS[expression])
        end = start + timedelta(days=1)
        granularity = "day"
    elif expression in WEEK_OFFSETS:
        start = midnight - timedelta(days=local.weekday()) + timedelta(weeks=WEEK_OFFSETS[expression])
        end = start + timedelta(days=7)
        granularity = "week"
    elif expression in MONTH_OFFSETS:
        index = local.year * 12 + local.month - 1 + MONTH_OFFSETS[expression]
        year, month = divmod(index, 12)
        start = datetime(year, month + 1, 1, tzinfo=local.tzinfo)
        end = start + timedelta(days=calendar.monthrange(year, month + 1)[1])
        granularity = "month"
    else:
        return {**result, "status": "ambiguous", "start_at": None, "end_at": None,
                "reason": "该表达没有唯一的时间范围，需要结合上下文或向用户确认。"}
    return {**result, "status": "resolved", "granularity": granularity,
            "start_at": start.isoformat(), "end_at": end.isoformat(),
            "convention": "自然日；每周从周一开始；自然月。"}


class ConversationService:
    def __init__(self, store: Store, clock: Clock | None = None):
        self.store = store
        self.clock = clock or Clock()

    @staticmethod
    def _serialize(row) -> dict:
        return {"event_id": row["id"], "session_id": row["session_id"], "turn_id": row["turn_id"],
                "event_name": row["event_name"], "role": row["role"],
                "observed_at": timestamp(row["observed_wall"], row["timezone"]),
                "timezone": row["timezone"], "timestamp_source": "hook_processing_time",
                "relative_references": json.loads(row["references_json"])}

    def record_event(self, session_id: str, turn_id: str | None, event_name: str,
                     prompt: str = "", timezone_name: str = "Asia/Shanghai") -> dict:
        identifier(session_id, "session_id")
        if turn_id is not None:
            identifier(turn_id, "turn_id")
        if event_name not in {"SessionStart", "UserPromptSubmit", "Stop"}:
            raise ValueError("不支持的对话事件")
        zone(timezone_name)
        if not isinstance(prompt, str):
            raise ValueError("prompt 必须是字符串")
        wall = self.clock.sample().wall
        role = {"SessionStart": "session", "UserPromptSubmit": "user", "Stop": "assistant"}[event_name]
        # Store matched time expressions rather than the full message.
        references = [resolve(term, wall, timezone_name) for term in dict.fromkeys(REFERENCE_PATTERN.findall(prompt))]
        event_id = uuid4().hex
        with self.store.connect() as db:
            db.execute("INSERT OR IGNORE INTO conversation_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (event_id, session_id, turn_id, event_name, role, wall, timezone_name,
                        json.dumps(references, ensure_ascii=False)))
            if turn_id is not None:
                row = db.execute("SELECT * FROM conversation_events WHERE session_id=? AND turn_id=? AND event_name=?",
                                 (session_id, turn_id, event_name)).fetchone()
            else:
                row = db.execute("SELECT * FROM conversation_events WHERE id=?", (event_id,)).fetchone()
        return self._serialize(row)

    def get_conversation_timeline(self, session_id: str, limit: int = 20, offset: int = 0) -> dict:
        identifier(session_id, "session_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit 必须是 1 到 100 的整数")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset 必须是非负整数")
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM conversation_events WHERE session_id=? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                              (session_id, limit + 1, offset)).fetchall()
        return {"session_id": session_id, "events": [self._serialize(row) for row in reversed(rows[:limit])],
                "has_more": len(rows) > limit, "next_offset": offset + limit if len(rows) > limit else None,
                "note": "只记录启用 hook 后的处理时刻；不会补造历史消息的发送时间。"}

    def resolve_time_reference(self, session_id: str, expression: str, anchor_turn_id: str | None = None,
                               anchor_at: str | None = None, timezone_name: str | None = None) -> dict:
        identifier(session_id, "session_id")
        identifier(expression, "expression", 100)
        if anchor_turn_id is not None and anchor_at is not None:
            raise ValueError("anchor_turn_id 与 anchor_at 只能指定一个")
        source = "current_clock"
        if anchor_turn_id is not None:
            identifier(anchor_turn_id, "anchor_turn_id")
            with self.store.connect() as db:
                row = db.execute("SELECT * FROM conversation_events WHERE session_id=? AND turn_id=? AND event_name='UserPromptSubmit'",
                                 (session_id, anchor_turn_id)).fetchone()
            if row is None:
                raise ValueError("没有该历史消息的时间记录，不能以当前日期替代")
            wall = row["observed_wall"]
            timezone_name = timezone_name or row["timezone"]
            source = "recorded_user_turn"
        elif anchor_at is not None:
            wall = parse_deadline(anchor_at)
            source = "explicit_anchor"
        else:
            wall = self.clock.sample().wall
        return {**resolve(expression, wall, timezone_name or "Asia/Shanghai"), "anchor_source": source,
                "anchor_turn_id": anchor_turn_id}
