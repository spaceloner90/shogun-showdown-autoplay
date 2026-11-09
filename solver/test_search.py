"""Tests for the ported enemy AI (enemy_ai.py) and the lookahead (search.py).

Run with: python solver/test_search.py
"""
import unittest

import enemy_ai
import search
from evaluator import WEIGHTS
from rules import Action, Agent, Attack, State, Tile, step
from test_rules import KATANA, SWIRL, enemy, make_state


def ashigaru(cell, facing=-1, queue=(), action="Wait"):
    return Agent("Ashigaru", cell, facing, 3, 3, queue=list(queue), action=action)


class DaisukeTest(unittest.TestCase):
    """DaisukeBoss.AIPickAction in the game's code."""

    def decide(self, queue, previous, facing=-1, cell=3, traits=False):
        foe = Agent("DaisukeBoss", cell, facing, 12, 15, queue=list(queue))
        foe.corrupted = traits
        return enemy_ai.decide(make_state(hero_cell=2, enemies=[foe]), foe, previous)

    CHARGE = Attack("Charge", 1, list(range(1, 11)), first_target=True)

    def test_he_turns_to_face_the_hero_first(self):
        self.assertEqual(self.decide([self.CHARGE, KATANA], "Attack", facing=1).action, "FlipLeft")

    def test_he_steps_back_after_attacking(self):
        self.assertEqual(self.decide([self.CHARGE, KATANA], "Attack").action, "MoveRight")

    def test_a_turn_after_playing_a_tile_unless_corrupted(self):
        self.assertEqual(self.decide([self.CHARGE, KATANA], "PlayTile").action, "Wait")
        self.assertEqual(self.decide([self.CHARGE, KATANA], "PlayTile", traits=True).action, "Attack")

    def test_the_katana_follows_a_lone_charge(self):
        choice = self.decide([self.CHARGE], "Wait")
        self.assertEqual((choice.action, choice.tile), ("PlayTile", "Katana"))

    def test_an_empty_queue_plays_an_unknown_tile(self):
        choice = self.decide([], "Wait")
        self.assertEqual((choice.action, choice.tile), ("PlayTile", None))

    def test_he_attacks_when_threatening(self):
        self.assertEqual(self.decide([self.CHARGE, KATANA], "Wait").action, "Attack")


class IwaoTest(unittest.TestCase):
    """IwaoBoss.AIPickAction and DashPattern in the game's code."""
    DASH = Attack("Dash", 0, [], first_target=True)
    SPEAR = Attack("Spear", 2, [1, 2])
    IMPALE = Attack("EarthImpale", 2, [-2, 2])

    def decide(self, queue, previous, facing=-1, cell=5, hero_cell=2, corrupted=False, others=()):
        foe = Agent("IwaoBoss", cell, facing, 12, 22, queue=list(queue))
        foe.corrupted = corrupted
        return enemy_ai.decide(make_state(hero_cell=hero_cell, enemies=[foe, *others]), foe, previous)

    def test_a_turn_after_playing_a_tile_unless_corrupted(self):
        self.assertEqual(self.decide([self.SPEAR], "PlayTile", cell=3).action, "Wait")
        self.assertEqual(self.decide([self.SPEAR], "PlayTile", cell=3, corrupted=True).action, "Attack")

    def test_the_spear_follows_a_dash_a_turn_later(self):
        self.assertEqual(self.decide([self.DASH], "PlayTile", corrupted=True).action, "Wait")
        choice = self.decide([self.DASH], "Wait", corrupted=True)
        self.assertEqual((choice.action, choice.tile), ("PlayTile", "Spear"))

    def test_with_dash_and_spear_he_strikes_from_anywhere(self):
        # logs/run17 turn 14: from cell 0, with the hero anywhere, nothing in between.
        self.assertEqual(self.decide([self.DASH, self.SPEAR], "Wait", corrupted=True).action, "Attack")

    def test_but_not_through_someone(self):
        self.assertEqual(self.decide([self.DASH, self.SPEAR], "Wait", corrupted=True,
                                     others=[enemy(4)]).action, "Wait")

    def test_with_a_dash_he_turns_to_face_the_hero_first(self):
        self.assertEqual(self.decide([self.DASH, self.SPEAR], "Wait", facing=1, corrupted=True).action, "FlipLeft")

    def test_he_steps_back_after_attacking(self):
        self.assertEqual(self.decide([], "Attack", cell=3).action, "MoveRight")

    def test_an_empty_queue_plays_an_unknown_tile(self):
        choice = self.decide([], "Wait")
        self.assertEqual((choice.action, choice.tile), ("PlayTile", None))

    def test_swirl_follows_earth_impale_with_the_hero_adjacent(self):
        choice = self.decide([self.IMPALE], "Wait", cell=3)
        self.assertEqual((choice.action, choice.tile), ("PlayTile", "Swirl"))

    def test_a_logged_tile_to_play_is_used(self):
        from rules import state_from_log
        import json
        from pathlib import Path
        rows = (Path(__file__).resolve().parent.parent / "research" / "logs" / "run17" / "state.jsonl").read_text(
            encoding="utf-8").splitlines()
        row = next(json.loads(r) for r in rows if '"seq":1633,' in r)
        iwao = state_from_log(row).enemies[0]
        self.assertEqual((iwao.corrupted, iwao.tile_to_play), (True, "Spear"))


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


