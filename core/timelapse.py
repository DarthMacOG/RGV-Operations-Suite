from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


STARBASE_TIMEZONE = ZoneInfo("America/Chicago")


@dataclass(frozen=True)
class TimelapseSchedule:
    starbase_start: datetime
    starbase_end: datetime
    reolink_start: datetime
    reolink_end: datetime
    duration: timedelta


def build_schedule(
    starbase_start_naive: datetime,
    starbase_end_naive: datetime,
    computer_timezone,
) -> TimelapseSchedule:
    if starbase_end_naive <= starbase_start_naive:
        raise ValueError("The end time must be later than the start time.")
    start = starbase_start_naive.replace(tzinfo=STARBASE_TIMEZONE)
    end = starbase_end_naive.replace(tzinfo=STARBASE_TIMEZONE)
    # Convert through UTC so DST boundaries are handled as elapsed instants,
    # not as simple differences between wall-clock labels.
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    duration = end_utc - start_utc
    if duration.total_seconds() <= 0:
        raise ValueError("The selected period is invalid across the timezone transition.")

    return TimelapseSchedule(
        starbase_start=start,
        starbase_end=end,
        reolink_start=start_utc.astimezone(computer_timezone),
        reolink_end=end_utc.astimezone(computer_timezone),
        duration=duration,
    )


def format_duration(duration: timedelta) -> str:
    seconds = int(duration.total_seconds())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    if seconds or not parts:
        parts.append(f"{seconds} sec")
    return " ".join(parts)


def format_schedule_summary(
    schedule: TimelapseSchedule,
) -> str:
    local_name = schedule.reolink_start.tzname() or "computer local time"
    return "\n".join(
        [
            "RGV Timelapse Plan",
            "",
            "Desired Starbase schedule:",
            f"  Start: {schedule.starbase_start:%A, %B %d, %Y at %I:%M %p} "
            f"({schedule.starbase_start.tzname()})",
            f"  End:   {schedule.starbase_end:%A, %B %d, %Y at %I:%M %p} "
            f"({schedule.starbase_end.tzname()})",
            "",
            "Enter in the Reolink Client on this PC:",
            f"  Start: {schedule.reolink_start:%A, %B %d, %Y at %I:%M %p} ({local_name})",
            f"  End:   {schedule.reolink_end:%A, %B %d, %Y at %I:%M %p} ({local_name})",
            f"  Duration: {format_duration(schedule.duration)}",
            "",
            "This is a planning aid; confirm the values shown by Reolink before starting capture.",
        ]
    )
