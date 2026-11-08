"""Replays F1's top choice on every core board, or every logged board, in parallel, and saves what each choice does.

    python tools/replay.py                       # the solver as it is now, on the core boards
    python tools/replay.py --full                # on every logged board: for releases
    python tools/replay.py --tag evaluator-v2.0  # a tagged version, read from git

Results go to research/replays/<version>.core.json, or <version>.json with --full, keyed "<log> <fight>:<turn>",
so a tagged version only needs replaying once. Compare two with tools/compare.py. The boards are listed in
solver/logged_boards.py, and the core in research/boards/core.json, chosen by tools/condense.py.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPLAYS = ROOT / "research" / "replays"
SOLVER_FILES = ("evaluator.py", "rules.py", "review.py", "logged_boards.py")


def _init(solver_dir):
    sys.path.insert(0, solver_dir)


def _replay(item):
    from evaluator import rank_actions
    from rules import state_from_log, step
    key, row = item
    state = state_from_log(row)
    best = rank_actions(state, depth=1)[0]
    action = best.actions[0]
    _, outcome = step(state, action)
    fired = 0
    if action.kind == "Attack":
        fired = len(action.order) if action.order is not None else len(state.queue_tiles)
    return key, dict(label=best.labels[0], score=round(best.score, 2), hp=outcome.hp_lost, kills=outcome.kills,
                     dmg=outcome.enemy_damage, sent=outcome.sent_back, fired=fired, wasted=outcome.wasted_attacks)


def solver_at(tag, into):
    """Writes a tag's solver files into a folder. The boards come from the current list, since old tags may not
    have it, so every version is replayed on the same boards."""
    for name in SOLVER_FILES:
        if name == "logged_boards.py":
            text = (ROOT / "solver" / name).read_text(encoding="utf-8")
        else:
            text = subprocess.run(["git", "show", f"{tag}:solver/{name}"], cwd=ROOT, capture_output=True,
                                  text=True, encoding="utf-8").stdout
        (Path(into) / name).write_text(text, encoding="utf-8")


def replay(solver_dir, workers, full):
    sys.path.insert(0, str(ROOT / "solver"))
    from logged_boards import logged_boards
    boards = list(logged_boards(core=not full))
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(solver_dir,)) as pool:
        return dict(pool.map(_replay, boards, chunksize=8))


def version_of(solver_dir):
    for line in (Path(solver_dir) / "evaluator.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION = "):
            return line.split('"')[1]
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", help="a git tag to replay, such as evaluator-v2.0")
    parser.add_argument("--name", help="the results file's name, if not the version")
    parser.add_argument("--workers", type=int, default=os.cpu_count())
    parser.add_argument("--full", action="store_true", help="every logged board, not just the core")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        solver_dir = str(ROOT / "solver")
        if args.tag:
            solver_at(args.tag, folder)
            solver_dir = folder
        name = args.name or version_of(solver_dir)
        results = replay(solver_dir, args.workers, args.full)
    REPLAYS.mkdir(parents=True, exist_ok=True)
    out = REPLAYS / (f"{name}.json" if args.full else f"{name}.core.json")
    out.write_text(json.dumps(results, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{len(results)} boards replayed with {name}: {out}")


if __name__ == "__main__":
    main()