class WaveEndTest(unittest.TestCase):
    """A line ends where the next wave arrives, scored on the board it lands on."""

    def test_a_kill_that_brings_the_wave_ends_the_line(self):
        state = make_state(enemies=[enemy(3, hp=2)], queue=["Swirl"])
        state.turns_until_wave = 9
        line = next(l for l in search.rank_lines(state, 4) if l.actions[0].kind == "Attack")
        self.assertEqual(len(line.actions), 1)

    def test_a_wave_among_enemies_still_there_doesnt_end_the_line(self):
        # The Ashigaru stays out of reach; the wave lands on the first turn, and the line plays on at a discount.
        state = make_state(hero_cell=0, enemies=[enemy(4, hp=9)])
        state.turns_until_wave = 1
        line = search.rank_lines(state, 3)[0]
        self.assertEqual(len(line.actions), 3)
        self.assertEqual(search._factor(state), WEIGHTS["future_discount"])


class WaveDelayGuaranteeTest(unittest.TestCase):
    """Putting off the kill that clears the room, to meet the wave set up, only when sure to be safe until it lands."""

    def board(self, known=True, held=False):
        foe = ashigaru(3, queue=[], action="Wait")
        foe.hp = 2
        state = make_state(hero_cell=2, enemies=[foe], queue=["Swirl"])
        state.turns_until_wave = 9
        if not known:
            foe.kind = "Mystery"  # No AI ported: its choices are guessed.
        if held:
            state.wave_held_at = 1
        return state

    def delay(self, state):
        return search.Line([Action("Wait"), Action("Attack")], 0.0, ["Wait", "Attack"], {}, 0.0, False)

    def test_a_known_safe_delay_is_allowed(self):
        state = self.board()
        self.assertTrue(search._clears_room(state, Action("Attack")))
        self.assertTrue(search._guaranteed_delay(state, self.delay(state)))

    def test_not_through_a_guessed_turn(self):
        state = self.board(known=False)
        self.assertFalse(search._guaranteed_delay(state, self.delay(state)))

    def test_not_when_a_crowded_room_holds_the_wave(self):
        state = self.board(held=True)
        self.assertFalse(search._guaranteed_delay(state, self.delay(state)))

    def test_not_if_the_wave_doesnt_land_within_the_line(self):
        state = self.board()
        line = search.Line([Action("Wait")], 0.0, ["Wait"], {}, 0.0, False)
        self.assertFalse(search._guaranteed_delay(state, line))

    def test_an_unsafe_delay_ranks_below_clearing_the_room(self):
        state = self.board(known=False)
        lines = search.rank_lines(state, 3)
        self.assertTrue(search._clears_room(state, lines[0].actions[0]))


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

    def test_of_equal_lines_the_one_loading_now_wins(self):
        # logs/run17: Wait, listed first, won exact ties with Back Shadow Dash ready, loading it later in the line.
        # The player: loading now is never worse, and the next turn may show a play that wants it loaded.
        import json
        from pathlib import Path
        from rules import state_from_log
        rows = (Path(__file__).resolve().parent.parent / "research" / "logs" / "run17" / "state.jsonl").read_text(
            encoding="utf-8").splitlines()
        row = next(json.loads(r) for r in rows if '"seq":716,' in r)
        lines = search.rank_lines(state_from_log(row), 4)
        waits = next(l for l in lines if l.labels[0] == "Wait")
        self.assertEqual(lines[0].labels[0], "PlayTile BackShadowDash")
        self.assertEqual(round(lines[0].score, 2), round(waits.score, 2))


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

    def test_an_immediate_potion_waits_for_the_turn_of_the_hit(self):
        # The Ashigaru steps in this turn and strikes the next: nothing stops it, but a Shield drunk now does no more
        # than one drunk next turn.
        foe = ashigaru(2, queue=[KATANA], action="MoveLeft")
        foe.hp = foe.max_hp = 9
        state = make_state(hero_cell=0, enemies=[foe], swap_charge=0)
        state.potions = ["Shield"]
        self.assertIsNone(self.choose(state)[0])
        after, _ = step(state, Action("Wait"))
        self.assertEqual(self.choose(after)[0], "Shield")

    def test_of_the_save_potions_the_shield_goes_first(self):
        # logs/run17 turn 18: Rain of Mirrors was drunk with a Shield that saved as much. Flipping everyone also tends
        # to leave the board better, which is why the player keeps it for worse spots.
        name, why = self.choose(self.board(["RainOfMirrors", "Shield"]))
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
