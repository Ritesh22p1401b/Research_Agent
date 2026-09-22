"""CLI: run the evaluation dataset and print/save a summary.

Usage:
    python scripts/evaluate.py [--out data/evaluation/results.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import get_logger  # noqa: E402
from app.evaluation.runner import run_evaluation  # noqa: E402

logger = get_logger(__name__)


async def main(out_path: Path) -> None:
    outcome = await run_evaluation()
    print(json.dumps(outcome["summary"], indent=2))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    logger.info("Saved full evaluation results to %s", out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/evaluation/results.json")
    args = parser.parse_args()
    asyncio.run(main(Path(args.out)))
