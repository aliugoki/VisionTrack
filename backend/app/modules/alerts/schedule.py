"""Determine whether a rule's schedule is currently active.

Used by the evaluator on every tick — fast path matters. Pure functions,
no I/O, easy to unit test.

Schedule shape (matches Step 5 Batch A schema):
  {
    "mode": "always" | "scheduled",
    "start_time": "HH:MM" | None,
    "end_time":   "HH:MM" | None,
    "days":       [0..6 list, 0=Monday]
  }

When mode == "always": active at all times.
When mode == "scheduled":
  - days: alert fires only if today (in tenant tz) is in the list
  - time window: alert fires only if local time is within
      [start_time, end_time)
  - If end_time < start_time the window crosses midnight. The active
    check becomes (now >= start) OR (now < end). The "day" check uses
    the day the window OPENS, not the day during which it's currently
    active — so a window 23:00..06:00 on Friday remains active until
    06:00 Saturday morning.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _hhmm_to_minutes(s: str) -> int:
    """'18:30' → 18*60+30 = 1110. Format already validated by Pydantic."""
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def is_rule_active_now(
    schedule: dict[str, Any] | None,
    tenant_tz: str,
    now_utc: datetime,
) -> bool:
    """True iff `schedule` is currently in its active window.

    Args:
      schedule: Rule.schedule dict (mode/start_time/end_time/days), or None.
      tenant_tz: IANA timezone name (validated by Tenant model upstream).
      now_utc: timezone-aware UTC datetime. The evaluator passes time.now()
        once per tick so all rules in the tick see the same instant.

    Returns:
      True if the rule should be evaluated; False if it's dormant.
    """
    # Missing schedule = always active. Defensive — Pydantic would normally
    # default to {"mode": "always"} but rules from old DB rows might lack it.
    if not schedule:
        return True

    mode = schedule.get("mode", "always")
    if mode == "always":
        return True
    if mode != "scheduled":
        # Unknown mode — fail closed (don't fire); operator misconfigured.
        return False

    # Resolve tenant local time
    try:
        tz = ZoneInfo(tenant_tz)
    except ZoneInfoNotFoundError:
        # Unknown tenant tz — fall back to UTC so we don't silently miss
        # alerts. A separate validation should catch this at tenant config.
        tz = ZoneInfo("UTC")
    local = now_utc.astimezone(tz)

    days = schedule.get("days") or []
    start_time = schedule.get("start_time")
    end_time = schedule.get("end_time")

    # Missing day list = all days
    if days:
        # weekday(): 0=Mon..6=Sun, matches our schema convention
        today = local.weekday()
        # For windows that cross midnight, the rule is "active" if EITHER:
        #   (today in days AND now >= start)   — first half of the window
        #   (yesterday in days AND now < end)  — second half (rolled over)
        if start_time and end_time:
            s = _hhmm_to_minutes(start_time)
            e = _hhmm_to_minutes(end_time)
            cur = local.hour * 60 + local.minute
            if e <= s:
                # Cross-midnight window
                opens_today = today in days and cur >= s
                yesterday = (today - 1) % 7
                still_open = yesterday in days and cur < e
                return opens_today or still_open
            else:
                # Same-day window: just check today's membership + time band
                if today not in days:
                    return False
                return s <= cur < e
        # No times set but days set — active all day on those days
        return today in days

    # Days unset, times set → daily band, any day
    if start_time and end_time:
        s = _hhmm_to_minutes(start_time)
        e = _hhmm_to_minutes(end_time)
        cur = local.hour * 60 + local.minute
        if e <= s:
            return cur >= s or cur < e
        return s <= cur < e

    # Neither days nor times → effectively always
    return True
