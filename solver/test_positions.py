"""Real positions from the logs, with what depth 1 should and shouldn't do in them.

These come from play: mistakes that should stay fixed, and good decisions that should stay good.

Run with: python solver/test_positions.py
"""
import json
import unittest
from pathlib import Path

from evaluator import rank_actions
from rules import Action, state_from_log, step

LOGS = Path(__file__).resolve().parent.parent / "research" / "logs"
ROWS = {
    name: [json.loads(line) for line in (LOGS / name / "state.jsonl").read_text(encoding="utf-8").splitlines()]
    for name in ("run2_complete", "run3_v03", "run3_part2")
}


def position(fight, turn, log="run2_complete"):
    """The first state of a turn. Fights are numbered as played, and the log's first combat is the camp."""
    rows = ROWS[log]
    start = [i for i, r in enumerate(rows) if r.get("event") == "combat_start"][fight]
    for row in rows[start:]:
        if row["type"] == "state" and row["turn"] == turn:
            return state_from_log(row)
    raise LookupError(f"fight {fight} has no turn {turn}")


def choice(fight, turn, log="run2_complete"):
    return rank_actions(position(fight, turn, log), depth=1)[0]


class MistakesToAvoid(unittest.TestCase):
    def test_kills_a_dashing_charger_instead_of_letting_it_fire(self):
        # Fight 5, turn 25: Arrow loaded and aimed at a 1hp Charger about to dash.
        best = choice(5, 25)
        self.assertEqual(best.actions[0].kind, "Attack")
        self.assertEqual(best.terms.get("hp_lost", 0), 0)

    def test_adds_to_the_stack_for_a_kill_next_turn(self):
        # Battle 8, turn 17: Swirl loaded beside a 5hp Guardian, with Katana ready.
        best = choice(8, 17)
        self.assertEqual(best.labels[0], "PlayTile Katana")

    def test_adds_to_the_stack_beside_a_yari_master(self):
        # Fight 9, turn 17: Katana loaded beside a 4hp Yari Master, with Arrow ready.
        self.assertEqual(choice(9, 17).labels[0], "PlayTile Arrow")

    def test_holds_a_lethal_stack_instead_of_chipping_with_arrow(self):
        # Fight 4, turn 23: Swirl and Arrow loaded, a 4hp Yari Master three cells away.
        self.assertFalse(choice(4, 23).labels[0].startswith("Attack"))

    def test_does_not_throw_away_a_full_stack_to_wound(self):
        # Fight 5, turn 42: three tiles loaded, and a 4hp Yari Master out of reach of two of them.
        self.assertFalse(choice(5, 42).labels[0].startswith("Attack"))

    def test_loads_what_removes_the_lethal_threat(self):
        # Fight 9, turn 19, on 1hp: a 1hp Yari Master behind is about to turn and attack.
        self.assertEqual(choice(9, 19).labels[0], "PlayTile Swirl")


class ShadowDash(unittest.TestCase):
    """Run 3's second boss: one failed use by F1 and one test by the player, with results to match."""

    def test_does_not_count_on_a_dash_with_no_room_behind_the_target(self):
        # Turn 10: the boss is on the last cell, and a Spear is about to reach the hero.
        best = choice(6, 10, "run3_v03")
        self.assertEqual(best.terms.get("hp_lost", 0), 0)
        self.assertNotEqual(best.actions[0].kind, "Attack")

    def test_simulates_the_failed_use_as_it_happened(self):
        after, outcome = step(position(6, 10, "run3_v03"), Action("Attack"))
        self.assertEqual((after.hero.cell, outcome.hp_lost), (4, 2))
        self.assertEqual(next(e.hp for e in after.enemies if e.kind == "IwaoBoss"), 13)

    def test_simulates_the_successful_use_as_it_happened(self):
        # Turn 28: past the boss to cell 5, where Arrow kills the Charger and Swirl hits the boss.
        after, _ = step(position(6, 28, "run3_v03"), Action("Attack"))
        self.assertEqual(after.hero.cell, 5)
        self.assertEqual([(e.kind, e.cell, e.hp) for e in after.enemies], [("IwaoBoss", 4, 7)])


