# TimeReact

**Give Codex a conversation timeline so relative dates stay tied to the messages they came from.**

TimeReact is a local time-awareness extension with a skill, an MCP server, and Codex hooks. It records message timestamps, resolves relative dates, and tracks task budgets and deadlines. Current version: `0.2.0`.

For example, a user says “The exam is tomorrow” on September 30. When they ask about that exam on October 3, the original message anchor still points to October 1.

## Features

- Message timestamps for session events, user prompts, and completed assistant responses.
- Chinese relative-date expressions for days, weeks, and months.
- Historical date references anchored to the original message.
- Current-time queries, elapsed time, remaining budgets, and overdue time.
- Local SQLite storage that survives service restarts.

TimeReact does not require an OpenAI API key or call a model directly. Codex handles its own model access.

## How it works

```text
User submits a message
        ↓
Codex hook records the timestamp in SQLite
        ↓
Time context is added to the conversation
        ↓
The time-awareness skill selects the relevant message anchor
        ↓
TimeReact MCP tools provide detailed queries when needed
```

| Component | Responsibility |
|---|---|
| Skill | Guides time queries, message-anchor selection, and task budgets. |
| MCP server | Provides clocks, timers, a conversation timeline, and date resolution. |
| Hooks | Record lifecycle events and supply timestamp context automatically. |

The integration runs in the local Codex environment where it is configured. Other applications need their own integration.

## Requirements

- Python 3.11 or later.
- A Codex host with local MCP and lifecycle hook support.
- IANA timezone data. The default timezone is `Asia/Shanghai`.

The primary development environment is macOS. Windows support has not been fully verified; it may require `tzdata` and adjusted Python paths and shell commands. The commands below use a macOS/Linux shell.

## Quick start

From the project directory, run the standalone demo:

```bash
python3 scripts/timereact.py demo
```

The demo creates a two-second budget, shows progress snapshots, and cleans up its temporary records. It only needs the Python standard library.

To create a five-minute timer:

```bash
python3 scripts/timereact.py now
python3 scripts/timereact.py --session study start --label "Study session" --seconds 300
python3 scripts/timereact.py --session study list
```

Use the returned `timer_id` to inspect or stop it:

```bash
python3 scripts/timereact.py --session study status YOUR_TIMER_ID
python3 scripts/timereact.py --session study cancel YOUR_TIMER_ID
```

For an absolute deadline, supply a timestamp with a UTC offset and replace the example date:

```bash
python3 scripts/timereact.py --session study start --deadline '2026-10-01T18:00:00+08:00'
```

## Set up Codex

### 1. Install dependencies

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

### 2. Generate local configuration

```bash
python3 scripts/generate_codex_config.py
```

This creates two files with absolute paths to the current installation:

```text
.timereact/config/codex-mcp.toml
.timereact/config/codex-hooks.json
```

The generator leaves existing Codex settings untouched. Run it again if you move the project.

### 3. Merge the configuration

- Merge `codex-mcp.toml` into `~/.codex/config.toml`.
- Merge the events under `hooks` in `codex-hooks.json` into `~/.codex/hooks.json`. If the destination does not exist, copy the generated file there.
- Preserve existing settings and avoid duplicate TimeReact handlers. If hooks are configured inline, add the events to that existing configuration instead.

If `CODEX_HOME` is set, use that configuration directory. MCP and hooks must share the same `TIMEREACT_DB`; the generated configuration uses `.timereact/state.sqlite3` in this project.

Files under `examples/` contain placeholder paths and need editing before use.

### 4. Install the skill

Copy the entire skill folder into the personal skill directory:

```bash
mkdir -p ~/.agents/skills
cp -R skills/time-awareness ~/.agents/skills/
```

If a copy already exists, update that folder instead of creating a nested or duplicate copy. Some hosts also discover skills in `~/.codex/skills`; use the location supported by your host. See the [Codex skill guide](https://learn.chatgpt.com/docs/build-skills).

### 5. Enable hooks and check the connection

In Codex CLI, open `/hooks` and review the three TimeReact handlers:

| Event | Recorded context |
|---|---|
| `SessionStart` | Session start, resume, or context compaction. |
| `UserPromptSubmit` | User message processing time and recognized time expressions. |
| `Stop` | Assistant response completion time. |

New hooks need the host's trust approval before they run. Saving the configuration alone does not activate them. See the [Codex hooks guide](https://learn.chatgpt.com/docs/hooks).

Reopen the conversation. Restart Codex if tools or the skill are missing. Then send:

```text
$time-awareness Check the current time and whether this message has an injected timestamp.
```

Confirm that the MCP tools are available and the conversation timeline contains new events for this session. Hook context is available to the model; it does not change chat bubble timestamps.

## Use the skill

The skill can be selected automatically when relevant or invoked explicitly with `$time-awareness`.

Its workflow is:

1. Reuse the conversation's session ID and choose the relevant timezone.
2. Choose a current message, historical message, or explicit reference time as the date anchor.
3. Query time, resolve a supported expression, or start and inspect a task timer.
4. Check the result before answering and retain important dates for later references.

For a task budget, ask:

```text
Use TimeReact to give this research task a five-minute budget. Check the remaining time at each useful phase and deliver available results when the budget expires.
```

For historical dates, refer to the original message or event. The skill retrieves that message's anchor rather than shifting the event to today's date.

## MCP tools

| Tool | Purpose |
|---|---|
| `get_time_context` | Read current time, timezone, and the interval since the last observation. |
| `start_timer` | Start a duration budget, absolute deadline, or stopwatch. |
| `get_timer` | Read elapsed, remaining, and overdue time. |
| `list_timers` | Find timers in the current session. |
| `cancel_timer` | Stop a timer and retain its record. |
| `get_conversation_timeline` | Retrieve message anchors with pagination. |
| `resolve_time_reference` | Resolve a relative date against the current time or a specified anchor. |

Use a stable `session_id` throughout a conversation. For date resolution, supply either `anchor_turn_id` for a recorded user message or `anchor_at` for an explicit timestamp.

The date parser currently accepts Chinese expressions, including `今天` (today), `昨天` (yesterday), `明天` (tomorrow), `上周` (last week), and `下个月` (next month). English equivalents are not parser inputs.

Example arguments for `resolve_time_reference`:

```json
{
  "session_id": "example-session",
  "expression": "明天",
  "anchor_at": "2026-09-30T23:55:00+08:00"
}
```

## Limitations

- Timers do not send automatic reminders, wake the model, or interrupt a response.
- Messages predating hook activation have no recorded timestamps.
- Missing conversation text cannot be reconstructed from timestamps alone.
- The model still needs conversation context to interpret references correctly.
- The plugin manifests are included, but direct plugin installation has not been fully verified. Use the local setup above for this version.

## License

No open-source license has been specified yet.
