---
name: time-awareness
description: Use TimeReact to check actual time, interpret relative dates against message timestamps, and manage task budgets or deadlines. Apply when a conversation depends on current time, historical date references, or elapsed time.
---

# Time awareness

Use TimeReact tools as time evidence. Token counts, intuition, and old snapshots do not establish the current time.

## Establish context

- Reuse the host's `session_id`, including the one supplied by a TimeReact hook. If none is available, create a random identifier and retain it for this conversation. It groups local records; it is not authentication.
- Use the user's requested timezone. Otherwise use the recorded timezone for historical messages and `Asia/Shanghai` for current-time queries.
- Hook timestamps describe processing time, approximately message arrival. They are not verified client send times or timestamps displayed on chat bubbles.
- If tools are unavailable, state which operation could not be performed. Do not claim that a timer started or that a date was verified. Missing hooks do not prevent time queries, but unrecorded messages have no historical anchors.

## Choose the workflow

| Need | Action |
|---|---|
| Current time or time since the last observation | Call `get_time_context` with the stable session ID and timezone. |
| Relative date in the current message | Use that message's injected timestamp or recorded user `turn_id` as the anchor. |
| Relative date in a historical message | Locate the original user message with `get_conversation_timeline`, then use its `turn_id`. |
| Explicit reference date or hypothetical scenario | Use the stated reference time with `anchor_at`, including its UTC offset. |
| Task budget, deadline, or stopwatch | Follow the timer workflow below. |

## Resolve a relative date

1. Identify whose words are being interpreted and whether they refer to an explicit date, a quotation, or a hypothetical scenario. Choose that reference before interpreting the time expression.
2. Call `resolve_time_reference` with either `anchor_turn_id` or `anchor_at`, never both. For historical records, follow `next_offset` while `has_more` is true when the needed event is outside the current page. Match the event to conversation context; a timestamp alone does not identify its subject.
3. Check the result before using it. A missing historical anchor is unknown, not today's date. A vague expression remains ambiguous; use conversation context or ask for clarification when the distinction affects the answer.
4. Preserve the resolved event date across later turns. If answering whether it is still upcoming, query current time separately. Keep important dates and original `turn_id` values in summaries.

For example, “明天考试” said on September 30 refers to October 1 even if the user asks about that exam on October 3. An operation that crosses midnight must still interpret the original message against its original anchor.

The parser supports Chinese day, week, and month expressions. Ranges exclude their end; weeks begin on Monday. Yesterday means the previous local calendar day, not the preceding 24 hours. If the user requests another convention or an unsupported expression, explain the parser's limitation and interpret it separately using the available evidence.

## Manage a task budget

1. Start once with `start_timer`: use `duration_seconds` for a budget, `deadline_at` with a UTC offset for an absolute deadline, or omit both for a stopwatch. Keep the returned `timer_id`. If recovering an existing timer, use `list_timers` in the same session rather than restarting it.
2. Query `get_timer` at useful phase boundaries, after slow tool calls, and before delivery. Avoid polling without useful work between checks. Adjust the remaining work to `remaining_seconds` and the user's priorities.
3. When `status=expired`, follow the user's instructions about overruns. If no overrun policy was given, prioritize delivering available results and clearly report unfinished work. A timer cannot interrupt an ongoing model response.
4. Before reporting elapsed or overdue time, inspect `estimated` and `clock_shift_detected`. Qualify uncertain measurements. Optionally call `cancel_timer` when the work ends to freeze the record; capture the final running snapshot first because cancellation clears remaining and overdue values.

`supports_background_wakeup=false`: expiry becomes observable on the next query. Do not promise automatic reminders or a background wakeup from this service.

Read [time-policy.md](references/time-policy.md) when sleep, clock adjustments, process restarts, or measurement reliability affect the task.
