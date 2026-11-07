"""Principles every position score must keep, checked on every logged board. Slower than the other tests.

Having a tile never scores lower than not having it: if it did, F1 would be better off without it, and could
throw it away to get there, as when Shadow Kama was fired at nothing to shed a positioning penalty. And a loaded
tile never scores lower than the same tile in hand, since sending it back is a free queue edit.

Each logged board is checked as it stands. The boards come from solver/logged_boards.py, and include the board
each real choice left, since that's the next turn's board in the log. The checks run in parallel.

Run with: python solver/test_principles.py
"""
import copy
import os
import unittest
from concurrent.futures import ProcessPoolExecutor

from evaluator import leaf_terms
from logged_boards import logged_boards
from rules import state_from_log

TOLERANCE = 0.01


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


def broken_on(item):
    """Every way one board breaks the two checks, as (check, text)."""
    where, row = item
    state = state_from_log(row)
    base = score(state)
    broken = []
    for index, tile in enumerate(state.tiles):
        if tile.ready:
            changed = without_tile(state, index, on_cooldown=True)
            if score(changed) > base + TOLERANCE:
                broken.append(("cooldown", f"{where}: {tile.attack.name} on cooldown gains {differences(state, changed)}"))
        if tile.in_queue:
            changed = without_tile(state, index, on_cooldown=False)
            if score(changed) > base + TOLERANCE:
                broken.append(("hand", f"{where}: {tile.attack.name} sent back gains {differences(state, changed)}"))
    return broken


class Principles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
            cls.broken = [b for found in pool.map(broken_on, logged_boards(), chunksize=8) for b in found]

    def check(self, kind):
        broken = [text for k, text in self.broken if k == kind]
        self.assertEqual(broken, [], f"{len(broken)} cases, first ones:\n" + "\n".join(broken[:15]))

    def test_having_a_tile_never_scores_lower(self):
        self.check("cooldown")

    def test_a_loaded_tile_never_scores_lower_than_in_hand(self):
        self.check("hand")


if __name__ == "__main__":
    unittest.main()
