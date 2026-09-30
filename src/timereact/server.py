"""Serve MCP tools over stdio; keep stdout clear for protocol messages."""

from functools import lru_cache

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .service import TimeService
from .store import Store, default_db
from .conversation import ConversationService

mcp = FastMCP("TimeReact", instructions="使用真实时间快照和计时器管理任务预算。每个会话使用独立且稳定的 session_id。此服务不支持后台唤醒。")


@lru_cache(maxsize=1)
def service() -> TimeService:
    return TimeService(Store(default_db()))


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def get_time_context(session_id: str, timezone: str = "Asia/Shanghai") -> dict:
    """Read the current time and save an observation. Return the interval since this session's previous observation. Use an IANA timezone name."""
    return service().get_time_context(session_id, timezone)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def start_timer(session_id: str, label: str = "任务", duration_seconds: float | None = None,
                deadline_at: str | None = None) -> dict:
    """Start a timer with a duration in seconds or an ISO deadline with a UTC offset. Omit both for a stopwatch. Keep the returned timer_id."""
    return service().start_timer(session_id, label, duration_seconds, deadline_at)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def get_timer(session_id: str, timer_id: str) -> dict:
    """Read elapsed, remaining, and overdue time with measurement flags. This is a snapshot; it does not send reminders or interrupt the model."""
    return service().get_timer(session_id, timer_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def list_timers(session_id: str, limit: int = 50) -> dict:
    """List recent timers in this session. Set limit from 1 to 200; has_more indicates that more records exist."""
    return service().list_timers(session_id, limit)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def cancel_timer(session_id: str, timer_id: str) -> dict:
    """Stop a timer and keep its record with elapsed time frozen. Repeated cancellation preserves the original stop time."""
    return service().cancel_timer(session_id, timer_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def get_conversation_timeline(session_id: str, limit: int = 20, offset: int = 0) -> dict:
    """Read timestamps and time expressions recorded by conversation hooks. Use limit and offset to page through events. Earlier unrecorded messages have no timestamps."""
    return ConversationService(service().store, service().clock).get_conversation_timeline(session_id, limit, offset)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def resolve_time_reference(session_id: str, expression: str, anchor_turn_id: str | None = None,
                           anchor_at: str | None = None, timezone: str | None = None) -> dict:
    """Resolve supported Chinese date expressions into date ranges. Use anchor_turn_id for a recorded message or anchor_at for an ISO timestamp with a UTC offset. Omit both to use the current time. Vague expressions remain ambiguous."""
    return ConversationService(service().store, service().clock).resolve_time_reference(
        session_id, expression, anchor_turn_id, anchor_at, timezone)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
