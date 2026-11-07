"""Principles every position score must keep, checked on every logged board. Slower than the other tests.

Having a tile never scores lower than not having it: if it did, F1 would be better off without it, and could
throw it away to get there, as when Shadow Kama was fired at nothing to shed a positioning penalty. And a loaded
tile never scores lower than the same tile in hand, since sending it back is a free queue edit.

Each logged board is checked as it stands and as F1's choice leaves it.

Run with: python solver/test_principles.py
"""
import copy
import json
import unittest
from pathlib import Path

from evaluator import leaf_terms, rank_actions
from rules import state_from_log, step

LOGS = Path(__file__).resolve().parent.parent / "research" / "logs"
RUNS = (("run5_full", 9), ("run6", 0), ("run7", 0), ("run7_part2", 0), ("run7_part3", 0), ("run8", 0))
TOLERANCE = 0.01


def logged_positions():
    """(where, state) for every logged board's first state of a turn, and the position F1's choice leaves."""
    for log, first in RUNS:
        rows = [json.loads(l) for l in (LOGS / log / "state.jsonl").read_text(encoding="utf-8").splitlines()]
        starts = [i for i, r in enumerate(rows) if r.get("event") == "combat_start"] + [len(rows)]
        for fight, (a, b) in enumerate(zip(starts, starts[1:])):
            if fight < first:
                continue
            seen = {}
            for row in rows[a:b]:
                if row["type"] == "state" and row["enemies"] and row["room"] != "CampRoom":
                    seen.setdefault(row["turn"], row)
            for turn, row in seen.items():
                state = state_from_log(row)
                yield f"{log} fight {fight} turn {turn}", state
                after, _ = step(state, rank_actions(state, depth=1)[0].actions[0])
                if after.hero.alive:
                    yield f"{log} fight {fight} turn {turn}, after F1's choice", after


def score(state):
    return sum(leaf_terms(state).values())


def without_tile(state, index, on_cooldown):
    """The position with one tile taken out of the queue: back in hand, or also put on cooldown."""
    changed = copy.deepcopy(state)
    tile = changed.tiles[index]
    if tile.in_queue:
        position = next(i for i, t in enumerate(changed.queue_tiles) if t is tile)
        del changed.queue_tiles[position]
        del changed.hero.queue[position]
        tile.in_queue = False
    if on_cooldown:
        tile.charge = 0
    return changed


def differences(before, after):
    a, b = leaf_terms(before), leaf_terms(after)
    return {k: round(b.get(k, 0) - a.get(k, 0), 1) for k in set(a) | set(b) if abs(b.get(k, 0) - a.get(k, 0)) > 0.05}


class Principles(unittest.TestCase):
    def test_having_a_tile_never_scores_lower(self):
        broken = []
        for where, state in logged_positions():
            base = score(state)
            for index, tile in enumerate(state.tiles):
                if tile.ready:
                    changed = without_tile(state, index, on_cooldown=True)
                    if score(changed) > base + TOLERANCE:
                        broken.append(f"{where}: {tile.attack.name} on cooldown gains {differences(state, changed)}")
        self.assertEqual(broken, [], f"{len(broken)} cases, first ones:\n" + "\n".join(broken[:15]))

    def test_a_loaded_tile_never_scores_lower_than_in_hand(self):
        broken = []
        for where, state in logged_positions():
            base = score(state)
            for index, tile in enumerate(state.tiles):
                if tile.in_queue:
                    changed = without_tile(state, index, on_cooldown=False)
                    if score(changed) > base + TOLERANCE:
                        broken.append(f"{where}: {tile.attack.name} sent back gains {differences(state, changed)}")
        self.assertEqual(broken, [], f"{len(broken)} cases, first ones:\n" + "\n".join(broken[:15]))


if __name__ == "__main__":
    unittest.main()
