"""The logged boards that replays and the principle test run on: every fight's first state of each turn.

Add a new log to RUNS once it's saved under research/logs/. Each entry is the log's folder name and the first fight
to use: run5_full's first nine fights were played by earlier versions.
"""
import json
from pathlib import Path

LOGS = Path(__file__).resolve().parent.parent / "research" / "logs"
RUNS = (
    ("run5_full", 9),
    ("run6", 0),
    ("run7", 0),
    ("run7_part2", 0),
    ("run7_part3", 0),
    ("run8", 0),
    ("run8_part2", 0),
    ("run9", 0),
    ("run10", 0),
    ("run11", 0),
    ("run12", 0),
    ("run13", 0),
)


def logged_boards(runs=RUNS):
    """Yields (key, row) for each fight's first state of each turn, keyed as "<log> <fight>:<turn>"."""
    for log, first in runs:
        rows = [json.loads(line) for line in (LOGS / log / "state.jsonl").read_text(encoding="utf-8").splitlines()]
        starts = [i for i, r in enumerate(rows) if r.get("event") == "combat_start"] + [len(rows)]
        for fight, (a, b) in enumerate(zip(starts, starts[1:])):
            if fight < first:
                continue
            seen = {}
            for row in rows[a:b]:
                if row["type"] == "state" and row["enemies"] and row["room"] != "CampRoom":
                    seen.setdefault(row["turn"], row)
            for turn, row in seen.items():
                yield f"{log} {fight}:{turn}", row
