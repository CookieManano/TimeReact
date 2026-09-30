# Time measurement rules

## Durations and deadlines

`duration_seconds` measures elapsed seconds from creation. Within the same service process, a continuous clock is preferred, so changing the system date does not change the budget. Its returned `deadline_at` is an estimate based on the wall clock at creation and may diverge from the remaining budget after a clock adjustment.

An input `deadline_at` is an absolute calendar time and must include a UTC offset. Its remaining time follows the wall clock and changes when the system clock is corrected.

The inputs are mutually exclusive. Omitting both creates a stopwatch. A zero-second budget or a past deadline is immediately `expired`. `remaining_seconds` is clamped to zero; excess time appears in `overdue_seconds`.

## Sleep and recovery

macOS uses `mach_continuous_time`. Linux uses `CLOCK_BOOTTIME` when available. Both include system sleep. Other platforms fall back to `time.monotonic` and report `includes_suspend=false`; sleep inclusion is not guaranteed.

Continuous clock readings are compared only within the same process instance. After a server restart or when another CLI process reads a timer, elapsed time is recovered from the saved UTC start: `measurement_basis=wall_clock_recovery`, `estimated=true`. This includes offline time but cannot reconstruct clock adjustments made while offline. Negative differences are clamped to zero and flagged as a clock anomaly.

Within one instance, a difference exceeding two seconds between accumulated wall time and continuous time sets `clock_shift_detected=true`. Sleep can also cause this difference on fallback platforms. The flag does not verify network time; the system clock itself may be inaccurate.

## Snapshots and cancellation

Results describe the time at `sampled_at`. Query again after further work. Three decimal places do not imply millisecond accuracy across the full request.

Cancellation freezes elapsed time and measurement flags and saves `cancelled_at`. Later queries have a new `sampled_at`, but the timer remains stopped. Remaining time becomes null and overdue time becomes zero. Capture the running snapshot before cancellation if those values are needed in the final report.

## Sessions and access

Timer queries are scoped by `session_id`. This avoids mixing records between conversations but does not provide access control. The current service is intended for trusted local use.

## Background wakeup

This version returns time information only when queried. The MCP server does not deliver background events, invoke a model, or wake the host.
