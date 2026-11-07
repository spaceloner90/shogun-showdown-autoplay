"""Which potion F1 would use first on every logged board with potions held, and why, in parallel.

    python tools/potions.py           # totals by potion
    python tools/potions.py --show    # also every board where one would be used
"""
import argparse
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SOLVER = str(Path(__file__).resolve().parent.parent / "solver")
sys.path.insert(0, SOLVER)


def _init():
    sys.path.insert(0, SOLVER)


def _plan(item):
    from evaluator import potion_plan, rank_actions
    from rules import state_from_log
    key, row = item
    state = state_from_log(row)
    name, why, _ = potion_plan(state, rank_actions(state, depth=1))
    return key, state.hero.hp, state.hero.max_hp, list(state.potions), name, why


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    from logged_boards import logged_boards
    boards = [(k, r) for k, r in logged_boards() if r.get("potions")]
    with ProcessPoolExecutor(max_workers=os.cpu_count(), initializer=_init) as pool:
        results = list(pool.map(_plan, boards, chunksize=4))
    uses = Counter()
    for key, hp, max_hp, held, name, why in results:
        if name:
            uses[name] += 1
            if args.show:
                print(f"{key:<18} HP {hp}/{max_hp} held {held}: {name} - {why}")
    print(f"{len(results)} boards with potions held; would use: {dict(uses.most_common())}")


if __name__ == "__main__":
    main()
