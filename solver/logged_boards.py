"""The logged boards that replays and the principle test run on: every fight's first state of each turn.

Add a new log to RUNS once it's saved under research/logs/, then run `python tools/condense.py --add` to pick its
core boards. Each entry is the log's folder name and the first fight to use: run5_full's first nine fights were
played by earlier versions. Raw logs are never trimmed: the core only picks which boards run by default.
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
    ("run14", 0),
)


CORE = LOGS.parent / "boards" / "core.json"


def core_keys():
    """The core boards tools/condense.py chose: the subset everyday checks run on."""
    return set(json.loads(CORE.read_text(encoding="utf-8"))["boards"])


def logged_boards(runs=RUNS, core=False):
    """Yields (key, row) for each fight's first state of each turn, keyed as "<log> <fight>:<turn>". With `core`,
    only the core boards; the full set stays for releases and whenever the core might miss something."""
    keep = core_keys() if core else None
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
                key = f"{log} {fight}:{turn}"
                if keep is None or key in keep:
                    yield key, row
