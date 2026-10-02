from __future__ import annotations

import json
from pathlib import Path

from council_v2 import CRITERIA_ORDER

FACULTY = Path(__file__).resolve().parents[1]
REPOS_ROOT = FACULTY.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def vec(*scores: int) -> dict[str, int]:
    assert len(scores) == 7
    return dict(zip(CRITERIA_ORDER, scores))


def legacy(cohort: str, slug: str, seat: str) -> dict:
    p = FACULTY / cohort / "council-reviews" / f"{slug}__{seat}.json"
    return json.loads(p.read_text(encoding="utf-8"))
