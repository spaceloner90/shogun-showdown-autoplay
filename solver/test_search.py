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


class HiddenMemoryTest(unittest.TestCase):
    """Since mod 0.17.0 the log gives what some enemies' AI remembers, so their choices are known."""

    def row(self, kind, memory, action="Wait", queue=(), tile=""):
        enemy_row = {"kind": kind, "cell": 4, "facing": "Left", "hp": 3, "maxHp": 3, "shield": False,
                     "queue": [{"name": q, "value": 0, "range": [], "closestTargetOnly": True} for q in queue],
                     "action": action, "memory": memory, "tileToPlay": tile}
        return {"cells": 7, "hero": {"kind": "Wanderer", "cell": 1, "facing": "Right", "hp": 10, "maxHp": 10,
                "shield": False, "queue": [], "action": "Wait", "special": {"name": "SwapSpecialMove", "charge": 4,
                "cooldown": 4}}, "enemies": [enemy_row], "tiles": [], "skills": []}

    def test_the_shinobi_alternates_from_its_logged_last_tile(self):
        from rules import state_from_log
        state = state_from_log(self.row("Shinobi", {"prevAttack": "Shuriken"}))
        choice = enemy_ai.decide(state, state.enemies[0], "Attack")
        self.assertEqual(choice.action, "MoveRight")  # Away after attacking, as before.
        foe = state.enemies[0]
        self.assertEqual(enemy_ai.tile_for(foe), "SmokeBomb")

    def test_a_logged_tile_to_play_is_used(self):
        from rules import state_from_log
        state = state_from_log(self.row("Warden", {"previousAttack": "Curse"}, action="PlayTile", tile="Summon"))
        self.assertEqual(state.enemies[0].tile_to_play, "Summon")

    def test_the_summoner_counts_down_then_summons(self):
        from rules import state_from_log
        state = state_from_log(self.row("Summoner", {"waitBeforeSummoning": 1, "turnsToWaitBeforeSummoning": 3}))
        foe = state.enemies[0]
        self.assertFalse(foe.movable)
        self.assertEqual(enemy_ai.decide(state, foe, "Wait").action, "Wait")
        self.assertEqual((enemy_ai.decide(state, foe, "Wait").action, foe.ai_wait), ("PlayTile", 0))

    def test_the_summoner_fires_and_restarts_its_countdown(self):
        from rules import state_from_log
        state = state_from_log(self.row("Summoner", {"waitBeforeSummoning": 0, "turnsToWaitBeforeSummoning": 3},
                                        queue=["Summon"]))
        foe = state.enemies[0]
        self.assertEqual((enemy_ai.decide(state, foe, "Wait").action, foe.ai_wait), ("Attack", 3))

    def test_the_swapper_waits_three_after_swapping(self):
        from rules import state_from_log
        state = state_from_log(self.row("Swapper", {"waitCountdown": 0}, queue=["BossSwap"]))
        foe = state.enemies[0]
        self.assertEqual((enemy_ai.decide(state, foe, "Wait").action, foe.ai_wait), ("Attack", 3))

    def test_without_logged_memory_they_stay_unknown(self):
        from rules import state_from_log
        state = state_from_log(self.row("Summoner", {}))
        self.assertIsNone(enemy_ai.decide(state, state.enemies[0], "Wait"))


class PotionChoiceTest(unittest.TestCase):
    """Potions judged over the deepest line, as the player set (v2.27)."""

    def board(self, potions):
        # The hero cornered, the special move uncharged, and an Ashigaru beside it about to strike: no way out.
        state = make_state(hero_cell=0, enemies=[ashigaru(1, queue=[KATANA], action="Attack")], swap_charge=0)
        state.potions = list(potions)
        return state

    def choose(self, state, depth=2):
        from rules import apply_potion
        lines = search.rank_lines(state, depth)
        after = {name: search.rank_lines(apply_potion(state, name), depth) for name in set(state.potions)
                 if name in search.POTION_PREFERENCE}
        return search.potion_choice(state, lines, after, depth)

    def test_a_potion_that_saves_hp_over_the_line_is_used(self):
        name, why = self.choose(self.board(["Shield"]))
        self.assertEqual(name, "Shield", why)

    def test_freeze_first_before_the_shogun(self):
        state = self.board(["Shield", "MassIce"])
        state.before_final = True
        self.assertEqual(self.choose(state)[0], "MassIce")

    def test_edamame_waits_for_six_with_triple_combo_heal(self):
        state = self.board(["Edamame"])
        state.hero.hp = 6
        state.triple_heal = True
        self.assertNotEqual(self.choose(state)[0], "Edamame")
        state.hero.hp = 4
        self.assertEqual(self.choose(state)[0], "Edamame")

    def test_progression_marks_the_fight_before_the_shogun(self):
        from rules import state_from_log
        row = {"cells": 5, "hero": {"kind": "Wanderer", "cell": 0, "facing": "Right", "hp": 10, "maxHp": 10,
               "shield": False, "queue": [], "action": "Wait", "special": {"name": "SwapSpecialMove", "charge": 4,
               "cooldown": 4}}, "enemies": [], "tiles": [], "skills": [],
               "progression": {"day": 1, "island": 7, "room": 2, "rooms": 4, "inShogunCastle": True}}
        self.assertTrue(state_from_log(row).before_final)
        row["progression"]["room"] = 3
        self.assertFalse(state_from_log(row).before_final)


if __name__ == "__main__":
    unittest.main()
