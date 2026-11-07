"""F1's top choices on one logged board, with every term, and what each does this turn.

    python tools/choices.py run8 13:12           # a log, and a fight:turn as tools/replay.py keys them
    python tools/choices.py run8 seq=4651        # or the state's sequence number
    python tools/choices.py run8 13:12 -n 8      # how many choices to show
    python tools/choices.py run8 13:12 --tag evaluator-v1.26   # as a tagged version would see it
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_row(log, where):
    rows = [json.loads(l) for l in (ROOT / "research" / "logs" / log / "state.jsonl").read_text(encoding="utf-8").splitlines()]
    if where.startswith("seq="):
        seq = int(where[4:])
        return next(r for r in rows if r.get("seq") == seq)
    fight, turn = map(int, where.split(":"))
    starts = [i for i, r in enumerate(rows) if r.get("event") == "combat_start"] + [len(rows)]
    return next(r for r in rows[starts[fight]:starts[fight + 1]]
                if r["type"] == "state" and r["enemies"] and r["turn"] == turn)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log")
    parser.add_argument("where", help="fight:turn, or seq=<number>")
    parser.add_argument("-n", type=int, default=6)
    parser.add_argument("--tag", help="a git tag whose solver to use")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        solver_dir = str(ROOT / "solver")
        if args.tag:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from replay import solver_at
            solver_at(args.tag, folder)
            solver_dir = folder
        sys.path.insert(0, solver_dir)
        from evaluator import VERSION, rank_actions
        from review import board
        from rules import state_from_log, step
        row = find_row(args.log, args.where)
        state = state_from_log(row)
        print(f"{VERSION}, turn {row['turn']}, HP {state.hero.hp}/{state.hero.max_hp}")
        print("  " + board(row))
        print("  tiles:", ", ".join(f"{t.attack.name} ({'loaded' if t.in_queue else 'ready' if t.ready else f'in {t.cooldown - t.charge}'})"
                                     for t in state.tiles), f"| special {state.swap_charge}/{state.swap_cooldown}")
        for line in rank_actions(state, depth=1)[:args.n]:
            outcome = step(state, line.actions[0])[1]
            print(f"  {line.score:8.1f} {line.labels[0]:<48} dmg {outcome.enemy_damage} kills {outcome.kills} hp lost {outcome.hp_lost}")
            print("           ", {k: round(v, 1) for k, v in line.terms.items() if abs(v) > 0.05})


if __name__ == "__main__":
    main()