class CurseAsPlayed(unittest.TestCase):
    """The twins boss, where a stack showed exactly how far a curse reaches."""

    def test_a_curse_doubles_exactly_one_tile(self):
        # Turn 8 in the game: Swirl hit for 3 and cursed, Arrow's 4 hit for 8, then Swirl's 2 hit for 2.
        rows = ROWS["run3_part2"]
        twins_row = next(i for i, r in enumerate(rows) if r["type"] == "state"
                         and any(e["kind"] == "TwinMainBoss" for e in r["enemies"]))
        fight = sum(r.get("event") == "combat_start" for r in rows[:twins_row]) - 1
        state = position(fight, 8, "run3_part2")
        swirl3 = next(i for i, t in enumerate(state.tiles) if t.attack.name == "Swirl" and t.attack.value == 3)
        arrow = next(i for i, t in enumerate(state.tiles) if t.attack.name == "Arrow")
        swirl2 = next(i for i, t in enumerate(state.tiles) if t.attack.name == "Swirl" and t.attack.value == 2)
        after, outcome = step(state, Action("Attack", order=(swirl3, arrow, swirl2)))
        self.assertEqual(outcome.enemy_damage, 13)
        self.assertEqual(next(e.hp for e in after.enemies if e.kind == "TwinMainBoss"), 18)


class FreePlay(unittest.TestCase):
    """Run 3's fight 7, where one Swirl had Free Play, and v0.4 loaded it and sent it back."""

    def test_never_loads_the_free_tile_on_its_own(self):
        for turn in range(1, 29):
            state = position(7, turn, "run3_v03")
            best = rank_actions(state, depth=1)[0]
            action = best.actions[0]
            if action.kind == "PlayTile":
                self.assertFalse(state.tiles[action.tile].free_play, turn)


class GoodPlaysToKeep(unittest.TestCase):
    def test_lines_up_the_double_kill(self):
        # Fight 7, turn 2: Swirl clears the Archer, so Arrow reaches the TwinTachi behind it.
        self.assertEqual(choice(7, 2).labels[0], "PlayTile Arrow")

    def test_fires_the_double_kill(self):
        best = choice(7, 3)
        self.assertEqual(best.actions[0].kind, "Attack")
        self.assertEqual(best.terms.get("kills", 0) / 60, 2)

    def test_lets_the_guardian_walk_in(self):
        # Battle 8, turn 14: it's telegraphed to step next to the hero, into a lethal stack.
        self.assertFalse(choice(8, 14).labels[0].startswith("Attack"))

    def test_fires_the_stack_when_the_guardian_arrives(self):
        self.assertEqual(choice(8, 15).actions[0].kind, "Attack")

    def test_steps_into_earth_impales_blind_spot(self):
        # Boss 2, turn 8: Earth Impale hits only 2 cells away, so stepping adjacent dodges it.
        self.assertEqual(choice(6, 8).labels[0], "MoveRight")

    def test_swaps_past_a_spear(self):
        self.assertEqual(choice(7, 28).labels[0], "MoveRight (swap)")

    def test_swaps_past_a_dash(self):
        # Boss 1, turn 8: the Charger's dash then carries on along the board.
        self.assertEqual(choice(3, 8).labels[0], "MoveLeft (swap)")

    def test_top_choices_stay_out_of_avoidable_hits(self):
        # Every option here dodges for free, so none should take the hit.
        for fight, turn in ((8, 6), (8, 10), (7, 10), (4, 14)):
            self.assertEqual(choice(fight, turn).terms.get("hp_lost", 0), 0, (fight, turn))


if __name__ == "__main__":
    unittest.main()
