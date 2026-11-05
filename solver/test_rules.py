"""Tests for rules the fight logs haven't exercised yet, such as Swap and flipping.

Run with: python solver/test_rules.py
"""
import unittest

from evaluator import leaf_terms, rank_actions, unanswerable_damage
from rules import Action, Agent, Attack, State, Tile, legal_actions, step

SWIRL = Attack("Swirl", 2, [-1, 1])
ARROW = Attack("Arrow", 2, list(range(1, 11)))
KATANA = Attack("Katana", 2, [1])


def make_state(hero_cell=2, facing=1, enemies=(), swap_charge=4, queue=()):
    swirl = Tile(SWIRL, cooldown=3, charge=3)
    arrow = Tile(ARROW, cooldown=5, charge=5)
    tiles = [swirl, arrow]
    queue_tiles = []
    for tile in tiles:
        if tile.attack.name in queue:
            tile.in_queue = True
            queue_tiles.append(tile)
    hero = Agent("Wanderer", hero_cell, facing, 10, 10, queue=[t.attack for t in queue_tiles])
    return State(5, hero, list(enemies), tiles, queue_tiles, swap_charge, 4)


def enemy(cell, facing=-1, hp=3, action="Wait", queue=()):
    return Agent("Ashigaru", cell, facing, hp, 3, queue=list(queue), action=action)


class RulesTest(unittest.TestCase):
    def test_moving_away_dodges_a_telegraphed_attack(self):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[KATANA])])
        after, outcome = step(state, Action("MoveLeft"))
        self.assertEqual(outcome.hp_lost, 0)
        self.assertEqual(after.hero.cell, 1)

    def test_waiting_takes_a_telegraphed_attack(self):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[KATANA])])
        _, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.hp_lost, 2)

    def test_killing_an_enemy_cancels_its_attack(self):
        state = make_state(enemies=[enemy(3, hp=2, action="Attack", queue=[KATANA])], queue=["Swirl"])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.hp_lost, 0)
        self.assertEqual(outcome.kills, 1)
        self.assertEqual(after.enemies, [])

    def test_swap_trades_cells_keeps_facing_and_dodges_katana(self):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[KATANA])])
        after, outcome = step(state, Action("MoveRight"))
        self.assertEqual((after.hero.cell, after.enemies[0].cell), (3, 2))
        self.assertEqual(after.enemies[0].facing, -1)
        self.assertEqual(outcome.hp_lost, 0)
        self.assertEqual(after.swap_charge, 0)

    def test_swap_does_not_dodge_swirl(self):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[SWIRL])])
        _, outcome = step(state, Action("MoveRight"))
        self.assertEqual(outcome.hp_lost, 2)

    def test_swap_needs_charge_and_facing(self):
        allowed = make_state(enemies=[enemy(3)])
        self.assertIn(Action("MoveRight"), legal_actions(allowed, allow_swap=True))
        blocked = make_state(enemies=[enemy(3)], swap_charge=3)
        self.assertNotIn(Action("MoveRight"), legal_actions(blocked, allow_swap=True))
        wrong_way = make_state(facing=-1, enemies=[enemy(3)])
        self.assertNotIn(Action("MoveRight"), legal_actions(wrong_way, allow_swap=True))

    def test_swap_is_off_by_default_for_v0(self):
        state = make_state(enemies=[enemy(3)])
        self.assertNotIn(Action("MoveRight"), legal_actions(state))

    def test_swap_cooldown_skips_the_turn_it_was_used(self):
        state = make_state(enemies=[enemy(3)])
        after, _ = step(state, Action("MoveRight"))
        self.assertEqual(after.swap_charge, 0)
        after, _ = step(after, Action("Wait"))
        self.assertEqual(after.swap_charge, 1)

    def test_missed_attack_still_starts_the_cooldown(self):
        state = make_state(enemies=[enemy(0)], queue=["Swirl"])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.wasted_attacks, 1)
        self.assertEqual(after.tiles[0].charge, 0)
        after, _ = step(after, Action("Wait"))
        self.assertEqual(after.tiles[0].charge, 1)

    def test_enemy_swirl_hits_its_ally(self):
        state = make_state(hero_cell=0, enemies=[
            enemy(1, facing=-1, action="Attack", queue=[SWIRL]), enemy(2)])
        after, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.hp_lost, 2)
        self.assertEqual(outcome.friendly_damage, 2)
        self.assertEqual(next(e for e in after.enemies if e.cell == 2).hp, 1)

    def test_enemy_cannot_walk_into_the_hero(self):
        state = make_state(enemies=[enemy(3, action="MoveLeft")])
        after, _ = step(state, Action("Wait"))
        self.assertEqual(after.enemies[0].cell, 3)

    def test_queue_fires_in_order_and_retargets(self):
        # Arrow kills the adjacent enemy first, so Swirl then has nothing to hit.
        state = make_state(enemies=[enemy(3, hp=2)], queue=[])
        state.hero.queue = [ARROW, SWIRL]
        state.queue_tiles = [state.tiles[1], state.tiles[0]]
        state.tiles[0].in_queue = state.tiles[1].in_queue = True
        _, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.kills, 1)
        self.assertEqual(outcome.wasted_attacks, 1)


