"""Record Codex lifecycle events and return their timestamp context."""

import json
import sys

from .conversation import ConversationService
from .store import Store, default_db


def handle(payload: dict, service: ConversationService, timezone_name: str = "Asia/Shanghai") -> dict:
    name = payload.get("hook_event_name")
    session = payload.get("session_id")
    event = service.record_event(session, payload.get("turn_id"), name,
                                 payload.get("prompt", "") if name == "UserPromptSubmit" else "", timezone_name)
    lines = ["[TimeReact 对话时间上下文]",
             "时间来自本机 hook 处理时刻，近似消息到达时间，不是已核实的客户端发送时刻。",
             f"当前会话：{session}；当前事件：{name}；当前消息时间：{event['observed_at']}；时区：{event['timezone']}。"]
    if event["turn_id"]:
        lines.append(f"当前消息标识 turn_id：{event['turn_id']}。")
    lines.extend([
        "解析本条消息的今天/明天/昨天等词时，以本条消息日期为锚点；引用历史消息时使用那条消息的时间。",
        "先判断话语是否在引用、假设或叙述其他日期，不能把检测到的时间词一律当作当前日期。",
        "历史消息的未来日期可能已经过去；再次回答前核对当前时间。刚才/最近/下次/稍后没有唯一范围，不能虚构精确日期。",
        "需要历史锚点时调用 get_conversation_timeline 或 resolve_time_reference(anchor_turn_id=...)；没有记录就说明未知。",
    ])
    recent = service.get_conversation_timeline(session, 5)["events"]
    lines.append("最近事件及其时间表达（这些换算仅适用于以该消息日期为锚点的情况）：")
    for item in recent:
        if item["role"] == "session":
            continue
        refs = []
        for ref in item["relative_references"][:3]:
            refs.append(ref["expression"] + ("→" + ref["start_at"] + "至" + ref["end_at"] + "（右端不含）"
                         if ref["status"] == "resolved" else "→需上下文判断"))
        lines.append(f"{item['role']} turn_id={item['turn_id'] or 'unknown'} @ {item['observed_at']}" +
                     ("；" + "；".join(refs) if refs else "") +
                     ("；其他时间词请查询 timeline" if len(item["relative_references"]) > 3 else ""))
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": "\n".join(lines)}}


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook 输入必须为 JSON 对象")
        print(json.dumps(handle(payload, ConversationService(Store(default_db()))), ensure_ascii=False))
    except Exception as exc:
        # Let the message proceed if timestamp collection fails.
        print(json.dumps({"systemMessage": f"TimeReact 时间记录失败（{type(exc).__name__}），本轮时间上下文未注入。"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
