import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from core.timelapse import build_schedule, format_duration, format_schedule_summary


class TimelapseTests(unittest.TestCase):
    def setUp(self):
        self.denver = ZoneInfo("America/Denver")

    def test_summer_starbase_converts_to_denver(self):
        schedule = build_schedule(
            datetime(2026, 7, 27, 8, 0),
            datetime(2026, 7, 27, 10, 0),
            self.denver,
        )
        self.assertEqual(schedule.starbase_start.tzname(), "CDT")
        self.assertEqual(schedule.reolink_start.hour, 7)
        self.assertEqual(schedule.reolink_start.tzname(), "MDT")

    def test_winter_starbase_converts_to_denver(self):
        schedule = build_schedule(
            datetime(2026, 12, 10, 8, 0),
            datetime(2026, 12, 10, 9, 0),
            self.denver,
        )
        self.assertEqual(schedule.starbase_start.tzname(), "CST")
        self.assertEqual(schedule.reolink_start.hour, 7)
        self.assertEqual(schedule.reolink_start.tzname(), "MST")

    def test_spring_dst_uses_elapsed_time(self):
        schedule = build_schedule(
            datetime(2026, 3, 8, 1, 30),
            datetime(2026, 3, 8, 3, 30),
            self.denver,
        )
        self.assertEqual(format_duration(schedule.duration), "1 hr")

    def test_rejects_invalid_period(self):
        with self.assertRaises(ValueError):
            build_schedule(
                datetime(2026, 7, 27, 10, 0),
                datetime(2026, 7, 27, 9, 0),
                self.denver,
            )

    def test_summary_contains_both_timezones(self):
        schedule = build_schedule(
            datetime(2026, 7, 27, 8, 0),
            datetime(2026, 7, 27, 9, 0),
            self.denver,
        )
        summary = format_schedule_summary(schedule)
        self.assertIn("CDT", summary)
        self.assertIn("MDT", summary)


if __name__ == "__main__":
    unittest.main()