class EvaluatorTest(unittest.TestCase):
    def test_kills_an_attacker_it_can_reach(self):
        state = make_state(enemies=[enemy(3, hp=2, action="Attack", queue=[KATANA])], queue=["Swirl"])
        self.assertEqual(rank_actions(state)[0].actions[0].kind, "Attack")

    def test_does_not_stand_still_under_attack(self):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[KATANA])])
        self.assertNotEqual(rank_actions(state)[0].actions[0].kind, "Wait")

    def test_plans_for_a_target_behind_the_hero(self):
        # With a queued Arrow and an enemy only behind, flipping beats firing into empty cells.
        state = make_state(enemies=[enemy(0, facing=1, hp=2)], queue=["Arrow"])
        ranked = [line.actions[0].kind for line in rank_actions(state, depth=2)]
        self.assertLess(ranked.index("Flip"), ranked.index("Attack"))

    def test_in_range_is_fine_when_the_hero_can_step_away(self):
        state = make_state(enemies=[enemy(3, queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 0)

    def test_cornered_with_nothing_ready_has_no_answer(self):
        # Hero in the corner, with the only free neighbour blocked by the enemy itself.
        state = make_state(hero_cell=0, facing=1, enemies=[enemy(1, queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 2)

    def test_cornered_but_able_to_kill_has_an_answer(self):
        state = make_state(hero_cell=0, facing=1, enemies=[enemy(1, hp=2, queue=[KATANA])], queue=["Swirl"])
        self.assertEqual(unanswerable_damage(state), 0)

    def test_stepping_into_another_threat_is_not_an_answer(self):
        state = make_state(hero_cell=2, enemies=[
            enemy(0, facing=1, queue=[Attack("Long", 2, [1, 2, 3])]), enemy(3, queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 4)

    def test_closes_in_rather_than_running_from_a_loaded_enemy(self):
        # Nothing threatens the hero yet, and an enemy is out of reach with tiles on cooldown.
        state = make_state(hero_cell=2, enemies=[enemy(4, queue=[KATANA])])
        for tile in state.tiles:
            tile.charge = 0
        self.assertEqual(rank_actions(state, depth=1)[0].actions[0].kind, "MoveRight")

    def test_prefers_facing_the_target(self):
        state = make_state(hero_cell=2, facing=1, enemies=[enemy(1, facing=1)])
        for tile in state.tiles:
            tile.charge = 0
        self.assertEqual(rank_actions(state, depth=1)[0].actions[0].kind, "Flip")

    def test_wave_pressure_grows_as_the_wave_nears(self):
        far = make_state(enemies=[enemy(3)])
        far.turns_until_wave = 6
        near = make_state(enemies=[enemy(3)])
        near.turns_until_wave = 1
        self.assertLess(leaf_terms(near)["wave_pressure"], leaf_terms(far)["wave_pressure"])


if __name__ == "__main__":
    unittest.main()
