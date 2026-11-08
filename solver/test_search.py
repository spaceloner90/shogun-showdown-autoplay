"""Tests for the ported enemy AI (enemy_ai.py) and the lookahead (search.py).

Run with: python solver/test_search.py
"""
import unittest

import enemy_ai
import search
from rules import Action, Agent, Attack, State, Tile, step
from test_rules import KATANA, SWIRL, enemy, make_state


def ashigaru(cell, facing=-1, queue=(), action="Wait"):
    return Agent("Ashigaru", cell, facing, 3, 3, queue=list(queue), action=action)


class EnemyAITest(unittest.TestCase):
    """The Ashigaru's choices, read from AshigaruEnemy.AIPickAction."""

    def decide(self, foe, previous, hero_cell=2):
        state = make_state(hero_cell=hero_cell, enemies=[foe])
        return enemy_ai.decide(state, foe, previous)

    def test_an_empty_queue_plays_its_katana(self):
        choice = self.decide(ashigaru(3), "Wait")
        self.assertEqual((choice.action, choice.tile), ("PlayTile", "Katana"))

    def test_it_waits_a_turn_after_playing_a_tile(self):
        self.assertEqual(self.decide(ashigaru(3, queue=[KATANA]), "PlayTile").action, "Wait")

    def test_it_attacks_when_the_hero_is_in_reach(self):
        self.assertEqual(self.decide(ashigaru(3, queue=[KATANA]), "Wait").action, "Attack")

    def test_it_closes_in_when_out_of_reach(self):
        self.assertEqual(self.decide(ashigaru(4, queue=[KATANA]), "Wait").action, "MoveLeft")

    def test_it_steps_back_after_attacking(self):
        self.assertEqual(self.decide(ashigaru(3, queue=[KATANA]), "Attack").action, "MoveRight")

    def test_it_turns_to_face_the_hero_first(self):
        self.assertEqual(self.decide(ashigaru(3, facing=1, queue=[KATANA]), "Wait").action, "FlipLeft")

    def test_a_frozen_enemy_waits(self):
        foe = ashigaru(3, queue=[KATANA])
        foe.ice = 2
        self.assertEqual(self.decide(foe, "Wait").action, "Wait")

    def test_an_unported_kind_is_unknown(self):
        boss = Agent("NobunagaBoss", 3, -1, 30, 30)
        self.assertIsNone(self.decide(boss, "Wait"))

    def test_the_simulation_carries_the_choice_into_next_turn(self):
        state = make_state(enemies=[ashigaru(4, action="PlayTile")])
        state.enemies[0].tile_to_play = "Katana"
        after, _ = step(state, Action("Wait"))
        foe = after.enemies[0]
        self.assertEqual(([a.name for a in foe.queue], foe.action, foe.known), (["Katana"], "Wait", True))


class SearchTest(unittest.TestCase):
    def test_a_known_turn_isnt_discounted(self):
        state = make_state(enemies=[ashigaru(4, queue=[KATANA])])
        self.assertTrue(search.certain(state))
        state.enemies[0].known = False
        self.assertFalse(search.certain(state))

    def test_the_win_only_counts_on_the_turn_chosen(self):
        state = make_state(enemies=[enemy(3, hp=2)], queue=["Swirl"])
        _, now, _, _ = search._turn(state, Action("Attack"), now=True)
        _, later, _, _ = search._turn(state, Action("Attack"), now=False)
        self.assertGreater(now - later, 1000)

    def test_it_sees_a_hit_coming_two_turns_out(self):
        # An Ashigaru two cells away will close in and then strike: F2 steps away in time or kills it.
        state = make_state(hero_cell=2, enemies=[ashigaru(4, queue=[KATANA])])
        line = search.rank_lines(state, 3)[0]
        after = state
        lost = 0
        for action in line.actions:
            after, outcome = step(after, action)
            lost += outcome.hp_lost
        self.assertEqual(lost, 0, line.labels)


class TieTest(unittest.TestCase):
    def test_a_kill_now_beats_the_same_kill_next_turn(self):
        # logs/run14, fight 7 turn 20: firing now killed three, and waiting a turn to fire scored the same.
        import json
        from pathlib import Path
        from rules import state_from_log
        rows = (Path(__file__).resolve().parent.parent / "research" / "logs" / "run14" / "state.jsonl").read_text(
            encoding="utf-8").splitlines()
        row = next(json.loads(r) for r in rows if '"seq":2526,' in r)
        best = search.rank_lines(state_from_log(row), 4)[0]
        self.assertTrue(best.labels[0].startswith("Attack"), best.labels)


if __name__ == "__main__":
    unittest.main()
