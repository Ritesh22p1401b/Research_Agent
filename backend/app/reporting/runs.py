"""Finished research runs kept in memory so a Word report can be generated on demand afterwards.

The user picks the report size (overview / detailed / comprehensive) *after* the research is done, so the
evidence and analysis of the run are cached here under a ``run_id`` (bounded, oldest evicted first).
"""
from __future__ import annotations

import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

MAX_RUNS = 30
_STATE_KEYS = ("query", "sub_questions", "evidence", "analysis", "critic", "report", "document_ids")


@dataclass
class SavedRun:
    query: str
    state: dict[str, Any]
    sources: list[dict]
    jobs: dict[str, str] = field(default_factory=dict)  # depth -> job id (so a repeated click reuses the job)


_runs: OrderedDict[str, SavedRun] = OrderedDict()


def save_run(query: str, final_state: dict[str, Any], sources: list[dict]) -> str:
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = SavedRun(query, {k: final_state.get(k) for k in _STATE_KEYS}, sources)
    while len(_runs) > MAX_RUNS:
        _runs.popitem(last=False)
    return run_id


def get_run(run_id: str) -> SavedRun | None:
    return _runs.get(run_id)
