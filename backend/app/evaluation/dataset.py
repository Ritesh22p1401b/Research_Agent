"""Loads the golden evaluation dataset (section 16)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATASET_PATH = Path("data") / "evaluation" / "questions.json"


@dataclass
class EvalQuestion:
    question: str
    expected_source: str | None = None
    expected_keywords: list[str] | None = None


def load_dataset(path: str | Path = DEFAULT_DATASET_PATH) -> list[EvalQuestion]:
    path = Path(path)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        EvalQuestion(
            question=item["question"],
            expected_source=item.get("expected_source"),
            expected_keywords=item.get("expected_keywords"),
        )
        for item in raw
    ]
