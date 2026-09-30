"""Optional secondary classifications; the existing work_type remains primary."""

import json

from business.growth_tracking import WORK_TYPES


def validate_work_types(primary, additional):
    if primary and primary not in WORK_TYPES:
        raise ValueError("Invalid work type")
    if not isinstance(additional, list) or any(not isinstance(item, str) or item not in WORK_TYPES
                                                for item in additional):
        raise ValueError("Invalid additional work types")
    if additional and not primary:
        raise ValueError("Choose a primary work type first")
    if primary in additional or len(set(additional)) != len(additional):
        raise ValueError("Work types must be distinct")
    return additional


def read_additional(value):
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []
