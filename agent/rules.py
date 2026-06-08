"""Deterministic alert-rule engine (the table in 02_architecture_and_implementation_plan.md §3).

Kept separate from the LLM so alert firing is reproducible and unit-testable. The LLM
(reason_decide) supplies the human narrative; these rules decide *whether* an alert fires
so QA scenarios are stable run-to-run.
"""

from __future__ import annotations

import os

BUSINESS_START_HOUR = int(os.environ.get("BUSINESS_START_HOUR", "8"))
BUSINESS_END_HOUR = int(os.environ.get("BUSINESS_END_HOUR", "18"))

_VEHICLE_WORDS = {
    "car", "truck", "van", "bus", "vehicle", "motorcycle", "motorbike",
    "bike", "bicycle", "suv", "jeep", "lorry", "pickup", "sedan",
}
_PERSON_WORDS = {"person", "pedestrian", "human", "man", "woman", "people", "individual"}

# Comma-separated location labels considered restricted (default: none).
RESTRICTED_LOCATIONS = {
    loc.strip().lower()
    for loc in os.environ.get("RESTRICTED_LOCATIONS", "").split(",")
    if loc.strip()
}

_SEVERITY_RANK = {"info": 0, "warning": 1, "high": 2, "critical": 3}


def severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity, 0)


def is_person(object_type: str) -> bool:
    t = (object_type or "").lower()
    return any(w in t for w in _PERSON_WORDS)


def is_vehicle(object_type: str) -> bool:
    t = (object_type or "").lower()
    return any(w in t for w in _VEHICLE_WORDS)


def _hour(telemetry: dict) -> int | None:
    raw = telemetry.get("time")
    if not raw:
        return None
    try:
        return int(str(raw).split(":")[0])
    except (ValueError, IndexError):
        return None


def is_after_hours(telemetry: dict) -> bool:
    h = _hour(telemetry)
    if h is None:
        return False
    return h < BUSINESS_START_HOUR or h >= BUSINESS_END_HOUR


def _count_trailing_matches(rolling_window: list[dict], object_type: str, location: str) -> int:
    """Consecutive trailing window entries matching object_type AND location."""
    count = 0
    ot, loc = (object_type or "").lower(), (location or "").lower()
    for entry in reversed(rolling_window):
        if (entry.get("object_type", "").lower() == ot
                and entry.get("location", "").lower() == loc):
            count += 1
        else:
            break
    return count


def evaluate(
    vlm: dict,
    telemetry: dict,
    rolling_window: list[dict],
    events_today: list[dict],
) -> list[dict]:
    """Return the list of fired rules; each is ``{rule, severity, event_type, message}``."""
    fired: list[dict] = []
    object_type = vlm.get("object_type", "none")
    time_str = telemetry.get("time", "??:??")
    # Prefer telemetry waypoint for location; fall back to VLM scene description.
    location = telemetry.get("location") or vlm.get("location") or "unknown"
    after_hours = is_after_hours(telemetry)
    person = is_person(object_type)
    vehicle = is_vehicle(object_type)

    if person and after_hours:
        fired.append({
            "rule": "after_hours_person",
            "severity": "critical",
            "event_type": "after_hours_person",
            "message": f"Person at {location}, {time_str} — after hours",
        })

    if vehicle and after_hours:
        fired.append({
            "rule": "after_hours_vehicle",
            "severity": "high",
            "event_type": "after_hours_vehicle",
            "message": f"Vehicle ({vlm.get('color', 'unknown')} {object_type}) at "
                       f"{location}, {time_str} — after hours",
        })

    # Loitering: same subject + location across 5+ consecutive frames (incl. current).
    consecutive = _count_trailing_matches(rolling_window, object_type, location) + 1
    if (person or vehicle) and consecutive >= 5:
        fired.append({
            "rule": "loitering",
            "severity": "high",
            "event_type": "loitering",
            "message": f"{object_type.capitalize()} loitering at {location} — "
                       f"{consecutive} consecutive frames",
        })

    # Repeat vehicle: same descriptor (type+color) seen 3+ times this session.
    if vehicle:
        color = (vlm.get("color") or "").lower()
        seen = 1 + sum(
            1 for e in rolling_window
            if is_vehicle(e.get("object_type", ""))
            and e.get("color", "").lower() == color
        )
        if seen >= 3:
            fired.append({
                "rule": "repeat_vehicle",
                "severity": "warning",
                "event_type": "repeat_vehicle",
                "message": f"{vlm.get('color', 'A')} {object_type} — {seen}th sighting "
                           f"this session, last at {time_str}",
            })

    # Restricted zone: any subject in a configured restricted location.
    if RESTRICTED_LOCATIONS and (object_type not in ("none", "n/a")):
        loc_l = str(location).lower()
        if any(r in loc_l for r in RESTRICTED_LOCATIONS):
            fired.append({
                "rule": "restricted_zone",
                "severity": "critical",
                "event_type": "restricted_zone",
                "message": f"{object_type.capitalize()} in restricted zone "
                           f"{location}, {time_str}",
            })

    return fired


def top_severity(fired: list[dict]) -> str:
    if not fired:
        return "info"
    return max((f["severity"] for f in fired), key=severity_rank)
