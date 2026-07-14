"""Unit tests for the daily per-employee CSV export formatters (pure)."""
import csv
import io
from datetime import datetime, timezone

from app.modules.analytics.export import _hms, _safe, dwell_csv, timeline_csv

T = datetime(2026, 7, 15, 9, 0, 0, tzinfo=timezone.utc)


def _parse(text):
    return list(csv.reader(io.StringIO(text)))


def test_hms():
    assert _hms(0) == "0:00:00"
    assert _hms(2970) == "0:49:30"
    assert _hms(3661) == "1:01:01"
    assert _hms(-5) == "0:00:00"


def test_safe_guards_formula_injection():
    assert _safe("=SUM(A1)") == "'=SUM(A1)"
    assert _safe("+1") == "'+1"
    assert _safe("-cmd") == "'-cmd"
    assert _safe("@x") == "'@x"
    assert _safe("Ali") == "Ali"
    assert _safe(None) == ""


def test_dwell_csv_header_and_rows():
    data = {"rows": [
        {"emp_id": "E1", "name": "Ali", "floor_plan_name": "Ground",
         "zone_name": "Sales", "seconds": 2970, "sessions": 2,
         "first_seen": T, "last_seen": T, "present": True},
        {"emp_id": "E2", "name": "Sara", "floor_plan_name": "Ground",
         "zone_name": "Production", "seconds": 2400, "sessions": 1,
         "first_seen": T, "last_seen": T, "present": False},
    ]}
    rows = _parse(dwell_csv(data))
    assert rows[0] == ["employee_id", "employee_name", "floor_plan", "zone",
                       "seconds", "time", "visits", "first_seen", "last_seen", "present"]
    assert rows[1][:7] == ["E1", "Ali", "Ground", "Sales", "2970", "0:49:30", "2"]
    assert rows[1][9] == "yes"
    assert rows[2][:7] == ["E2", "Sara", "Ground", "Production", "2400", "0:40:00", "1"]
    assert rows[2][9] == "no"
    assert rows[1][7] == T.isoformat()


def test_dwell_csv_quotes_names_with_commas():
    data = {"rows": [{"emp_id": "E1", "name": "Doe, John", "floor_plan_name": "F",
                      "zone_name": "Z", "seconds": 60, "sessions": 1,
                      "first_seen": T, "last_seen": T, "present": False}]}
    # csv.reader round-trips the quoted comma back to one field.
    rows = _parse(dwell_csv(data))
    assert rows[1][1] == "Doe, John"


def test_timeline_csv_sequences_segments():
    data = {"emp_id": "E1", "name": "Ali", "segments": [
        {"floor_plan_name": "G", "zone_name": "Desk A", "start": T, "end": T,
         "seconds": 600, "sessions": 1, "present": False},
        {"floor_plan_name": "G", "zone_name": "Desk B", "start": T, "end": T,
         "seconds": 600, "sessions": 1, "present": True},
    ]}
    rows = _parse(timeline_csv(data))
    assert rows[0][:5] == ["employee_id", "employee_name", "sequence", "floor_plan", "zone"]
    assert rows[1][2] == "1" and rows[1][4] == "Desk A"
    assert rows[2][2] == "2" and rows[2][4] == "Desk B" and rows[2][10] == "yes"


def test_empty_exports_have_just_headers():
    assert len(_parse(dwell_csv({"rows": []}))) == 1
    assert len(_parse(timeline_csv({"emp_id": "E1", "name": None, "segments": []}))) == 1
