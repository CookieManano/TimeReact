"""Check MCP calls against a server running in a separate process."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_work_over_stdio_and_recover(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="timereact-mcp-test-") as folder:
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(root / "scripts/run_server.py")],
                env={"TIMEREACT_DB": str(Path(folder) / "state.sqlite3")},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertEqual({tool.name for tool in tools.tools}, {
                        "get_time_context", "start_timer", "get_timer", "list_timers", "cancel_timer",
                        "get_conversation_timeline", "resolve_time_reference"
                    })

                    async def call(name, arguments):
                        result = await session.call_tool(name, arguments)
                        self.assertFalse(result.isError, result.content)
                        return json.loads(result.content[0].text)

                    now = await call("get_time_context", {"session_id": "protocol"})
                    self.assertEqual(now["timezone"], "Asia/Shanghai")
                    relative = await call("resolve_time_reference", {"session_id": "protocol", "expression": "明天",
                                          "anchor_at": "2026-09-30T23:55:00+08:00"})
                    self.assertEqual(relative["start_at"], "2026-10-01T00:00:00+08:00")
                    timeline = await call("get_conversation_timeline", {"session_id": "protocol"})
                    self.assertEqual(timeline["events"], [])
                    created = await call("start_timer", {"session_id": "protocol", "duration_seconds": 300})
                    timer_id = created["timer_id"]
                    observed = await call("get_timer", {"session_id": "protocol", "timer_id": timer_id})
                    self.assertFalse(observed["estimated"])
                    self.assertGreater(observed["remaining_seconds"], 290)
                    records = await call("list_timers", {"session_id": "protocol"})
                    self.assertEqual(len(records["timers"]), 1)
                    missing = await session.call_tool("get_timer", {"session_id": "other", "timer_id": timer_id})
                    self.assertTrue(missing.isError)
                    bad = await session.call_tool("start_timer", {"session_id": "protocol", "duration_seconds": -1})
                    self.assertTrue(bad.isError)
            # Check that saved timers remain available after a server restart.
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("get_timer", {"session_id": "protocol", "timer_id": timer_id})
                    self.assertFalse(result.isError)
                    recovered = json.loads(result.content[0].text)
                    self.assertTrue(recovered["estimated"])
                    cancelled = await session.call_tool("cancel_timer", {"session_id": "protocol", "timer_id": timer_id})
                    self.assertEqual(json.loads(cancelled.content[0].text)["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
