"""JSON export for graves."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from gravedigger.exhume import Grave


def _default_serializer(obj: Any) -> Any:
    """JSON serializer for non-standard types."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def graves_to_json(graves: list[Grave]) -> str:
    """Serialize list of Graves to JSON string.

    Dates are ISO strings, tuples are lists, all fields included.
    """
    data = []
    for g in graves:
        data.append({
            "path": g.path,
            "death_commit": g.death_commit,
            "death_date": g.death_date,
            "killer": g.killer,
            "death_message": g.death_message,
            "born_commit": g.born_commit,
            "born_date": g.born_date,
            "born_message": g.born_message,
            "born_by": g.born_by,
            "lifespan_days": g.lifespan_days,
            "lines_at_death": g.lines_at_death,
            "last_snippet": g.last_snippet,
            "notability": g.notability,
            "members": g.members,
            "is_mass": g.is_mass,
        })
    return json.dumps(data, default=_default_serializer, ensure_ascii=False, indent=2)