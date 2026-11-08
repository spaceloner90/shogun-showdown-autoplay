"""Plays whole fights offline against the ported enemy AI, to compare how often each policy gets hit.

    python tools/simulate.py --policies F1 F3          # every start in every log
    python tools/simulate.py --policies F1 F4 --limit 40 --logs run13

Starts are the first board of each logged fight and the first board after each wave arrives, wherever every enemy's
AI is ported (no bosses). From there the chosen policy plays the hero and solver/enemy_ai.py the enemies, until all
of them are dead, the hero is, or MAX_TURNS pass. Waves still to come aren't spawned, and potions aren't used, so
every policy faces the same fight. F1 is the live evaluator's choice; F2 and deeper come from solver/search.py.

Reported per policy: HP lost, the turns on which the hero took damage (hits), deaths, starts not cleared in time,
and turns taken. Runs in parallel, one start per worker.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOLVER = str(ROOT / "solver")
sys.path.insert(0, SOLVER)
MAX_TURNS = 60


def _init():
    sys.path.insert(0, SOLVER)


def starts(logs):
    """(key, row) for each fight's first board and each board right after a wave arrives, all enemies ported."""
    from enemy_ai import PORTED
    from logged_boards import LOGS, RUNS
    found = []
    for log, first in RUNS:
        if logs and log not in logs:
            continue
        rows = [json.loads(line) for line in (LOGS / log / "state.jsonl").read_text(encoding="utf-8").splitlines()]
        fight, want = -1, False
        for row in rows:
            if row.get("event") == "combat_start":
                fight += 1
                want = True
            elif row.get("event") == "wave_spawn":
                want = True
            elif row["type"] == "state" and want and fight >= first and row["enemies"] and row["room"] != "CampRoom":
                want = False
                if all(e["kind"] in PORTED for e in row["enemies"]):
                    found.append((f"{log} {fight}:{row['turn']}", row))
    return found


def choose(state, policy):
    if policy == "F1":
        from evaluator import rank_actions
        return rank_actions(state, depth=1)[0].actions[0]
    from search import rank_lines
    return rank_lines(state, int(policy[1:]))[0].actions[0]


def play(item):
    key, row, policy = item
    from rules import state_from_log, step
    state = state_from_log(row)
    hp_lost = hits = turns = 0
    unknown_turns = 0
    started = time.perf_counter()
    while turns < MAX_TURNS and state.hero.alive and any(e.alive for e in state.enemies):
        action = choose(state, policy)
        state, outcome = step(state, action)
        turns += 1
        hp_lost += outcome.hp_lost
        hits += outcome.hp_lost > 0
        unknown_turns += any(e.alive and not e.known for e in state.enemies)
    return {"key": key, "policy": policy, "hp_lost": hp_lost, "hits": hits, "turns": turns,
            "dead": not state.hero.alive, "cleared": not any(e.alive for e in state.enemies),
            "unknown_turns": unknown_turns, "seconds": time.perf_counter() - started}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--policies", nargs="+", default=["F1", "F3"])
    parser.add_argument("--logs", nargs="*")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", help="where to save every result, as JSON")
    args = parser.parse_args()
    found = starts(args.logs)
    if args.limit:
        found = found[::max(1, len(found) // args.limit)][:args.limit]
    jobs = [(key, row, policy) for policy in args.policies for key, row in found]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=os.cpu_count(), initializer=_init) as pool:
        results = list(pool.map(play, jobs))
    print(f"{len(found)} starts, {time.perf_counter() - started:.0f} s")
    for policy in args.policies:
        mine = [r for r in results if r["policy"] == policy]
        total = lambda field: sum(r[field] for r in mine)  # noqa: E731
        decisions = total("turns")
        print(f"  {policy:<4} HP lost {total('hp_lost'):>4}  hits {total('hits'):>4}  deaths {total('dead'):>3}  "
              f"not cleared {sum(not r['cleared'] for r in mine):>3}  turns {decisions:>5}  "
              f"unknown turns {total('unknown_turns'):>4}  {total('seconds') / max(1, decisions):.3f} s a turn")
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=0), encoding="utf-8")


if __name__ == "__main__":
    main()
