import math
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from timereact.clock import Clock, Sample
from timereact.service import TimeService
from timereact.store import Store


class FakeClock:
    source = "test_continuous"
    includes_suspend = True

    def __init__(self, wall=1_800_000_000.0, steady=100.0, instance="first"):
        self.wall, self.steady, self.instance = wall, steady, instance

    def sample(self):
        return Sample(self.wall, self.steady, self.instance)

    def advance(self, seconds, wall_shift=0):
        self.wall += seconds + wall_shift
        self.steady += seconds


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "timers.sqlite3"
        self.clock = FakeClock()
        self.service = TimeService(Store(self.path), self.clock)

    def tearDown(self):
        self.folder.cleanup()

    def start(self, seconds=10, session="a"):
        return self.service.start_timer(session, "测试任务", seconds)["timer_id"]

    def test_native_clock_advances(self):
        clock = Clock()
        first, second = clock.sample(), clock.sample()
        self.assertGreaterEqual(second.steady, first.steady)
        self.assertEqual(first.instance, second.instance)
        if sys.platform == "darwin":
            self.assertEqual(clock.source, "mach_continuous_time")
            self.assertTrue(clock.includes_suspend)

    def test_context_observes_elapsed_and_timezone(self):
        first = self.service.get_time_context("a")
        self.assertIsNone(first["since_previous_observation"])
        self.assertTrue(first["local_time"].endswith("+08:00"))
        self.clock.advance(15)
        second = self.service.get_time_context("a")
        self.assertEqual(second["since_previous_observation"]["elapsed_seconds"], 15)
        self.assertFalse(second["supports_background_wakeup"])

    def test_observations_are_separate_for_sessions(self):
        self.service.get_time_context("a")
        self.clock.advance(15)
        self.assertIsNone(self.service.get_time_context("b")["since_previous_observation"])

    def test_duration_progress_and_expiry(self):
        timer = self.start()
        self.clock.advance(4)
        result = self.service.get_timer("a", timer)
        self.assertEqual(result["remaining_seconds"], 6)
        self.assertEqual(result["status"], "running")
        self.clock.advance(8)
        result = self.service.get_timer("a", timer)
        self.assertEqual(result["status"], "expired")
        self.assertEqual(result["remaining_seconds"], 0)
        self.assertEqual(result["overdue_seconds"], 2)

    def test_expiry_does_not_use_rounded_time(self):
        timer = self.start(0.0004)
        self.assertEqual(self.service.get_timer("a", timer)["status"], "running")
        self.clock.advance(0.0005)
        self.assertEqual(self.service.get_timer("a", timer)["status"], "expired")

    def test_zero_budget_is_immediately_expired(self):
        timer = self.start(0)
        self.assertEqual(self.service.get_timer("a", timer)["status"], "expired")

    def test_duration_ignores_wall_clock_jump(self):
        timer = self.start()
        self.clock.advance(4, wall_shift=3600)
        result = self.service.get_timer("a", timer)
        self.assertEqual(result["elapsed_seconds"], 4)
        self.assertEqual(result["remaining_seconds"], 6)
        self.assertTrue(result["clock_shift_detected"])

    def test_duration_ignores_wall_clock_backward_adjustment(self):
        timer = self.start()
        self.clock.advance(4, wall_shift=-3600)
        result = self.service.get_timer("a", timer)
        self.assertEqual(result["elapsed_seconds"], 4)
        self.assertTrue(result["clock_shift_detected"])

    def test_absolute_deadline_tracks_wall_clock(self):
        deadline = datetime.fromtimestamp(self.clock.wall + 10, timezone.utc).isoformat()
        timer = self.service.start_timer("a", deadline_at=deadline)["timer_id"]
        self.clock.advance(4, wall_shift=20)
        result = self.service.get_timer("a", timer)
        self.assertEqual(result["mode"], "deadline")
        self.assertEqual(result["status"], "expired")
        self.assertEqual(result["overdue_seconds"], 14)

    def test_past_deadline_is_immediately_expired(self):
        deadline = datetime.fromtimestamp(self.clock.wall - 10, timezone.utc).isoformat()
        result = self.service.start_timer("a", deadline_at=deadline)
        self.assertEqual(result["overdue_seconds"], 10)

    def test_stopwatch_has_no_remaining_budget(self):
        timer = self.service.start_timer("a")["timer_id"]
        self.clock.advance(100)
        result = self.service.get_timer("a", timer)
        self.assertEqual(result["mode"], "stopwatch")
        self.assertEqual(result["elapsed_seconds"], 100)
        self.assertIsNone(result["remaining_seconds"])

    def test_restart_recovers_with_explicit_estimate(self):
        timer = self.start()
        self.clock.advance(7)
        recovered = TimeService(Store(self.path), FakeClock(self.clock.wall, 0, "new"))
        result = recovered.get_timer("a", timer)
        self.assertEqual(result["elapsed_seconds"], 7)
        self.assertEqual(result["remaining_seconds"], 3)
        self.assertTrue(result["estimated"])
        self.assertEqual(result["measurement_basis"], "wall_clock_recovery")

    def test_restart_context_marks_estimate(self):
        self.service.get_time_context("a")
        self.clock.advance(7)
        recovered = TimeService(Store(self.path), FakeClock(self.clock.wall, 0, "new"))
        self.assertTrue(recovered.get_time_context("a")["since_previous_observation"]["estimated"])

    def test_backward_clock_after_restart_is_reported(self):
        timer = self.start()
        recovered = TimeService(Store(self.path), FakeClock(self.clock.wall - 100, 0, "new"))
        result = recovered.get_timer("a", timer)
        self.assertEqual(result["elapsed_seconds"], 0)
        self.assertTrue(result["estimated"])
        self.assertTrue(result["clock_shift_detected"])

    def test_session_scoped_lookup_and_cancel(self):
        timer = self.start()
        self.assertEqual(self.service.list_timers("b")["timers"], [])
        for action in (self.service.get_timer, self.service.cancel_timer):
            with self.assertRaises(ValueError):
                action("b", timer)
        self.assertEqual(self.service.get_timer("a", timer)["status"], "running")

    def test_cancel_freezes_elapsed_and_is_idempotent(self):
        timer = self.start()
        self.clock.advance(3)
        first = self.service.cancel_timer("a", timer)
        self.clock.advance(50)
        second = self.service.cancel_timer("a", timer)
        self.assertEqual(first["cancelled_at"], second["cancelled_at"])
        self.assertEqual(second["elapsed_seconds"], 3)
        self.assertEqual(second["status"], "cancelled")
        self.assertIsNone(second["remaining_seconds"])
        recovered = TimeService(Store(self.path), FakeClock(self.clock.wall, 0, "new"))
        self.assertEqual(recovered.get_timer("a", timer)["elapsed_seconds"], 3)

    def test_list_reports_truncation(self):
        self.start()
        self.clock.advance(1)
        newest = self.start()
        result = self.service.list_timers("a", 1)
        self.assertEqual(result["timers"][0]["timer_id"], newest)
        self.assertTrue(result["has_more"])

    def test_invalid_duration_does_not_create_records(self):
        for duration in (-1, math.nan, math.inf, True, "10", 1e300):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                self.service.start_timer("a", duration_seconds=duration)
        self.assertEqual(self.service.list_timers("a")["timers"], [])

    def test_invalid_or_ambiguous_deadline(self):
        for deadline in ("invalid", "2026-09-30T12:00:00", "2026-09-30"):
            with self.subTest(deadline=deadline), self.assertRaises(ValueError):
                self.service.start_timer("a", deadline_at=deadline)
        with self.assertRaises(ValueError):
            self.service.start_timer("a", duration_seconds=10, deadline_at="2026-09-30T12:00:00+08:00")

    def test_invalid_session_and_timezone(self):
        with self.assertRaises(ValueError):
            self.service.get_time_context("a", "invalid/zone")
        with self.assertRaises(ValueError):
            self.service.start_timer(" ")
        with self.assertRaises(ValueError):
            self.service.list_timers("a", 0)


if __name__ == "__main__":
    unittest.main()
