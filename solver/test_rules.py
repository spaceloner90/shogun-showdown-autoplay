"""Tests for rules the fight logs haven't exercised yet, such as Swap and flipping.

Run with: python solver/test_rules.py
"""
import dataclasses
import unittest

from evaluator import WEIGHTS, _volleys, _has_way_out, potion_plan, _threat_damage, ideal_target, leaf_terms, rank_actions, unanswerable_damage
from rules import ICE_TURNS, can_use_special, fight_won, SIMULATED_POTIONS, Action, Agent, Attack, State, Tile, apply_potion, is_tank, legal_actions, state_from_log, step, unmodeled_content

SWIRL = Attack("Swirl", 2, [-1, 1])
ARROW = Attack("Arrow", 2, list(range(1, 11)), first_target=True)
KATANA = Attack("Katana", 2, [1], first_target=True)
TETSUBO = Attack("Tetsubo", 4, [1], first_target=True)
CHARGE = Attack("Charge", 1, list(range(1, 11)), first_target=True)


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

    def test_swap_is_considered_and_labelled(self):
        state = make_state(enemies=[enemy(3)])
        self.assertIn(Action("MoveRight"), legal_actions(state))
        self.assertEqual(Action("MoveRight").label(state), "MoveRight (swap)")

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

    def test_a_full_queue_can_fire_fifteen_ways_starting_as_it_stands(self):
        state = make_state(queue=["Swirl", "Arrow"])
        third = Tile(TETSUBO, cooldown=7, charge=7, in_queue=True)
        state.tiles.append(third)
        state.queue_tiles.append(third)
        state.hero.queue.append(TETSUBO)
        attacks = [a for a in legal_actions(state) if a.kind == "Attack"]
        self.assertEqual(len(attacks), 15)
        self.assertEqual(attacks[0], Action("Attack"))
        self.assertEqual(len(set(attacks)), 15)

    def test_firing_one_tile_sends_the_other_back_charged(self):
        state = make_state(enemies=[enemy(3)], queue=["Swirl", "Arrow"])
        after, outcome = step(state, Action("Attack", order=(0,)))
        self.assertEqual(outcome.enemy_damage, 2)
        self.assertEqual(after.hero.queue, [])
        self.assertEqual(after.tiles[0].charge, 0)
        self.assertTrue(after.tiles[1].ready)
        self.assertFalse(after.tiles[1].in_queue)

    def test_firing_order_can_change_the_result(self):
        # Swirl first kills the 2hp enemy ahead, leaving Arrow nothing to hit. Arrow first does the
        # same kill, and Swirl still hits the enemy behind, so neither attack is wasted.
        behind = enemy(1, facing=1)
        state = make_state(enemies=[behind, enemy(3, hp=2)], queue=["Swirl", "Arrow"])
        _, swirl_first = step(state, Action("Attack"))
        _, arrow_first = step(state, Action("Attack", order=(1, 0)))
        self.assertEqual(swirl_first.wasted_attacks, 1)
        self.assertEqual(arrow_first.wasted_attacks, 0)
        self.assertEqual(arrow_first.kills, 1)
        self.assertEqual(arrow_first.enemy_damage, 4)

    def test_charge_stops_at_the_first_target_and_moves_the_attacker(self):
        ally = enemy(4, facing=1)
        state = make_state(hero_cell=2, enemies=[enemy(0, facing=1, action="Attack", queue=[CHARGE]), ally])
        after, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.hp_lost, 1)
        self.assertEqual(outcome.friendly_damage, 0)
        self.assertEqual(after.enemies[0].cell, 1)

    def test_charge_hits_an_ally_in_the_way(self):
        state = make_state(hero_cell=4, facing=-1, enemies=[enemy(0, facing=1, action="Attack", queue=[CHARGE]), enemy(2, facing=1)])
        _, outcome = step(state, Action("Wait"))
        self.assertEqual((outcome.hp_lost, outcome.friendly_damage), (0, 1))

    def test_hero_charge_moves_the_hero_next_to_the_target(self):
        state = make_state(hero_cell=0, facing=1, enemies=[enemy(4)])
        state.tiles[0].attack = CHARGE
        state.tiles[0].in_queue = True
        state.queue_tiles = [state.tiles[0]]
        state.hero.queue = [CHARGE]
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.hero.cell, outcome.enemy_damage), (3, 1))

    def _fire_back_charge(self, hero_cell, facing, enemies, cells=5, also=()):
        back = Attack("BackCharge", 3, list(range(1, 11)), first_target=True)
        state = make_state(hero_cell=hero_cell, facing=facing, enemies=enemies)
        state.cells = cells
        state.tiles[0].attack = back
        state.tiles[0].in_queue = True
        state.queue_tiles = [state.tiles[0]]
        state.hero.queue = [back]
        for name in also:
            tile = next(t for t in state.tiles if t.attack.name == name)
            tile.in_queue = True
            state.queue_tiles.append(tile)
            state.hero.queue.append(tile.attack)
        return state

    def test_back_charge_runs_backward_to_the_target_without_turning(self):
        state = self._fire_back_charge(4, 1, [enemy(1, hp=9)])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.hero.cell, after.hero.facing, outcome.enemy_damage), (2, 1, 3))

    def test_back_charge_hits_an_adjacent_target_without_moving(self):
        state = self._fire_back_charge(3, 1, [enemy(2, hp=9)])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.hero.cell, outcome.enemy_damage), (3, 3))

    def test_back_charge_ignores_targets_ahead(self):
        state = self._fire_back_charge(2, 1, [enemy(3, hp=9)])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.hero.cell, outcome.enemy_damage), (0, 0))

    def test_back_charge_with_nothing_behind_is_a_retreat_not_a_waste(self):
        state = self._fire_back_charge(2, 1, [enemy(4, hp=9)])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.hero.cell, outcome.wasted_attacks), (0, 0))

    def test_back_charge_against_the_wall_does_nothing_but_uses_the_tile(self):
        state = self._fire_back_charge(0, 1, [enemy(3, hp=9)])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.hero.cell, outcome.enemy_damage, outcome.wasted_attacks), (0, 0, 1))
        self.assertEqual(after.tiles[0].charge, 0)

    def test_back_charge_dodges_a_telegraphed_attack(self):
        state = self._fire_back_charge(3, 1, [enemy(4, action="Attack", queue=[KATANA])])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.hero.cell, outcome.hp_lost), (0, 0))

    def test_tiles_after_a_back_charge_fire_from_where_it_landed(self):
        # Facing right, it runs left to cell 2, next to the enemy on cell 1. Swirl then reaches it.
        state = self._fire_back_charge(4, 1, [enemy(1, hp=9)], also=("Arrow",))
        state.tiles[1].attack = SWIRL
        state.hero.queue[1] = SWIRL
        _, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.enemy_damage, 5)

    def test_a_charge_that_does_nothing_is_still_a_waste(self):
        state = make_state(hero_cell=4, facing=1, enemies=[enemy(0)])
        state.tiles[0].attack = CHARGE
        state.tiles[0].in_queue = True
        state.queue_tiles = [state.tiles[0]]
        state.hero.queue = [CHARGE]
        _, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.wasted_attacks, 1)

    def test_plain_dash_moves_to_the_last_free_cell_and_hits_nothing(self):
        dash_attack = Attack("Dash", 0, list(range(1, 11)))
        state = make_state(hero_cell=0, facing=1, enemies=[enemy(4)])
        state.tiles[0].attack = dash_attack
        state.tiles[0].in_queue = True
        state.queue_tiles = [state.tiles[0]]
        state.hero.queue = [dash_attack]
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.hero.cell, outcome.enemy_damage, outcome.wasted_attacks), (3, 0, 0))

    def _fire_shadow_dash(self, hero_cell, enemies):
        shadow = Attack("ShadowDash", 2, list(range(1, 11)), first_target=True)
        state = make_state(hero_cell=hero_cell, facing=1, enemies=enemies)
        state.tiles[0].attack = shadow
        state.tiles[0].in_queue = True
        state.queue_tiles = [state.tiles[0]]
        state.hero.queue = [shadow]
        return step(state, Action("Attack"))

    def test_shadow_dash_passes_through_and_hits_everyone_in_a_row(self):
        after, outcome = self._fire_shadow_dash(1, [enemy(2), enemy(3)])
        self.assertEqual((after.hero.cell, outcome.enemy_damage), (4, 4))

    def test_shadow_dash_reaches_a_target_at_any_distance(self):
        after, outcome = self._fire_shadow_dash(0, [enemy(2)])
        self.assertEqual((after.hero.cell, outcome.enemy_damage), (3, 2))

    def test_shadow_dash_fails_with_no_free_cell_behind_the_target(self):
        # There's a free cell before the target, but only one behind it counts.
        after, outcome = self._fire_shadow_dash(2, [enemy(4)])
        self.assertEqual((after.hero.cell, outcome.enemy_damage, outcome.wasted_attacks), (2, 0, 1))
        self.assertEqual(after.tiles[0].charge, 0)

    def test_shadow_dash_stops_behind_the_first_target_with_room(self):
        after, outcome = self._fire_shadow_dash(0, [enemy(1), enemy(3)])
        self.assertEqual((after.hero.cell, outcome.enemy_damage), (2, 2))

    def test_shadow_dash_needs_a_target(self):
        after, outcome = self._fire_shadow_dash(1, [enemy(0, facing=1)])
        self.assertEqual((after.hero.cell, outcome.enemy_damage), (1, 0))

    def test_two_tiles_of_a_name_are_told_apart(self):
        weak = Attack("Swirl", 2, [-1, 1])
        strong = Attack("Swirl", 3, [-1, 1])
        state = make_state(enemies=[enemy(3)])
        state.tiles = [Tile(weak, 3, 3), Tile(strong, 3, 3)]
        self.assertEqual(Action("PlayTile", 1).label(state), "PlayTile Swirl (3)")
        self.assertNotEqual(Action("PlayTile", 0).label(state), Action("PlayTile", 1).label(state))

    def test_a_free_play_tile_is_not_loaded_ahead_of_time(self):
        state = make_state(enemies=[enemy(3)])
        state.tiles[0].free_play = True
        kinds = [(a.kind, a.tile) for a in legal_actions(state)]
        self.assertNotIn(("PlayTile", 0), kinds)
        self.assertIn(("PlayTile", 1), kinds)

    def test_a_free_play_tile_can_attack_from_hand_with_an_empty_queue(self):
        state = make_state(enemies=[enemy(3)])
        state.tiles[0].free_play = True
        attacks = [a for a in legal_actions(state) if a.kind == "Attack"]
        self.assertEqual(attacks, [Action("Attack", order=(0,))])
        self.assertEqual(attacks[0].label(state), "Attack Swirl (free)")
        after, outcome = step(state, attacks[0])
        self.assertEqual(outcome.enemy_damage, 2)
        self.assertEqual(after.tiles[0].charge, 0)
        self.assertEqual(outcome.sent_back, 0)

    def test_a_free_play_tile_joins_a_queued_attack_in_any_order(self):
        state = make_state(enemies=[enemy(3)], queue=["Arrow"])
        state.tiles[0].free_play = True
        orders = {a.order for a in legal_actions(state) if a.kind == "Attack"}
        self.assertEqual(orders, {None, (1, 0), (0, 1), (0,)})
        self.assertEqual(Action("Attack", order=(0, 1)).label(state), "Attack Swirl (free) > Arrow")
        _, outcome = step(state, Action("Attack", order=(0, 1)))
        self.assertEqual(outcome.enemy_damage, 3)  # The 3hp enemy has only 3 to lose.
        self.assertEqual(outcome.kills, 1)

    def test_a_full_queue_can_trade_a_tile_for_a_free_one(self):
        state = make_state(enemies=[enemy(3)], queue=["Swirl", "Arrow"])
        third = Tile(TETSUBO, cooldown=7, charge=7, in_queue=True)
        fourth = Tile(KATANA, cooldown=0, charge=0, free_play=True)
        state.tiles += [third, fourth]
        state.queue_tiles.append(third)
        state.hero.queue.append(TETSUBO)
        orders = [a.order for a in legal_actions(state) if a.kind == "Attack"]
        self.assertTrue(all(o is None or len(o) <= 3 for o in orders))
        _, outcome = step(state, Action("Attack", order=(3, 0, 1)))
        self.assertEqual(outcome.sent_back, 1)

    def test_a_free_play_tile_on_cooldown_cannot_join(self):
        state = make_state(enemies=[enemy(3)], queue=["Arrow"])
        state.tiles[0].free_play = True
        state.tiles[0].charge = 1
        self.assertEqual({a.order for a in legal_actions(state) if a.kind == "Attack"}, {None, })

    def test_attack_labels_describe_the_edits(self):
        state = make_state(enemies=[enemy(3)], queue=["Swirl", "Arrow"])
        self.assertEqual(Action("Attack").label(state), "Attack")
        self.assertEqual(Action("Attack", order=(1, 0)).label(state), "Attack Arrow > Swirl")
        self.assertEqual(Action("Attack", order=(1,)).label(state), "Attack Arrow (Swirl to hand)")


class CurseTest(unittest.TestCase):
    CURSED_ARROW = Attack("Arrow", 2, list(range(1, 11)), first_target=True, effect="Curse")

    def _with_curse_arrow(self, enemies, queue=("Arrow",)):
        state = make_state(enemies=enemies, queue=queue)
        state.tiles[1].attack = self.CURSED_ARROW
        state.hero.queue = [t.attack for t in state.queue_tiles]
        return state

    def test_a_curse_doubles_one_hit_and_is_used_up(self):
        target = enemy(3, hp=9)
        target.curse = True
        state = make_state(enemies=[target], queue=["Swirl", "Arrow"])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.enemy_damage, 6)  # Swirl doubled to 4, then Arrow's normal 2.
        self.assertFalse(after.enemies[0].curse)

    def test_a_curse_does_not_double_the_attack_that_applied_it(self):
        after, outcome = step(self._with_curse_arrow([enemy(3, hp=9)]), Action("Attack"))
        self.assertEqual(outcome.enemy_damage, 2)
        self.assertTrue(after.enemies[0].curse)

    def test_firing_order_decides_whether_the_curse_pays_off_this_attack(self):
        curse_first = self._with_curse_arrow([enemy(3, hp=9)], queue=("Swirl", "Arrow"))
        _, swirl_then_curse = step(curse_first, Action("Attack"))
        _, curse_then_swirl = step(curse_first, Action("Attack", order=(1, 0)))
        self.assertEqual(swirl_then_curse.enemy_damage, 4)
        self.assertEqual(curse_then_swirl.enemy_damage, 6)

    def test_a_killed_enemy_stays_dead_and_uncursed(self):
        after, outcome = step(self._with_curse_arrow([enemy(3, hp=2)]), Action("Attack"))
        self.assertEqual(outcome.kills, 1)
        self.assertEqual(after.enemies, [])

    def test_swirl_doubles_each_cursed_target_separately(self):
        left, right = enemy(1, facing=1, hp=9), enemy(3, hp=9)
        left.curse = right.curse = True
        state = make_state(enemies=[left, right], queue=["Swirl"])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.enemy_damage, 8)
        self.assertFalse(any(e.curse for e in after.enemies))

    def test_a_shield_blocks_the_hit_but_keeps_the_curse_and_takes_the_effect(self):
        kept = enemy(3, hp=9)
        kept.curse = True
        kept.shield = True
        state = make_state(enemies=[kept], queue=["Swirl"])
        after, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.enemy_damage, 0)
        self.assertFalse(after.enemies[0].shield)
        self.assertTrue(after.enemies[0].curse)
        fresh = enemy(3, hp=9)
        fresh.shield = True
        after, _ = step(self._with_curse_arrow([fresh]), Action("Attack"))
        self.assertTrue(after.enemies[0].curse)

    def test_a_cursed_ally_takes_double_from_enemies_too(self):
        ally = enemy(2, facing=1, hp=9)
        ally.curse = True
        state = make_state(hero_cell=4, facing=-1, enemies=[enemy(1, facing=1, action="Attack", queue=[KATANA]), ally])
        after, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.friendly_damage, 4)
        self.assertFalse(after.enemies[1].curse)
        self.assertEqual(leaf_terms(after)["curse"], 0)

    def test_a_curse_is_worthless_when_every_tile_already_kills(self):
        state = make_state(enemies=[enemy(3, hp=2)])
        state.enemies[0].curse = True
        self.assertEqual(leaf_terms(state)["curse"], 0)

    def test_a_curse_counts_its_best_use_even_when_another_tile_kills_anyway(self):
        # Swirl kills this 3hp enemy anyway, but the curse lets Arrow kill it too, leaving Swirl free: 2 damage
        # becomes a kill, 20 becomes 90, and half of that 70 counts. Another tile can only add (rule 1).
        state = make_state(enemies=[enemy(3, hp=3)])
        state.enemies[0].curse = True
        state.tiles[0].attack = Attack("Swirl", 3, [-1, 1])
        self.assertEqual(leaf_terms(state)["curse"], 35)

    def test_a_curse_counts_when_it_makes_a_kill_available_sooner(self):
        # Swirl would kill, but it's cooling down. The curse lets the ready Arrow do it now.
        state = make_state(enemies=[enemy(3, hp=3)])
        state.enemies[0].curse = True
        state.tiles[0].attack = Attack("Swirl", 3, [-1, 1])
        state.tiles[0].charge = 0
        self.assertGreater(leaf_terms(state)["curse"], 0)

    def test_a_curse_gains_only_up_to_the_health_left(self):
        # Doubling 2 to 4 only adds 1 real damage on a 3hp enemy, but the kill is worth having.
        barely = make_state(enemies=[enemy(3, hp=3)])
        barely.enemies[0].curse = True
        for tile in barely.tiles:
            tile.attack = Attack(tile.attack.name, 2, tile.attack.range)
        full = make_state(enemies=[enemy(3, hp=4)])
        full.enemies[0].curse = True
        self.assertLess(leaf_terms(barely)["curse"], leaf_terms(full)["curse"])

    def test_a_cursed_hero_takes_double_once(self):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[KATANA, KATANA])])
        state.hero.curse = True
        self.assertEqual(_threat_damage(state, 2), 6)
        after, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.hp_lost, 6)
        self.assertFalse(after.hero.curse)

    def test_a_curse_is_worth_something_on_a_survivor(self):
        cursed = make_state(enemies=[enemy(3, hp=9)])
        cursed.enemies[0].curse = True
        plain = make_state(enemies=[enemy(3, hp=9)])
        self.assertGreater(leaf_terms(cursed)["curse"], 0)
        self.assertEqual(leaf_terms(plain)["curse"], 0)

    def test_a_curse_is_worth_more_when_it_turns_a_wound_into_a_kill(self):
        kill = make_state(enemies=[enemy(3, hp=4)])
        kill.enemies[0].curse = True
        wound = make_state(enemies=[enemy(3, hp=9)])
        wound.enemies[0].curse = True
        self.assertGreater(leaf_terms(kill)["curse"], leaf_terms(wound)["curse"])

    def test_a_curse_is_worth_less_while_every_tile_is_cooling_down(self):
        ready = make_state(enemies=[enemy(3, hp=9)])
        ready.enemies[0].curse = True
        cooling = make_state(enemies=[enemy(3, hp=9)])
        cooling.enemies[0].curse = True
        for tile in cooling.tiles:
            tile.charge = 0
        self.assertLess(leaf_terms(cooling)["curse"], leaf_terms(ready)["curse"])

    def test_a_loaded_volley_that_uses_the_curse_is_scored_without_it(self):
        # The curse counts as kept, and the stack counts the volley that uses it against the board it leaves, where
        # the curse is gone: firing Swirl into it doubles 2 to 4, worth 20 more and 8 less for HP left in the room,
        # but loses the 10 the curse was worth kept.
        state = make_state(enemies=[enemy(3, hp=9)], queue=["Swirl"])
        state.enemies[0].curse = True
        terms = leaf_terms(state)
        plain = make_state(enemies=[enemy(3, hp=9)], queue=["Swirl"])
        self.assertEqual(terms["curse"], 10)
        self.assertAlmostEqual(terms["stack"] - leaf_terms(plain)["stack"], 0.6 * (20 + 8 - 10))

    def test_fires_the_curse_first_when_stacked(self):
        state = self._with_curse_arrow([enemy(3, hp=9)], queue=("Swirl", "Arrow"))
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.actions[0], Action("Attack", order=(1, 0)))

    def test_understood_skills_get_no_warning_and_others_do(self):
        row = {"tiles": [], "hero": {"queue": []}, "enemies": [],
               "skills": [{"name": "Fortress", "level": 1}, {"name": "Sniper", "level": 1}, {"name": "Karma", "level": 1}]}
        self.assertEqual(unmodeled_content(row), ["skill Karma"])

    def test_curse_gets_no_warning(self):
        row = {"tiles": [{"attack": {"name": "Arrow", "effect": "Curse", "tileEffect": "None"}}],
               "hero": {"queue": [], "curse": True}, "enemies": [], "skills": []}
        self.assertEqual(unmodeled_content(row), [])


HOOK = Attack("GrapplingHook", 1, list(range(1, 11)), first_target=True)
SPEAR = Attack("Spear", 2, [1, 2])
ALLY_SHIELD = Attack("ShieldAllied", 0, list(range(1, 11)))
SELF_SHIELD = Attack("Shield", 0, [], first_target=True)


class GrapplingHookTest(unittest.TestCase):
    def _hooked(self, hero_cell=1, **kwargs):
        return make_state(hero_cell=hero_cell, swap_charge=0, enemies=[
            enemy(4, action="Attack", queue=[HOOK, KATANA], **kwargs)])

    def test_the_hook_pulls_the_hero_next_to_the_grappler_for_the_katana(self):
        after, outcome = step(self._hooked(), Action("Wait"))
        self.assertEqual((after.hero.cell, outcome.hp_lost), (3, 3))

    def test_a_shield_blocks_the_hooks_damage_but_not_its_pull(self):
        # As played: the shield took the hook, the pull still happened, and the Katana hit for 2.
        state = self._hooked()
        state.hero.shield = True
        after, outcome = step(state, Action("Wait"))
        self.assertEqual((after.hero.cell, after.hero.shield, outcome.hp_lost), (3, False, 2))

    def test_stepping_back_does_not_escape_it(self):
        state = self._hooked()
        self.assertEqual(_threat_damage(state, 0), 3)
        self.assertEqual(unanswerable_damage(state), 3)

    def test_an_enemy_in_the_way_takes_the_hook_instead(self):
        state = make_state(hero_cell=0, swap_charge=0, facing=1, enemies=[
            enemy(2, facing=1, hp=9), enemy(4, action="Attack", queue=[HOOK, KATANA])])
        after, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.hp_lost, 0)
        self.assertEqual(sorted(e.cell for e in after.enemies), [3, 4])
        self.assertEqual(outcome.friendly_damage, 3)

    def test_killing_the_grappler_stops_it(self):
        state = make_state(hero_cell=3, enemies=[enemy(4, hp=2, action="Attack", queue=[HOOK, KATANA])], queue=["Swirl"])
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.actions[0].kind, "Attack")
        self.assertEqual(best.terms.get("hp_lost", 0), 0)

    def test_a_heavy_target_is_not_pulled_or_swapped(self):
        heavy = enemy(3)
        heavy.movable = False
        state = make_state(hero_cell=2, enemies=[heavy])
        self.assertNotIn(Action("MoveRight"), legal_actions(state))
        state = make_state(hero_cell=0, facing=1, enemies=[heavy])
        state.tiles[0].attack = HOOK
        state.tiles[0].in_queue = True
        state.queue_tiles = [state.tiles[0]]
        state.hero.queue = [HOOK]
        after, _ = step(state, Action("Attack"))
        self.assertEqual(after.enemies[0].cell, 3)


class EnemyShieldTest(unittest.TestCase):
    def test_shield_protects_the_caster(self):
        after, _ = step(make_state(enemies=[enemy(4, action="Attack", queue=[SELF_SHIELD])]), Action("Wait"))
        self.assertTrue(after.enemies[0].shield)

    def test_shield_allied_goes_to_the_first_shieldless_ally_past_the_hero(self):
        shielded, target = enemy(1, facing=-1), enemy(0, facing=1)
        shielded.shield = True
        caster = enemy(4, action="Attack", queue=[ALLY_SHIELD])
        after, _ = step(make_state(hero_cell=2, enemies=[target, shielded, caster]), Action("Wait"))
        by_cell = {e.cell: e.shield for e in after.enemies}
        self.assertEqual(by_cell, {0: True, 1: True, 4: False})
        self.assertFalse(after.hero.shield)

    def test_shield_allied_with_nobody_to_shield_does_nothing(self):
        after, _ = step(make_state(enemies=[enemy(4, action="Attack", queue=[ALLY_SHIELD])]), Action("Wait"))
        self.assertFalse(after.enemies[0].shield)

    def test_a_shield_counts_as_extra_hp_equal_to_the_weakest_tile(self):
        shielded = make_state(enemies=[enemy(4, hp=3)])
        shielded.enemies[0].shield = True
        plain = make_state(enemies=[enemy(4, hp=3)])
        self.assertEqual(leaf_terms(shielded)["enemy_hp_left"] - leaf_terms(plain)["enemy_hp_left"], -8)

    def test_breaking_a_shield_earns_credit_for_a_lone_tile(self):
        target = enemy(3, hp=9)
        target.shield = True
        state = make_state(enemies=[target], queue=["Swirl"])
        line = next(l for l in rank_actions(state, depth=1) if l.actions[0].kind == "Attack")
        self.assertEqual(line.terms["shields_broken"], 20)

    def test_the_weakest_tile_breaks_the_shield_first(self):
        weak = Attack("Swirl", 1, [-1, 1])
        strong = Attack("Arrow", 4, [1], first_target=True)
        target = enemy(3, hp=4)
        target.shield = True
        state = make_state(enemies=[target], queue=["Swirl", "Arrow"])
        state.tiles[0].attack, state.tiles[1].attack = weak, strong
        state.hero.queue = [strong, weak]
        state.queue_tiles = [state.tiles[1], state.tiles[0]]
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.actions[0], Action("Attack", order=(0, 1)))
        self.assertGreater(best.terms["kills"], 0)

    def test_the_lower_effective_hp_is_the_target(self):
        shielded = enemy(1, facing=1, hp=2)
        shielded.shield = True
        state = make_state(hero_cell=2, enemies=[shielded, enemy(4, hp=3)])
        self.assertEqual(ideal_target(state).cell, 4)


class FreeCurseTileTest(unittest.TestCase):
    FREE_CURSE = Attack("Pike", 1, [1], first_target=True, effect="Curse")
    CURSED_SWIRL = Attack("Swirl", 2, [-1, 1], effect="Curse")

    def _state(self, hp=9):
        state = make_state(enemies=[enemy(3, hp=hp)], queue=["Swirl"])
        state.tiles[0].attack = self.CURSED_SWIRL
        state.hero.queue = [self.CURSED_SWIRL]
        state.tiles[1].attack = self.FREE_CURSE
        state.tiles[1].free_play = True
        return state

    def test_a_free_curse_doubles_a_curse_tile_which_re_applies_the_curse(self):
        after, outcome = step(self._state(), Action("Attack", order=(1, 0)))
        self.assertEqual(outcome.enemy_damage, 5)  # 1 from the free tile, then Swirl's 2 doubled to 4.
        self.assertTrue(after.enemies[0].curse)

    def test_a_curse_does_not_stack(self):
        state = self._state()
        state.enemies[0].curse = True
        after, outcome = step(state, Action("Attack", order=(1, 0)))
        self.assertEqual(outcome.enemy_damage, 6)  # 1 doubled to 2, re-cursed, then Swirl's 2 doubled to 4.
        self.assertTrue(after.enemies[0].curse)

    def test_it_finds_that_order_on_its_own(self):
        best = rank_actions(self._state(), depth=1)[0]
        self.assertEqual(best.actions[0], Action("Attack", order=(1, 0)))
        self.assertEqual(best.labels[0], "Attack Pike (free) > Swirl")


class CurseAttackTest(unittest.TestCase):
    """The game's own Curse tile: no damage, reaches the first target at range."""
    CURSE = Attack("Curse", 0, list(range(1, 11)), first_target=True)

    def _with_free_curse(self, enemies, queue=()):
        state = make_state(enemies=enemies, queue=queue)
        state.tiles.append(Tile(self.CURSE, 7, 7, free_play=True))
        return state

    def test_it_curses_the_first_target_only_and_deals_nothing(self):
        state = self._with_free_curse([enemy(3, hp=9), enemy(4, hp=9)])
        after, outcome = step(state, Action("Attack", order=(2,)))
        self.assertEqual(outcome.enemy_damage, 0)
        self.assertEqual([e.curse for e in after.enemies], [True, False])
        self.assertEqual(after.tiles[2].charge, 0)

    def test_it_doesnt_touch_a_shield(self):
        shielded = enemy(3, hp=9)
        shielded.shield = True
        after, outcome = step(self._with_free_curse([shielded]), Action("Attack", order=(2,)))
        self.assertTrue(after.enemies[0].curse)
        self.assertTrue(after.enemies[0].shield)
        self.assertEqual(outcome.shields_broken, 0)

    def test_a_miss_goes_on_cooldown_and_counts_as_wasted(self):
        after, outcome = step(self._with_free_curse([enemy(0, facing=1)]), Action("Attack", order=(2,)))
        self.assertEqual(outcome.wasted_attacks, 1)
        self.assertEqual(after.tiles[2].charge, 0)

    def test_it_doubles_the_next_tile_in_the_stack(self):
        state = self._with_free_curse([enemy(3, hp=9)], queue=["Swirl"])
        _, outcome = step(state, Action("Attack", order=(2, 0)))
        self.assertEqual(outcome.enemy_damage, 4)

    def test_f1_adds_it_to_an_attack_that_turns_a_wound_into_a_kill(self):
        state = self._with_free_curse([enemy(3, hp=4)], queue=["Swirl"])
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.actions[0], Action("Attack", order=(2, 0)))
        self.assertEqual(best.labels[0], "Attack Curse (free) > Swirl")
        self.assertGreater(best.terms["kills"], 0)

    def test_it_gets_no_warning(self):
        row = {"tiles": [{"attack": {"name": "Curse", "effect": "None", "tileEffect": "FreePlay"}}],
               "hero": {"queue": []}, "enemies": [], "skills": []}
        self.assertEqual(unmodeled_content(row), [])


class QueueCapTest(unittest.TestCase):
    def _four_tiles(self):
        state = make_state(enemies=[enemy(3, hp=20)], queue=["Swirl", "Arrow"])
        state.tiles += [Tile(TETSUBO, 7, 7, free_play=True), Tile(KATANA, 0, 0, free_play=True)]
        return state

    def test_an_attack_never_fires_more_than_the_queue_holds(self):
        orders = [a.order for a in legal_actions(self._four_tiles()) if a.kind == "Attack"]
        self.assertEqual(max(len(o) for o in orders if o), 3)

    def test_the_stack_counts_only_the_best_three(self):
        terms = leaf_terms(self._four_tiles())
        self.assertEqual(terms["loaded"], 2.0 * (4 + 2 + 2))
        # The stack's volleys never fire more than three, though every size up to that is tried.
        self.assertEqual({len(v) for v in _volleys(self._four_tiles())}, {1, 2, 3})


class DamagingMoveTest(unittest.TestCase):
    def _swap_at(self, target, level=1):
        state = make_state(enemies=[target])
        state.swap_damage = level
        return state

    def test_a_swap_hits_the_enemy_for_the_skills_level(self):
        after, outcome = step(self._swap_at(enemy(3, hp=9), level=2), Action("MoveRight"))
        self.assertEqual((after.hero.cell, after.enemies[0].cell, after.enemies[0].hp, outcome.enemy_damage), (3, 2, 7, 2))

    def test_without_the_skill_a_swap_deals_nothing(self):
        after, outcome = step(make_state(enemies=[enemy(3, hp=9)]), Action("MoveRight"))
        self.assertEqual((after.enemies[0].hp, outcome.enemy_damage), (9, 0))

    def test_a_shield_blocks_it_and_a_curse_doubles_it(self):
        shielded = enemy(3, hp=9)
        shielded.shield = True
        after, outcome = step(self._swap_at(shielded), Action("MoveRight"))
        self.assertEqual((after.enemies[0].hp, after.enemies[0].shield, outcome.shields_broken), (9, False, 1))
        cursed = enemy(3, hp=9)
        cursed.curse = True
        after, _ = step(self._swap_at(cursed), Action("MoveRight"))
        self.assertEqual((after.enemies[0].hp, after.enemies[0].curse), (7, False))

    def test_killing_an_enemy_with_a_swap_stops_its_attack(self):
        target = enemy(3, hp=1, action="Attack", queue=[SWIRL])
        after, outcome = step(self._swap_at(target), Action("MoveRight"))
        self.assertEqual((after.hero.cell, after.enemies, outcome.kills, outcome.hp_lost), (3, [], 1, 0))

    def test_f1_uses_a_swap_as_a_free_kill(self):
        state = self._swap_at(enemy(3, hp=1))
        for tile in state.tiles:
            tile.charge = 0
        self.assertEqual(rank_actions(state, depth=1)[0].labels[0], "MoveRight (swap)")

    def test_a_killing_swap_answers_a_threat_a_plain_swap_cannot(self):
        # A plain swap lands next to the Swirl, which reaches both sides, and the corner leaves nowhere else.
        plain = make_state(hero_cell=0, enemies=[enemy(1, hp=1, queue=[SWIRL])])
        self.assertEqual(unanswerable_damage(plain), 2)
        killing = make_state(hero_cell=0, enemies=[enemy(1, hp=1, queue=[SWIRL])])
        killing.swap_damage = 1
        self.assertEqual(unanswerable_damage(killing), 0)

    def _archer_behind(self, blocker_hp, swap_damage):
        # An Archer on cell 0 is firing right. Swapping with the enemy on cell 3 puts it in the way.
        state = make_state(hero_cell=2, facing=1, enemies=[
            enemy(0, facing=1, action="Attack", queue=[ARROW]), enemy(3, facing=-1, hp=blocker_hp)])
        state.swap_damage = swap_damage
        return state

    def test_a_swap_blocks_a_projectile_with_the_enemy_it_passes(self):
        _, outcome = step(self._archer_behind(9, 1), Action("MoveRight"))
        self.assertEqual(outcome.hp_lost, 0)
        self.assertEqual(outcome.friendly_damage, 2)

    def test_a_swap_that_kills_the_blocker_lets_the_projectile_through(self):
        after, outcome = step(self._archer_behind(1, 1), Action("MoveRight"))
        self.assertEqual((outcome.kills, outcome.hp_lost), (1, 2))
        self.assertEqual(after.hero.cell, 3)

    def test_the_threat_check_knows_a_dead_blocker_blocks_nothing(self):
        # With nowhere safe to step, a swap is only a full answer if the blocker survives it.
        def left_over(blocker_hp):
            state = self._archer_behind(blocker_hp, 1)
            state.enemies[0].action = "Wait"
            return unanswerable_damage(state)
        self.assertEqual(left_over(9), 0)
        self.assertEqual(left_over(1), 2)

    def test_the_skill_level_is_read_from_the_log(self):
        row = {"cells": 5, "tiles": [], "enemies": [], "skills": [{"name": "DamagingMove", "level": 2}],
               "hero": {"kind": "H", "cell": 0, "facing": "Right", "hp": 9, "maxHp": 9, "shield": False, "queue": [],
                        "action": "Wait", "special": {"charge": 3, "cooldown": 3}}}
        self.assertEqual(state_from_log(row).swap_damage, 2)
        row["skills"] = []
        self.assertEqual(state_from_log(row).swap_damage, 0)

    def test_these_skills_get_no_warning(self):
        row = {"tiles": [], "hero": {"queue": []}, "enemies": [],
               "skills": [{"name": n, "level": 1} for n in ("DamagingMove", "QuickRecovery", "Healthy")]}
        self.assertEqual(unmodeled_content(row), [])


class ShieldValueTest(unittest.TestCase):
    def _attacked(self, shield=True, **kwargs):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[KATANA])], swap_charge=0, **kwargs)
        state.hero.shield = shield
        return state

    def test_a_shield_is_worth_about_one_hp(self):
        with_shield = make_state(enemies=[enemy(4)])
        with_shield.hero.shield = True
        without = make_state(enemies=[enemy(4)])
        self.assertEqual(leaf_terms(with_shield)["shield"] - leaf_terms(without)["shield"], 100)

    def test_dodges_rather_than_spend_a_shield_for_nothing(self):
        best = rank_actions(self._attacked(), depth=1)[0]
        self.assertEqual(best.actions[0].kind, "MoveLeft")
        self.assertEqual(best.terms["shield"], 85)

    def test_spends_a_shield_when_the_hit_cannot_be_dodged(self):
        # Backed into the corner with Swap charging, so the only question is what else to do.
        state = make_state(hero_cell=4, facing=-1, swap_charge=0,
                           enemies=[enemy(3, facing=1, action="Attack", queue=[KATANA])])
        state.hero.shield = True
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.terms.get("hp_lost", 0), 0)
        self.assertEqual(best.terms.get("shield", 0), 0)
        self.assertNotEqual(best.actions[0].kind, "Wait")

    def test_a_kill_that_removes_the_attacker_keeps_the_shield(self):
        state = make_state(enemies=[enemy(3, hp=2, action="Attack", queue=[KATANA])], queue=["Swirl"])
        state.hero.shield = True
        state.turns_until_wave = 5  # More to come, so the kill doesn't win the fight and the position still counts.
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.actions[0].kind, "Attack")
        self.assertEqual(best.terms["shield"], 85)


class EvaluatorTest(unittest.TestCase):
    def test_loads_a_ready_tile_rather_than_walking_with_an_empty_queue(self):
        state = make_state(hero_cell=0, facing=1, enemies=[enemy(4)])
        self.assertEqual(rank_actions(state, depth=1)[0].actions[0].kind, "PlayTile")

    def test_does_not_fire_a_tile_that_would_miss(self):
        # Only Swirl reaches the enemy behind, so Arrow should stay charged instead of being wasted.
        state = make_state(enemies=[enemy(1, facing=1, hp=2)], queue=["Swirl", "Arrow"])
        best = rank_actions(state, depth=1)[0].actions[0]
        self.assertEqual((best.kind, best.order), ("Attack", (0,)))

    def test_swaps_past_an_attacker_when_cornered(self):
        # The only way out of a telegraphed attack from a corner is through the attacker.
        state = make_state(hero_cell=0, facing=1, enemies=[enemy(1, action="Attack", queue=[KATANA])])
        best = rank_actions(state, depth=1)[0].actions[0]
        self.assertEqual(best.kind, "MoveRight")

    def test_kills_an_attacker_it_can_reach(self):
        state = make_state(enemies=[enemy(3, hp=2, action="Attack", queue=[KATANA])], queue=["Swirl"])
        self.assertEqual(rank_actions(state)[0].actions[0].kind, "Attack")

    def test_does_not_stand_still_under_attack(self):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[KATANA])])
        self.assertNotEqual(rank_actions(state)[0].actions[0].kind, "Wait")

    def test_plans_for_a_target_behind_the_hero(self):
        # With a queued Arrow and an enemy only behind, firing into empty cells isn't even considered, and the
        # flip that turns the Arrow onto it comes first.
        state = make_state(enemies=[enemy(0, facing=1, hp=2)], queue=["Arrow"])
        ranked = [line.actions[0].kind for line in rank_actions(state, depth=2)]
        self.assertNotIn("Attack", ranked)
        self.assertEqual(ranked[0], "Flip")

    def test_in_range_is_fine_when_the_hero_can_step_away(self):
        state = make_state(enemies=[enemy(3, queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 0)

    def test_cornered_with_nothing_ready_has_no_answer(self):
        # Hero in the corner, with the only free neighbour blocked by the enemy, and Swap charging.
        state = make_state(hero_cell=0, facing=1, swap_charge=0, enemies=[enemy(1, queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 2)

    def test_swapping_past_the_attacker_is_an_answer(self):
        state = make_state(hero_cell=0, facing=1, enemies=[enemy(1, queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 0)

    def test_a_partial_answer_counts_for_what_it_removes(self):
        # A dash can't be dodged, but killing the Spear carrier still removes 2 of the 3 damage.
        state = make_state(hero_cell=2, facing=1, swap_charge=0, queue=["Swirl"], enemies=[
            enemy(0, facing=1, queue=[CHARGE]), enemy(3, hp=2, queue=[Attack("Spear", 2, [1, 2])])])
        self.assertEqual(unanswerable_damage(state), 1)

    def test_an_enemy_in_the_way_blocks_a_first_target_threat(self):
        state = make_state(hero_cell=4, facing=-1, enemies=[enemy(0, facing=1, queue=[ARROW]), enemy(2, facing=1)])
        self.assertEqual(_threat_damage(state, 4), 0)

    def test_a_dash_carries_the_next_attack_in_its_queue_into_range(self):
        state = make_state(hero_cell=4, facing=-1, enemies=[enemy(0, facing=1, queue=[CHARGE, KATANA])])
        self.assertEqual(_threat_damage(state, 4), 3)

    def test_a_stack_counts_for_a_kill_a_step_away(self):
        # A 4hp enemy two cells away: Swirl and Arrow together kill it, from the next cell over.
        near = make_state(hero_cell=2, facing=1, queue=["Swirl", "Arrow"], enemies=[enemy(4, hp=4)])
        alone = make_state(hero_cell=2, facing=1, queue=["Arrow"], enemies=[enemy(4, hp=4)])
        self.assertGreater(leaf_terms(near)["stack"], leaf_terms(alone)["stack"] * 2)

    def test_closing_in_matters_less_with_nothing_to_threaten(self):
        def pull(charge):
            far, near = (make_state(hero_cell=cell, enemies=[enemy(4)]) for cell in (0, 3))
            for state in (far, near):
                for tile in state.tiles:
                    tile.charge = charge
            return leaf_terms(near)["reach"] - leaf_terms(far)["reach"]
        self.assertGreater(pull(5), pull(0))

    def test_a_free_play_tile_in_hand_counts_toward_the_stack(self):
        in_hand = make_state(hero_cell=2, facing=1, enemies=[enemy(3, hp=2)])
        in_hand.tiles[0].free_play = True
        empty = make_state(hero_cell=2, facing=1, enemies=[enemy(3, hp=2)])
        self.assertGreater(leaf_terms(in_hand)["stack"], leaf_terms(empty)["stack"])

    def test_a_free_play_tile_in_hand_is_an_answer_to_a_threat(self):
        state = make_state(hero_cell=0, facing=1, swap_charge=0, enemies=[enemy(1, hp=2, queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 2)
        state.tiles[0].free_play = True
        self.assertEqual(unanswerable_damage(state), 0)

    def test_fires_a_free_play_tile_to_kill_an_attacker(self):
        state = make_state(enemies=[enemy(3, hp=2, action="Attack", queue=[KATANA])])
        state.tiles[0].free_play = True
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.actions[0], Action("Attack", order=(0,)))
        self.assertEqual(best.terms.get("hp_lost", 0), 0)

    def test_cornered_but_able_to_kill_has_an_answer(self):
        state = make_state(hero_cell=0, facing=1, enemies=[enemy(1, hp=2, queue=[KATANA])], queue=["Swirl"])
        self.assertEqual(unanswerable_damage(state), 0)

    def test_stepping_into_another_threat_is_only_a_partial_answer(self):
        state = make_state(hero_cell=2, swap_charge=0, enemies=[
            enemy(0, facing=1, queue=[Attack("Long", 2, [1, 2, 3])]), enemy(3, queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 2)

    def test_doesnt_run_from_a_loaded_enemy(self):
        # Nothing threatens the hero yet, and an enemy is out of reach with tiles on cooldown. With nothing to hit it
        # with soon, closing in is worth less than standing next to it costs, so it waits rather than run.
        state = make_state(hero_cell=2, enemies=[enemy(4, queue=[KATANA])])
        for tile in state.tiles:
            tile.charge = 0
        self.assertNotEqual(rank_actions(state, depth=1)[0].actions[0].kind, "MoveLeft")

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


def fire(state, attack, cooldown=3):
    """The hero fires this attack, then the enemies take their turn."""
    tile = Tile(attack, cooldown=cooldown, charge=cooldown, in_queue=True)
    state.tiles.append(tile)
    state.hero.queue = [attack]
    state.queue_tiles = [tile]
    return step(state, Action("Attack"))


FAR = list(range(1, 11))
SMOKE_BOMB = Attack("SmokeBomb", 1, FAR, first_target=True)
BACK_SMOKE_BOMB = Attack("BackSmokeBomb", 1, [-r for r in FAR], first_target=True)
SWAP_TOSS = Attack("SwapToss", 0, [-1, 1])
MIRROR = Attack("Mirror", 0, [])
ORIGIN = Attack("OriginOfSymmetry", 0, [])
PUNCH = Attack("DragonPunch", 1, [1], first_target=True)
BARRAGE = Attack("CorruptedBarrage", 3, [-1, 1])


class SwapAndMoveAttackTest(unittest.TestCase):
    def test_smoke_bomb_trades_places_then_hits(self):
        after, outcome = fire(make_state(enemies=[enemy(4)]), SMOKE_BOMB)
        self.assertEqual((after.hero.cell, after.enemies[0].cell), (4, 2))
        self.assertEqual(outcome.enemy_damage, 1)

    def test_back_smoke_bomb_works_behind_the_hero(self):
        after, _ = fire(make_state(enemies=[enemy(0)]), BACK_SMOKE_BOMB)
        self.assertEqual((after.hero.cell, after.enemies[0].cell), (0, 2))

    def test_smoke_bomb_fails_on_a_heavy_target(self):
        heavy = enemy(4)
        heavy.movable = False
        after, outcome = fire(make_state(enemies=[heavy]), SMOKE_BOMB)
        self.assertEqual((after.hero.cell, after.enemies[0].hp, outcome.wasted_attacks), (2, 3, 1))

    def test_an_enemys_smoke_bomb_moves_the_hero(self):
        after, outcome = step(make_state(enemies=[enemy(4, action="Attack", queue=[SMOKE_BOMB])]), Action("Wait"))
        self.assertEqual((after.hero.cell, after.enemies[0].cell, outcome.hp_lost), (4, 2, 1))

    def test_swap_toss_trades_the_cells_either_side(self):
        tosser = enemy(3, action="Attack", queue=[SWAP_TOSS])
        after, outcome = step(make_state(enemies=[tosser, enemy(4)]), Action("Wait"))
        self.assertEqual(after.hero.cell, 4)
        self.assertEqual(sorted(e.cell for e in after.enemies), [2, 3])
        self.assertEqual(outcome.hp_lost, 0)

    def test_swap_toss_moves_someone_into_an_empty_cell(self):
        after, _ = step(make_state(enemies=[enemy(3, action="Attack", queue=[SWAP_TOSS])]), Action("Wait"))
        self.assertEqual(after.hero.cell, 4)

    def test_swap_toss_needs_both_cells_to_exist(self):
        after, _ = step(make_state(hero_cell=3, enemies=[enemy(4, action="Attack", queue=[SWAP_TOSS])]), Action("Wait"))
        self.assertEqual(after.hero.cell, 3)

    def test_swap_toss_fails_on_a_heavy_neighbour(self):
        heavy = enemy(4)
        heavy.movable = False
        after, _ = step(make_state(enemies=[enemy(3, action="Attack", queue=[SWAP_TOSS]), heavy]), Action("Wait"))
        self.assertEqual(after.hero.cell, 2)

    def test_mirror_reflects_across_the_middle_and_turns_around(self):
        after, _ = step(make_state(hero_cell=0, enemies=[enemy(3, action="Attack", queue=[MIRROR])]), Action("Wait"))
        self.assertEqual((after.enemies[0].cell, after.enemies[0].facing), (1, 1))

    def test_mirror_trades_places_and_turns_the_other_around_too(self):
        after, _ = step(make_state(hero_cell=1, facing=1, enemies=[enemy(3, action="Attack", queue=[MIRROR])]), Action("Wait"))
        self.assertEqual((after.enemies[0].cell, after.enemies[0].facing), (1, 1))
        self.assertEqual((after.hero.cell, after.hero.facing), (3, -1))

    def test_mirror_on_the_middle_cell_only_turns_around(self):
        after, _ = step(make_state(hero_cell=0, enemies=[enemy(2, action="Attack", queue=[MIRROR])]), Action("Wait"))
        self.assertEqual((after.enemies[0].cell, after.enemies[0].facing), (2, 1))

    def test_mirror_on_an_even_room_uses_the_left_middle(self):
        state = make_state(hero_cell=0, enemies=[enemy(3, action="Attack", queue=[MIRROR])])
        state.cells = 6
        after, _ = step(state, Action("Wait"))
        self.assertEqual(after.enemies[0].cell, 1)

    def test_origin_of_symmetry_goes_to_the_centre(self):
        after, _ = step(make_state(hero_cell=0, enemies=[enemy(4, action="Attack", queue=[ORIGIN])]), Action("Wait"))
        self.assertEqual((after.enemies[0].cell, after.enemies[0].facing, after.hero.cell), (2, -1, 0))

    def test_origin_of_symmetry_trades_places_with_whoever_is_there(self):
        after, _ = step(make_state(hero_cell=2, enemies=[enemy(4, action="Attack", queue=[ORIGIN])]), Action("Wait"))
        self.assertEqual((after.enemies[0].cell, after.hero.cell), (2, 4))

    def test_dragon_punch_sends_them_as_far_as_they_go(self):
        after, outcome = fire(make_state(hero_cell=1, enemies=[enemy(2)]), PUNCH)
        self.assertEqual((after.enemies[0].cell, after.enemies[0].hp), (4, 2))
        self.assertEqual(outcome.enemy_damage, 1)

    def test_dragon_punch_into_someone_hurts_them_both(self):
        after, outcome = fire(make_state(hero_cell=1, enemies=[enemy(2), enemy(4)]), PUNCH)
        self.assertEqual([(e.cell, e.hp) for e in after.enemies], [(3, 1), (4, 2)])
        self.assertEqual(outcome.enemy_damage, 3)

    def test_dragon_punch_leaves_a_heavy_target_in_place(self):
        heavy = enemy(2)
        heavy.movable = False
        after, _ = fire(make_state(hero_cell=1, enemies=[heavy]), PUNCH)
        self.assertEqual((after.enemies[0].cell, after.enemies[0].hp), (2, 2))


def shogun(cell=3, hp=30, queue=(), kind="ShogunPhase2Boss"):
    return Agent(kind, cell, -1, hp, 40, queue=list(queue), action="Attack" if queue else "Wait")


class CorruptedBarrageTest(unittest.TestCase):
    def barrage(self, hero_cell):
        state = make_state(hero_cell=hero_cell, enemies=[shogun(queue=[BARRAGE])])
        state.cells = 7
        return state

    def test_hits_the_cells_beside_the_boss_straight_away(self):
        after, outcome = step(self.barrage(2), Action("Wait"))
        self.assertEqual(outcome.hp_lost, 3)
        self.assertEqual(after.hazards, [{"damage": 3, "groups": [[1, 5], [0, 6]]}])

    def test_spreads_one_cell_a_turn(self):
        # As played: fired from cell 3 on turn 37, and it hit the hero on cell 0 on turn 39.
        state, first = step(self.barrage(0), Action("Wait"))
        state, second = step(state, Action("Wait"))
        state, third = step(state, Action("Wait"))
        self.assertEqual((first.hp_lost, second.hp_lost, third.hp_lost), (0, 0, 3))
        self.assertEqual(state.hazards, [])

    def test_the_ring_starts_from_where_it_was_fired(self):
        state, _ = step(self.barrage(1), Action("MoveLeft"))
        state.enemies[0].cell = 6
        _, outcome = step(state, Action("MoveRight"))
        self.assertEqual(outcome.hp_lost, 3)

    def test_a_shield_blocks_it(self):
        state = self.barrage(4)
        state.hero.shield = True
        after, outcome = step(state, Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.hero.shield), (0, False))

    def test_it_heals_a_boss_it_lands_on(self):
        state = make_state(hero_cell=0, enemies=[shogun(cell=4, hp=39)])
        state.hazards = [{"damage": 3, "groups": [[4]]}]
        after, outcome = step(state, Action("Wait"))
        self.assertEqual(after.enemies[0].hp, 40)
        self.assertEqual(outcome.friendly_damage, 0)

    def test_it_hurts_other_enemies(self):
        state = make_state(hero_cell=0, enemies=[enemy(4, hp=3)])
        state.hazards = [{"damage": 2, "groups": [[4]]}]
        after, _ = step(state, Action("Wait"))
        self.assertEqual(after.enemies[0].hp, 1)

    def test_counts_as_a_threat_on_the_marked_cell_only(self):
        state = make_state(hero_cell=0, enemies=[shogun()])
        state.hazards = [{"damage": 3, "groups": [[0, 4], [1]]}]
        self.assertEqual(_threat_damage(state, 0), 3)
        self.assertEqual(_threat_damage(state, 1), 0)
        self.assertEqual(unanswerable_damage(state), 0)

    def test_the_hero_steps_off_a_marked_cell(self):
        state = make_state(hero_cell=0, enemies=[shogun()])
        state.hazards = [{"damage": 3, "groups": [[0, 4]]}]
        self.assertEqual(rank_actions(state, depth=1)[0].terms.get("hp_lost", 0), 0)

    def test_the_hero_doesnt_step_onto_the_next_ring(self):
        state = make_state(hero_cell=1, enemies=[shogun(cell=3)])
        state.cells = 7
        state.hazards = [{"damage": 3, "groups": [[0]]}]
        self.assertNotEqual(rank_actions(state, depth=1)[0].labels[0], "MoveLeft")


def twins(main_hp=35):
    return (Agent("TwinMainBoss", 0, 1, main_hp, 35), Agent("TwinSideBoss", 3, -1, 100, 100))


class TwinsTest(unittest.TestCase):
    def test_damage_to_the_side_twin_comes_off_the_main_twin(self):
        main, side = twins()
        after, outcome = fire(make_state(enemies=[main, side]), KATANA)
        by_kind = {e.kind: e.hp for e in after.enemies}
        self.assertEqual(by_kind, {"TwinMainBoss": 33, "TwinSideBoss": 98})
        self.assertEqual(outcome.enemy_damage, 2)

    def test_damage_to_the_main_twin_doesnt_reach_the_side_twin(self):
        main, side = twins()
        main.cell = 1
        state = make_state(facing=-1, enemies=[main, side])
        after, _ = fire(state, KATANA)
        by_kind = {e.kind: e.hp for e in after.enemies}
        self.assertEqual(by_kind, {"TwinMainBoss": 33, "TwinSideBoss": 100})

    def test_a_cursed_side_twin_passes_on_the_doubled_damage(self):
        main, side = twins()
        side.curse = True
        after, _ = fire(make_state(enemies=[main, side]), KATANA)
        self.assertEqual({e.kind: e.hp for e in after.enemies}["TwinMainBoss"], 31)

    def test_the_last_of_the_main_twins_hp_can_come_through_the_side_twin(self):
        main, side = twins(main_hp=2)
        after, outcome = fire(make_state(enemies=[main, side]), KATANA)
        self.assertEqual((after.enemies, outcome.kills), ([], 1))

    def test_the_main_twin_dying_takes_the_side_twin_along(self):
        main, side = twins(main_hp=2)
        main.cell = 1
        after, outcome = fire(make_state(facing=-1, enemies=[main, side]), KATANA)
        self.assertEqual((after.enemies, outcome.kills), ([], 1))

    def test_the_side_twins_hp_isnt_counted_as_what_is_left_to_do(self):
        main, side = twins()
        self.assertEqual(leaf_terms(make_state(enemies=[main, side]))["enemy_hp_left"], -4 * 35)

    def test_either_twin_will_do_so_the_closer_one_is_the_target(self):
        main, side = twins()
        self.assertIs(ideal_target(make_state(enemies=[main, side])), side)


class BossDeathTest(unittest.TestCase):
    def test_everyone_dies_with_the_boss(self):
        state = make_state(enemies=[shogun(cell=3, hp=2), enemy(0)])
        after, outcome = fire(state, KATANA)
        self.assertEqual((after.enemies, outcome.kills), ([], 2))  # They count as kills, as if killed outright.

    def test_a_sweep_counts_those_who_die_with_the_boss(self):
        # Swirl hits both for 2: the Shogun dies, and the Ashigaru's last 1 HP counts too, as a kill.
        state = make_state(enemies=[shogun(cell=1, hp=2), enemy(3)])
        after, outcome = fire(state, SWIRL)
        self.assertEqual((after.enemies, outcome.kills, outcome.enemy_damage), ([], 2, 5))

    def test_killing_the_boss_wins_the_fight(self):
        state = make_state(enemies=[shogun(cell=3, hp=2), enemy(0)])
        after, _ = fire(state, KATANA)
        self.assertTrue(fight_won(after))

    def test_a_cleared_room_wins_only_on_the_last_wave(self):
        state = make_state(enemies=[enemy(3, hp=2)])
        state.turns_until_wave, state.last_wave = 4, False
        self.assertFalse(fight_won(fire(state, KATANA)[0]))
        state = make_state(enemies=[enemy(3, hp=2)])
        state.turns_until_wave, state.last_wave = 4, True
        self.assertTrue(fight_won(fire(state, KATANA)[0]))

    def test_a_free_win_now_beats_anything(self):
        state = make_state(enemies=[enemy(3, hp=2)], queue=["Swirl"])
        best = rank_actions(state, depth=1)[0]
        self.assertEqual((best.actions[0].kind, best.terms.get("win")), ("Attack", WEIGHTS["win"]))

    def test_a_win_that_costs_hp_now_earns_nothing_extra(self):
        # Killing a lone Warden from beside it wins, but its blast hits the hero for 2.
        state = make_state(hero_cell=2, enemies=[WardenTest.warden(None, 3)], queue=["Swirl"])
        lines = {line.labels[0]: line for line in rank_actions(state, depth=1)}
        self.assertNotIn("win", lines["Attack"].terms)

    def test_a_barricade_dying_with_its_boss_counts_nothing(self):
        barricade = Agent("Barricade", 0, 1, 5, 5, inanimate=True)
        _, outcome = fire(make_state(enemies=[shogun(cell=3, hp=2), barricade]), KATANA)
        self.assertEqual((outcome.kills, outcome.enemy_damage), (1, 2))

    def test_a_tank_dying_with_its_boss_counts_nothing(self):
        state = make_state(enemies=[shogun(cell=3, hp=2), statue(cell=0)])
        _, outcome = fire(state, KATANA)
        self.assertEqual((outcome.kills, outcome.enemy_damage), (1, 2))

    def test_their_attacks_die_with_them(self):
        state = make_state(enemies=[shogun(cell=3, hp=2), enemy(1, facing=1, action="Attack", queue=[KATANA])])
        _, outcome = fire(state, KATANA)
        self.assertEqual(outcome.hp_lost, 0)


def statue(cell=3, hp=30):
    return Agent("ShogunSummoner", cell, -1, hp, 30, movable=False)


class StatueTest(unittest.TestCase):
    def test_damage_to_a_statue_barely_counts(self):
        _, outcome = fire(make_state(enemies=[shogun(cell=0), statue()]), KATANA)
        self.assertEqual((outcome.enemy_damage, outcome.tank_damage), (0, 2))

    def test_killing_a_statue_isnt_a_kill(self):
        _, outcome = fire(make_state(enemies=[shogun(cell=0), statue(hp=2)]), KATANA)
        self.assertEqual((outcome.kills, outcome.tank_damage), (0, 2))

    def test_breaking_a_statues_shield_earns_nothing(self):
        guarded = statue()
        guarded.shield = True
        _, outcome = fire(make_state(enemies=[shogun(cell=0), guarded]), KATANA)
        self.assertEqual(outcome.shields_broken, 0)

    def test_a_statue_isnt_the_target_even_when_closer(self):
        boss = shogun(cell=0)
        self.assertIs(ideal_target(make_state(enemies=[boss, statue()])), boss)

    def test_a_statues_hp_isnt_counted_as_what_is_left_to_do(self):
        state = make_state(enemies=[shogun(cell=0, hp=40), statue()])
        self.assertEqual(leaf_terms(state)["enemy_hp_left"], -4 * 40)

    def test_another_bosss_summons_still_count(self):
        summoner = Agent("Summoner", 3, -1, 15, 15)
        _, outcome = fire(make_state(enemies=[shogun(cell=0, kind="DaisukeBoss"), summoner]), KATANA)
        self.assertEqual((outcome.enemy_damage, outcome.tank_damage), (2, 0))

    def test_an_enemys_hit_on_a_statue_earns_nothing(self):
        state = make_state(hero_cell=0, enemies=[shogun(cell=2), statue(cell=3)])
        state.enemies[0].facing, state.enemies[0].action, state.enemies[0].queue = 1, "Attack", [KATANA]
        _, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.friendly_damage, 0)


class PerfectStrikeTest(unittest.TestCase):
    STRIKE = Attack("Spear", 1, [1], first_target=True, effect="PerfectStrike")

    def fired_tile(self, *enemies):
        after, _ = fire(make_state(enemies=list(enemies)), self.STRIKE, cooldown=4)
        return next(t for t in after.tiles if t.attack.name == "Spear")

    def test_an_exact_kill_recharges_the_tile(self):
        self.assertTrue(self.fired_tile(enemy(3, hp=1)).ready)

    def test_a_wound_doesnt(self):
        self.assertEqual(self.fired_tile(enemy(3, hp=2)).charge, 0)

    def test_overkill_doesnt(self):
        strike = Attack("Spear", 3, [1], first_target=True, effect="PerfectStrike")
        after, _ = fire(make_state(enemies=[enemy(3, hp=1)]), strike, cooldown=4)
        self.assertEqual(next(t for t in after.tiles if t.attack.name == "Spear").charge, 0)

    def test_a_curse_counts_toward_the_exact_amount(self):
        cursed = enemy(3, hp=2)
        cursed.curse = True
        self.assertTrue(self.fired_tile(cursed).ready)


class UnfriendlyFireTest(unittest.TestCase):
    def test_enemies_hit_each_other_harder(self):
        state = make_state(hero_cell=0, enemies=[enemy(3, hp=5), enemy(4, action="Attack", queue=[KATANA])])
        state.friendly_bonus = 1
        after, outcome = step(state, Action("Wait"))
        self.assertEqual((after.enemies[0].hp, outcome.friendly_damage), (2, 3))

    def test_the_hero_takes_no_extra(self):
        state = make_state(enemies=[enemy(3, action="Attack", queue=[KATANA])])
        state.friendly_bonus = 1
        _, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.hp_lost, 2)

    def test_collisions_arent_affected(self):
        puncher = enemy(1, facing=1, action="Attack", queue=[PUNCH])
        state = make_state(hero_cell=0, enemies=[puncher, enemy(2, hp=5), enemy(4, hp=5)])
        state.friendly_bonus = 1
        after, _ = step(state, Action("Wait"))
        # The punch gets the bonus, for 2. The two collision hits are 1 each.
        self.assertEqual([(e.cell, e.hp) for e in after.enemies], [(1, 3), (3, 2), (4, 4)])


def volley(target_cell=None):
    return Attack("Volley", 2, FAR, first_target=True, target_cell=target_cell)


def sniper(cell=4, target_cell=2, action="Attack"):
    return Agent("Sniper", cell, -1, 3, 3, queue=[volley(target_cell)], action=action)


class VolleyTest(unittest.TestCase):
    def test_staying_on_the_locked_cell_takes_the_hit(self):
        _, outcome = step(make_state(enemies=[sniper()]), Action("Wait"))
        self.assertEqual(outcome.hp_lost, 2)

    def test_stepping_off_dodges_it_even_along_the_same_line(self):
        after, outcome = step(make_state(enemies=[sniper()]), Action("MoveLeft"))
        self.assertEqual((after.hero.cell, outcome.hp_lost), (1, 0))

    def test_it_passes_over_anyone_in_between(self):
        blocker = enemy(3)
        after, outcome = step(make_state(enemies=[blocker, sniper()]), Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.enemies[0].hp), (2, 3))

    def test_it_hits_whoever_is_on_the_cell_when_it_lands(self):
        after, outcome = step(make_state(enemies=[enemy(3, hp=5), sniper()]), Action("MoveRight"))
        self.assertEqual(after.hero.cell, 3)
        by_kind = {e.kind: e for e in after.enemies}
        self.assertEqual((outcome.hp_lost, by_kind["Ashigaru"].cell, by_kind["Ashigaru"].hp), (0, 2, 3))

    def test_a_shield_blocks_it(self):
        state = make_state(enemies=[sniper()])
        state.hero.shield = True
        after, outcome = step(state, Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.hero.shield), (0, False))

    def test_killing_the_sniper_cancels_it(self):
        _, outcome = fire(make_state(enemies=[sniper(cell=3)]), TETSUBO)
        self.assertEqual(outcome.hp_lost, 0)

    def test_a_loaded_volley_locks_onto_where_the_hero_ends_the_turn(self):
        after, _ = step(make_state(enemies=[sniper(target_cell=None, action="Wait")]), Action("MoveLeft"))
        self.assertEqual(after.enemies[0].queue[0].target_cell, 1)

    def test_it_only_threatens_the_locked_cell(self):
        state = make_state(enemies=[sniper()])
        self.assertEqual(_threat_damage(state, 2), 2)
        self.assertEqual(_threat_damage(state, 1), 0)

    def test_a_free_cell_beside_the_hero_is_an_answer(self):
        self.assertEqual(unanswerable_damage(make_state(enemies=[sniper()])), 0)

    def test_having_nowhere_to_step_is_not_an_answer(self):
        state = make_state(hero_cell=0, facing=1, swap_charge=0, enemies=[enemy(1), sniper(target_cell=0)])
        self.assertEqual(unanswerable_damage(state), 2)

    def test_the_hero_steps_off_the_locked_cell(self):
        best = rank_actions(make_state(enemies=[sniper()]), depth=1)[0]
        self.assertEqual(best.terms.get("hp_lost", 0), 0)

    def test_state_from_log_locks_it_only_on_the_turn_it_fires(self):
        def attacks_for(action):
            shot = {"name": "Volley", "value": 2, "range": FAR, "closestTargetOnly": True, "effect": "None"}
            shooter = {"kind": "Sniper", "cell": 6, "facing": "Left", "hp": 3, "maxHp": 3, "shield": False,
                       "queue": [shot], "action": action}
            hero = {"kind": "Wanderer", "cell": 2, "facing": "Left", "hp": 10, "maxHp": 10, "shield": False,
                    "queue": [], "action": "Wait"}
            return state_from_log({"cells": 7, "hero": hero, "enemies": [shooter], "tiles": []}).enemies[0].queue[0]
        self.assertEqual(attacks_for("Attack").target_cell, 2)
        self.assertIsNone(attacks_for("Wait").target_cell)


BOMB = Attack("Bomb", 3, [1], first_target=True)
BARRICADE = Attack("Barricade", 0, [1], first_target=True)
COPYCAT = Attack("CopycatMirror", 0, [1], first_target=True)


class BombTest(unittest.TestCase):
    def thrown(self, hero_cell=4, boss_cell=2, facing=1):
        boss = Agent("HideyoshiBoss", boss_cell, facing, 30, 40, queue=[BOMB], action="Attack")
        state = make_state(hero_cell=hero_cell, enemies=[boss])
        state.cells = 7
        return state

    def test_it_does_nothing_on_the_turn_it_lands(self):
        after, outcome = step(self.thrown(hero_cell=3), Action("Wait"))
        self.assertEqual(outcome.hp_lost, 0)
        self.assertEqual(after.hazards[0]["groups"], [[], [2, 3, 4]])

    def test_it_goes_off_two_turns_later_on_three_cells(self):
        # As played: thrown on turn 21, and it hit the hero for 3 on turn 23.
        state, first = step(self.thrown(hero_cell=3), Action("Wait"))
        state, second = step(state, Action("Wait"))
        state, third = step(state, Action("Wait"))
        self.assertEqual((first.hp_lost, second.hp_lost, third.hp_lost), (0, 0, 3))
        self.assertEqual(state.hazards, [])

    def test_two_steps_get_clear_of_the_blast(self):
        state, _ = step(self.thrown(hero_cell=3), Action("Wait"))
        state, _ = step(state, Action("MoveRight"))
        state, outcome = step(state, Action("MoveRight"))
        self.assertEqual((state.hero.cell, outcome.hp_lost), (5, 0))

    def test_one_step_within_the_blast_isnt_enough(self):
        state, _ = step(self.thrown(hero_cell=3), Action("Wait"))
        state, _ = step(state, Action("Wait"))
        _, outcome = step(state, Action("MoveRight"))
        self.assertEqual(outcome.hp_lost, 3)

    def test_it_needs_a_cell_in_front(self):
        after, _ = step(self.thrown(boss_cell=6, facing=1), Action("Wait"))
        self.assertEqual(after.hazards, [])

    def test_the_blast_hurts_a_boss_rather_than_healing_it(self):
        state = make_state(hero_cell=0, enemies=[shogun(cell=4, hp=30)])
        state.hazards = [{"damage": 3, "groups": [[4]], "heals_boss": False}]
        after, _ = step(state, Action("Wait"))
        self.assertEqual(after.enemies[0].hp, 27)

    def test_a_fuse_shows_no_threat_until_the_last_turn(self):
        state = make_state(hero_cell=0, enemies=[shogun()])
        state.hazards = [{"damage": 3, "groups": [[], [0, 1]], "heals_boss": False}]
        self.assertEqual(_threat_damage(state, 0), 0)
        state.hazards = [{"damage": 3, "groups": [[0, 1]], "heals_boss": False}]
        self.assertEqual(_threat_damage(state, 0), 3)

    def test_standing_in_the_middle_of_a_blast_has_no_answer_next_turn(self):
        state = make_state(hero_cell=2, enemies=[shogun(cell=4)])
        state.hazards = [{"damage": 3, "groups": [[1, 2, 3]], "heals_boss": False}]
        self.assertEqual(unanswerable_damage(state), 3)

    def test_the_hero_leaves_in_time(self):
        state = make_state(hero_cell=2, enemies=[shogun(cell=4)])
        state.cells = 7
        state.hazards = [{"damage": 3, "groups": [[], [1, 2, 3]], "heals_boss": False}]
        best = rank_actions(state, depth=1)[0]
        self.assertIn(best.labels[0], ("MoveLeft", "MoveRight"))


class BarricadeTest(unittest.TestCase):
    def test_it_appears_in_front_of_its_user(self):
        boss = Agent("BaruBoss", 3, -1, 14, 14, queue=[BARRICADE], action="Attack")
        after, _ = step(make_state(hero_cell=0, enemies=[boss]), Action("Wait"))
        wall = next(e for e in after.enemies if e.kind == "Barricade")
        self.assertEqual((wall.cell, wall.hp, wall.facing, wall.action), (2, 5, -1, "Wait"))

    def test_it_needs_a_free_cell(self):
        boss = Agent("BaruBoss", 3, -1, 14, 14, queue=[BARRICADE], action="Attack")
        after, _ = step(make_state(hero_cell=2, enemies=[boss]), Action("Wait"))
        self.assertEqual([e.kind for e in after.enemies], ["BaruBoss"])

    def test_it_stops_a_first_target_shot(self):
        wall = Agent("Barricade", 3, -1, 5, 5)
        archer = enemy(4, action="Attack", queue=[Attack("Arrow", 2, FAR, first_target=True)])
        after, outcome = step(make_state(enemies=[wall, archer]), Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.enemies[0].hp), (0, 3))


class CopycatMirrorTest(unittest.TestCase):
    def test_it_leaves_an_unknown_copy_in_the_queue(self):
        kabukai = Agent("Kabukai", 3, -1, 5, 5, queue=[COPYCAT], action="Attack")
        after, outcome = step(make_state(enemies=[kabukai]), Action("Wait"))
        self.assertEqual([a.name for a in after.enemies[0].queue], ["UnknownCopy"])
        self.assertEqual(outcome.hp_lost, 0)

    def test_the_unknown_copy_isnt_a_threat(self):
        # It copies from the hero's hand wherever the hero stands, so it can't be dodged, and the copy could be
        # anything: F1 reacts once it shows, before the copier can fire it.
        kabukai = Agent("Kabukai", 3, -1, 5, 5, queue=[COPYCAT], action="Attack")
        after, _ = step(make_state(enemies=[kabukai]), Action("Wait"))
        self.assertEqual(_threat_damage(after, 2), 0)

    def test_a_tile_an_enemy_plays_still_is(self):
        ashigaru = enemy(3, action="PlayTile")
        after, _ = step(make_state(enemies=[ashigaru]), Action("Wait"))
        self.assertGreater(_threat_damage(after, 2), 0)


POISON_SHOT = Attack("Shuriken", 3, FAR, first_target=True, effect="Poison")


class PoisonTest(unittest.TestCase):
    def test_it_ticks_for_three_turns_starting_at_once(self):
        # As played: the boss went 2, then 1, then clear, losing 1 HP each turn.
        state, _ = fire(make_state(enemies=[enemy(4, hp=9)]), POISON_SHOT)
        self.assertEqual((state.enemies[0].hp, state.enemies[0].poison), (5, 2))
        state, _ = step(state, Action("Wait"))
        self.assertEqual((state.enemies[0].hp, state.enemies[0].poison), (4, 1))
        state, _ = step(state, Action("Wait"))
        self.assertEqual((state.enemies[0].hp, state.enemies[0].poison), (3, 0))
        state, _ = step(state, Action("Wait"))
        self.assertEqual(state.enemies[0].hp, 3)

    def test_a_shield_blocks_a_tick_and_is_used_up(self):
        # As played on turn 24 of the final boss. The turn still counts down.
        target = enemy(4, hp=9)
        target.poison, target.shield = 2, True
        after, _ = step(make_state(enemies=[target]), Action("Wait"))
        self.assertEqual((after.enemies[0].hp, after.enemies[0].shield, after.enemies[0].poison), (9, False, 1))

    def test_a_tick_can_kill(self):
        target = enemy(4, hp=1)
        target.poison = 2
        after, outcome = step(make_state(enemies=[target]), Action("Wait"))
        self.assertEqual((after.enemies, outcome.kills), ([], 1))

    def test_a_tick_on_a_boss_ends_the_fight(self):
        boss = shogun(cell=4, hp=1)
        boss.poison = 1
        after, _ = step(make_state(hero_cell=0, enemies=[boss, enemy(2)]), Action("Wait"))
        self.assertEqual(after.enemies, [])

    def test_poisoning_again_only_refreshes_it(self):
        target = enemy(4, hp=20)
        target.poison = 2
        after, _ = fire(make_state(enemies=[target]), POISON_SHOT)
        self.assertEqual(after.enemies[0].poison, 2)  # Back up to 3, then one tick.

    def test_poison_counts_for_nothing_if_the_volley_then_kills(self):
        def stack(hp, effect="Poison"):
            state = make_state(hero_cell=3, enemies=[enemy(4, hp=hp)])
            first = Tile(Attack("Spear", 1, [1], first_target=True, effect=effect), cooldown=3, charge=3)
            second = Tile(Attack("Katana", 2, [1], first_target=True), cooldown=3, charge=3)
            first.in_queue = second.in_queue = True
            state.tiles = [first, second]
            state.queue_tiles = [first, second]
            state.hero.queue = [first.attack, second.attack]
            return leaf_terms(state)["stack"]
        # At 3 HP the volley kills, so the poison adds nothing. At 9 HP it adds 3 turns of poison, 24.
        self.assertAlmostEqual(stack(3), stack(3, effect="None"))
        self.assertAlmostEqual(stack(9) - stack(9, effect="None"), 24 * 0.6)

    def test_the_hero_is_hurt_by_it_too(self):
        state = make_state(enemies=[enemy(4)])
        state.hero.poison = 2
        after, outcome = step(state, Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.hero.poison), (1, 1))

    def test_poison_left_on_an_enemy_is_worth_something(self):
        target = enemy(4, hp=9)
        target.poison = 2
        self.assertEqual(leaf_terms(make_state(enemies=[target]))["poison"], 16)

    def test_it_counts_no_further_than_the_enemys_hp(self):
        target = enemy(4, hp=1)
        target.poison = 3
        self.assertEqual(leaf_terms(make_state(enemies=[target]))["poison"], 8)

    def test_it_costs_the_hero(self):
        state = make_state(enemies=[enemy(4)])
        state.hero.poison = 2
        self.assertEqual(leaf_terms(state)["poison"], -200)

    def test_a_loaded_poison_tile_beats_the_same_damage_without_it(self):
        def load_score(attack):
            state = make_state(enemies=[enemy(4, hp=9)])
            tile = Tile(attack, cooldown=3, charge=3)
            state.tiles = [tile]
            return rank_actions(state, depth=1)[0].terms["stack"]
        plain = Attack("Shuriken", 3, FAR, first_target=True)
        self.assertGreater(load_score(POISON_SHOT), load_score(plain))


class TwoWayMoveTest(unittest.TestCase):
    def test_swap_needs_the_skill_to_work_backward(self):
        state = make_state(facing=1, enemies=[enemy(1)])
        self.assertNotIn(Action("MoveLeft"), legal_actions(state))
        state.two_way_swap = True
        self.assertIn(Action("MoveLeft"), legal_actions(state))

    def test_a_backward_swap_keeps_the_hero_facing_the_same_way(self):
        state = make_state(facing=1, enemies=[enemy(1)])
        state.two_way_swap = True
        after, _ = step(state, Action("MoveLeft"))
        self.assertEqual((after.hero.cell, after.hero.facing, after.enemies[0].cell, after.swap_charge), (1, 1, 2, 0))

    def test_it_still_needs_a_charge(self):
        state = make_state(facing=1, swap_charge=0, enemies=[enemy(1)])
        state.two_way_swap = True
        self.assertNotIn(Action("MoveLeft"), legal_actions(state))

    def test_it_counts_as_an_answer_to_a_threat(self):
        state = make_state(hero_cell=0, facing=-1, enemies=[enemy(1, action="Attack", queue=[KATANA])])
        self.assertEqual(unanswerable_damage(state), 2)
        state.two_way_swap = True
        self.assertEqual(unanswerable_damage(state), 0)


class FrozenEnemyTest(unittest.TestCase):
    def test_a_frozen_enemys_loaded_attack_isnt_a_threat(self):
        frozen = enemy(3, queue=[KATANA])
        frozen.ice = 2
        self.assertEqual(_threat_damage(make_state(enemies=[frozen]), 2), 0)

    def test_it_is_again_once_the_ice_runs_out(self):
        frozen = enemy(3, queue=[KATANA])
        frozen.ice = 1
        after, _ = step(make_state(enemies=[frozen]), Action("Wait"))
        self.assertEqual(after.enemies[0].ice, 0)
        self.assertEqual(_threat_damage(after, 2), 2)


class ShoveTest(unittest.TestCase):
    def test_a_shove_earns_credit_for_the_distance(self):
        _, outcome = fire(make_state(hero_cell=1, enemies=[enemy(2)]), PUNCH)
        self.assertEqual(outcome.shove_cells, 2)

    def test_the_credit_is_capped(self):
        state = make_state(hero_cell=0, enemies=[enemy(1)])
        state.cells = 9
        _, outcome = fire(state, PUNCH)
        self.assertEqual(outcome.shove_cells, 3)

    def test_a_statue_earns_none(self):
        target = statue(cell=2)
        target.movable = True
        _, outcome = fire(make_state(hero_cell=1, enemies=[shogun(cell=4), target]), PUNCH)
        self.assertEqual(outcome.shove_cells, 0)

    def test_it_counts_toward_loading_a_shove(self):
        state = make_state(hero_cell=1, enemies=[enemy(2, hp=9)])
        state.tiles = [Tile(PUNCH, cooldown=2, charge=2)]
        plain = make_state(hero_cell=1, enemies=[enemy(2, hp=9)])
        plain.tiles = [Tile(Attack("Katana", 1, [1], first_target=True), cooldown=2, charge=2)]
        self.assertGreater(rank_actions(state, depth=1)[0].terms["stack"], rank_actions(plain, depth=1)[0].terms["stack"])


def ronin(hero_cell=2, facing=1, enemies=(), swap_charge=4):
    state = make_state(hero_cell=hero_cell, facing=facing, enemies=enemies, swap_charge=swap_charge)
    state.special = "PushSpecialMove"
    return state


def jujitsuka(hero_cell=2, facing=1, enemies=(), swap_charge=4):
    state = make_state(hero_cell=hero_cell, facing=facing, enemies=enemies, swap_charge=swap_charge)
    state.cells = 7
    state.special = "ThrowSpecialMove"
    return state


class ThrowSpecialMoveTest(unittest.TestCase):
    """ThrowSpecialMove in the game's code: the enemy behind the hero goes over it, then is pushed on as far as it goes."""

    def test_the_enemy_behind_lands_in_front_and_slides_away(self):
        # Facing right, the enemy behind is on the left, so the throw is a move left, into it.
        after, _ = step(jujitsuka(enemies=[enemy(1, facing=1)]), Action("MoveLeft"))
        self.assertEqual((after.hero.cell, after.enemies[0].cell, after.swap_charge), (2, 6, 0))

    def test_it_stops_at_whoever_is_there_and_both_take_a_collision(self):
        after, _ = step(jujitsuka(enemies=[enemy(1, facing=1), enemy(5)]), Action("MoveLeft"))
        self.assertEqual(sorted((e.cell, e.hp) for e in after.enemies), [(4, 2), (5, 2)])

    def test_not_the_way_the_hero_faces_without_two_way_move(self):
        state = jujitsuka(enemies=[enemy(3)])
        self.assertNotIn("MoveRight", [a.kind for a in legal_actions(state)])
        state.two_way_swap = True
        self.assertIn("MoveRight", [a.kind for a in legal_actions(state)])

    def test_the_cell_in_front_must_be_free(self):
        self.assertFalse(can_use_special(jujitsuka(enemies=[enemy(1, facing=1), enemy(3)]), -1))
        self.assertFalse(can_use_special(jujitsuka(hero_cell=6, facing=1, enemies=[enemy(5, facing=1)]), -1))

    def test_a_heavy_enemy_cant_be_thrown(self):
        heavy = enemy(1, facing=1)
        heavy.movable = False
        self.assertFalse(can_use_special(jujitsuka(enemies=[heavy]), -1))

    def test_the_label_says_throw(self):
        state = jujitsuka(enemies=[enemy(1, facing=1)])
        self.assertEqual(Action("MoveLeft").label(state), "MoveLeft (throw)")


class DragonPunchKillTest(unittest.TestCase):
    """logs/run9: a Dragon Punch that kills still sends the body flying into whoever is behind."""

    def test_the_body_still_hits_whoever_stops_it(self):
        punch = Attack("DragonPunch", 1, [1], first_target=True)
        state = jujitsuka(hero_cell=0, enemies=[enemy(1, hp=1), enemy(6, hp=2)])
        after, outcome = fire(state, punch)
        self.assertEqual(([(e.cell, e.hp) for e in after.enemies], outcome.kills), ([(6, 1)], 1))

    def test_an_enemy_punch_that_kills_still_throws_it_into_the_hero(self):
        # logs/run9, fight 3, turn 31: Rei's Dragon Punch killed a 1 HP TwinTachi, which still flew into the hero.
        rei = enemy(6, hp=4, action="Attack", queue=[Attack("DragonPunch", 1, [1], first_target=True)])
        rei.kind = "ReiBoss"
        state = jujitsuka(hero_cell=3, enemies=[enemy(5, hp=1), rei])
        _, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.hp_lost, 1)


class SaiTest(unittest.TestCase):
    """SaiAttack in the game's code: the first agent on the cell ahead, twice as hard if it's telegraphing an attack."""
    SAI = Attack("Sai", 2, [1], first_target=True)

    def test_it_hits_the_enemy_ahead(self):
        after, outcome = fire(jujitsuka(enemies=[enemy(3, hp=5)]), self.SAI)
        self.assertEqual(after.enemies[0].hp, 3)

    def test_twice_as_hard_on_one_about_to_attack(self):
        after, outcome = fire(jujitsuka(enemies=[enemy(3, hp=5, action="Attack", queue=[KATANA])]), self.SAI)
        self.assertEqual((after.enemies[0].hp, outcome.hp_lost), (1, 2))

    def test_only_the_cell_ahead(self):
        _, outcome = fire(jujitsuka(enemies=[enemy(4, hp=5)]), self.SAI)
        self.assertEqual(outcome.wasted_attacks, 1)


class NobunagaTest(unittest.TestCase):
    """NobunagaBoss in the game's code: hurt only on a spotlit cell, and the lights move once he's been hurt."""
    POISON_KATANA = Attack("Katana", 2, [1], first_target=True, effect="Poison")

    def board(self, lit, boss_cell=3, hero_cell=2, hp=40, **kwargs):
        boss = enemy(boss_cell, hp=hp, **kwargs)
        boss.kind, boss.max_hp = "NobunagaBoss", 40
        state = jujitsuka(hero_cell=hero_cell, enemies=[boss])
        state.lit_cells, state.nobunaga_hp_last_turn = list(lit), hp
        return state

    def test_his_armor_stops_a_hit_off_the_light(self):
        after, outcome = fire(self.board(lit=[0, 5]), KATANA)
        self.assertEqual((after.enemies[0].hp, outcome.enemy_damage), (40, 0))

    def test_a_hit_in_the_light_lands(self):
        after, _ = fire(self.board(lit=[3]), KATANA)
        self.assertEqual(after.enemies[0].hp, 38)

    def test_an_effect_still_lands_through_the_armor_but_its_ticks_dont(self):
        after, _ = fire(self.board(lit=[0]), self.POISON_KATANA)
        self.assertEqual((after.enemies[0].hp, after.enemies[0].poison), (40, 2))

    def test_poison_ticks_in_the_light(self):
        state = self.board(lit=[3])
        state.enemies[0].poison = 3
        after, _ = step(state, Action("Wait"))
        self.assertEqual(after.enemies[0].hp, 39)

    def test_once_hurt_the_lights_move_and_nothing_counts_as_lit(self):
        after, _ = fire(self.board(lit=[3]), KATANA)
        self.assertEqual(after.lit_cells, [])

    def test_the_lights_stay_while_he_isnt_hurt(self):
        after, _ = step(self.board(lit=[0, 5]), Action("Wait"))
        self.assertEqual(after.lit_cells, [0, 5])

    def test_trading_places_puts_him_in_the_light(self):
        # The hero stands lit; a Smoke Bomb trades places, then hits him there.
        state = self.board(lit=[2])
        after, outcome = fire(state, Attack("SmokeBomb", 1, [1, 2, 3], first_target=True))
        self.assertEqual((after.enemies[0].cell, after.enemies[0].hp), (2, 39))

    def test_a_poison_tick_lands_before_the_lights_move(self):
        # logs/run10, fight 20 turn 42: hurt in the light, then poisoned, and the tick still hurt him on the old
        # light. The lights move from the room's turn, after every agent's end of turn.
        state = self.board(lit=[3])
        state.enemies[0].poison = 2
        after, _ = fire(state, KATANA)
        self.assertEqual((after.enemies[0].hp, after.lit_cells, after.nobunaga_hp_last_turn), (37, [], 37))

    def test_f1_goes_for_another_enemy_while_he_is_dark(self):
        state = self.board(lit=[0])
        state.enemies.append(enemy(5, hp=3))
        self.assertEqual(ideal_target(state).kind, "Ashigaru")


class ScarStrikeTest(unittest.TestCase):
    """ScarStrikeAttack in the game's code: every enemy below full health, wherever it is."""
    SCAR = Attack("ScarStrike", 1, [])

    def test_it_hits_every_wounded_enemy_anywhere(self):
        wounded_far, wounded_behind, healthy = enemy(6, hp=2), enemy(0, facing=1, hp=1), enemy(3)
        state = jujitsuka(enemies=[wounded_behind, healthy, wounded_far])
        after, outcome = fire(state, self.SCAR)
        self.assertEqual(sorted((e.cell, e.hp) for e in after.enemies), [(3, 3), (6, 1)])
        self.assertEqual(outcome.kills, 1)

    def test_an_earlier_tile_in_the_volley_adds_a_target(self):
        state = jujitsuka(enemies=[enemy(3)])
        swirl, scar = Tile(SWIRL, 3, 3, in_queue=True), Tile(self.SCAR, 5, 5, in_queue=True)
        state.tiles = [swirl, scar]
        state.queue_tiles = [swirl, scar]
        state.hero.queue = [SWIRL, self.SCAR]
        # Swirl takes the 3 HP Ashigaru to 1, which makes it a target, and Scar Strike finishes it.
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.enemies, outcome.kills), ([], 1))

    def test_with_nobody_wounded_it_hits_nothing(self):
        _, outcome = fire(jujitsuka(enemies=[enemy(3)]), self.SCAR)
        self.assertEqual(outcome.wasted_attacks, 1)

    def wounds(self, *enemies, charge=5):
        state = jujitsuka(hero_cell=0, enemies=list(enemies))
        state.tiles = [Tile(self.SCAR, 5, charge)]
        return leaf_terms(state)["wounds"]

    def test_a_chip_on_a_full_enemy_is_worth_half_again(self):
        # 1 damage is worth 10; the wound it leaves is worth half of Scar Strike's 1-damage hit, 5.
        self.assertEqual(self.wounds(enemy(6, hp=2)), 5)
        self.assertEqual(self.wounds(enemy(6, hp=3)), 0)

    def test_no_more_when_it_would_kill(self):
        # The kill shows in the stack when it's loaded, so the wound itself is worth the same.
        self.assertEqual(self.wounds(enemy(6, hp=1)), 5)

    def test_the_same_while_it_cools_down(self):
        self.assertEqual(self.wounds(enemy(6, hp=2), charge=0), 5)

    def test_nothing_without_it_in_the_deck(self):
        state = jujitsuka(hero_cell=0, enemies=[enemy(6, hp=2)])
        self.assertEqual(leaf_terms(state)["wounds"], 0)

    def test_where_the_hero_stands_doesnt_matter_to_it(self):
        state = jujitsuka(hero_cell=0, enemies=[enemy(6, hp=2)])
        state.tiles = [Tile(self.SCAR, 5, 5)]
        self.assertEqual(leaf_terms(state)["reach"], 0)


class ShoveSpecialMoveTest(unittest.TestCase):
    def test_it_pushes_the_target_and_the_hero_stays(self):
        after, outcome = step(ronin(enemies=[enemy(3)]), Action("MoveRight"))
        self.assertEqual((after.hero.cell, after.hero.facing, after.enemies[0].cell, after.enemies[0].hp), (2, 1, 4, 3))
        self.assertEqual((after.swap_charge, outcome.enemy_damage), (0, 0))

    def test_the_distance_earns_no_credit_since_stepping_back_makes_the_same_space(self):
        _, outcome = step(ronin(hero_cell=1, enemies=[enemy(2)]), Action("MoveRight"))
        self.assertEqual(outcome.shove_cells, 0)

    def test_stepping_back_is_preferred_when_it_dodges_just_as_well(self):
        state = ronin(hero_cell=2, enemies=[enemy(3, action="Attack", queue=[KATANA])])
        state.tiles = []
        self.assertEqual(rank_actions(state, depth=1)[0].labels[0], "MoveLeft")

    def test_it_doesnt_charge_on_the_turn_its_used(self):
        after, _ = step(ronin(enemies=[enemy(3)]), Action("MoveRight"))
        self.assertEqual(after.swap_charge, 0)

    def test_someone_behind_the_target_means_a_collision(self):
        after, outcome = step(ronin(enemies=[enemy(3), enemy(4)]), Action("MoveRight"))
        self.assertEqual([(e.cell, e.hp) for e in after.enemies], [(3, 2), (4, 2)])
        self.assertEqual(outcome.enemy_damage, 2)

    def test_it_needs_a_cell_behind_the_target(self):
        state = ronin(hero_cell=3, enemies=[enemy(4)])
        self.assertNotIn(Action("MoveRight"), legal_actions(state))

    def test_a_cell_is_enough_even_two_away_from_the_wall(self):
        state = ronin(hero_cell=2, enemies=[enemy(3)])
        self.assertIn(Action("MoveRight"), legal_actions(state))

    def test_it_needs_a_movable_target(self):
        heavy = enemy(3)
        heavy.movable = False
        self.assertNotIn(Action("MoveRight"), legal_actions(ronin(enemies=[heavy])))

    def test_it_needs_a_charge(self):
        self.assertNotIn(Action("MoveRight"), legal_actions(ronin(swap_charge=0, enemies=[enemy(3)])))

    def test_it_only_works_forward_without_two_way_move(self):
        state = ronin(facing=-1, enemies=[enemy(3)])
        self.assertNotIn(Action("MoveRight"), legal_actions(state))
        state.two_way_swap = True
        self.assertIn(Action("MoveRight"), legal_actions(state))

    def test_a_backward_shove_pushes_that_way_and_keeps_the_facing(self):
        state = ronin(hero_cell=3, facing=1, enemies=[enemy(2)])
        state.cells = 7
        state.two_way_swap = True
        after, _ = step(state, Action("MoveLeft"))
        self.assertEqual((after.hero.cell, after.hero.facing, after.enemies[0].cell, after.swap_charge), (3, 1, 0, 0))

    def test_it_dodges_a_melee_hit_by_moving_the_attacker(self):
        _, outcome = step(ronin(enemies=[enemy(3, action="Attack", queue=[KATANA])]), Action("MoveRight"))
        self.assertEqual(outcome.hp_lost, 0)

    def test_it_doesnt_dodge_a_shot_that_still_reaches(self):
        arrow = Attack("Arrow", 2, FAR, first_target=True)
        _, outcome = step(ronin(enemies=[enemy(3, action="Attack", queue=[arrow])]), Action("MoveRight"))
        self.assertEqual(outcome.hp_lost, 2)

    def test_it_counts_as_an_answer_to_a_melee_threat(self):
        state = ronin(hero_cell=0, enemies=[enemy(1, queue=[KATANA])])
        state.occupant(1).action = "Attack"
        self.assertEqual(unanswerable_damage(state), 0)

    def test_damaging_move_hits_first_and_can_leave_nobody_to_shove(self):
        state = ronin(enemies=[enemy(3, hp=1)])
        state.swap_damage = 1
        after, outcome = step(state, Action("MoveRight"))
        self.assertEqual((after.enemies, outcome.kills, outcome.shove_cells), ([], 1, 0))

    def test_damaging_move_then_shoves_a_survivor(self):
        state = ronin(enemies=[enemy(3, hp=3)])
        state.swap_damage = 1
        after, _ = step(state, Action("MoveRight"))
        self.assertEqual((after.enemies[0].cell, after.enemies[0].hp), (4, 2))

    def test_the_label_says_shove(self):
        state = ronin(enemies=[enemy(3)])
        self.assertEqual(Action("MoveRight").label(state), "MoveRight (shove)")

    def test_a_swap_still_swaps(self):
        after, _ = step(make_state(enemies=[enemy(3)]), Action("MoveRight"))
        self.assertEqual((after.hero.cell, after.enemies[0].cell), (3, 2))

    def test_smoke_bomb_works_for_the_hero_and_turns_nobody(self):
        after, _ = fire(ronin(enemies=[enemy(4)]), SMOKE_BOMB)
        self.assertEqual((after.hero.cell, after.hero.facing, after.enemies[0].cell, after.enemies[0].facing), (4, 1, 2, -1))

    def test_an_unknown_special_move_isnt_offered_and_warns(self):
        state = make_state(enemies=[enemy(3)])
        state.special = "MadeUpSpecialMove"
        self.assertNotIn(Action("MoveRight"), legal_actions(state))
        row = {"tiles": [], "hero": {"queue": [], "special": {"name": "MadeUpSpecialMove"}}, "enemies": [], "skills": []}
        self.assertEqual(unmodeled_content(row), ["special move MadeUpSpecialMove"])

    def test_the_shove_is_read_from_the_log(self):
        hero = {"kind": "Ronin", "cell": 2, "facing": "Right", "hp": 10, "maxHp": 10, "shield": False, "queue": [],
                "action": "Wait", "special": {"name": "PushSpecialMove", "charge": 3, "cooldown": 3}}
        state = state_from_log({"cells": 7, "hero": hero, "enemies": [], "tiles": []})
        self.assertEqual((state.special, state.swap_charge, state.swap_cooldown), ("PushSpecialMove", 3, 3))


HOOK = Attack("GrapplingHook", 1, [1, 2, 3, 4], first_target=True)


class HeroGrapplingHookTest(unittest.TestCase):
    def test_it_hits_and_pulls_the_target_next_to_the_hero(self):
        after, outcome = fire(make_state(hero_cell=0, enemies=[enemy(3, hp=5)]), HOOK)
        self.assertEqual((after.hero.cell, after.enemies[0].cell, after.enemies[0].hp), (0, 1, 4))
        self.assertEqual(outcome.enemy_damage, 1)

    def test_it_works_facing_left(self):
        after, _ = fire(make_state(hero_cell=4, facing=-1, enemies=[enemy(1, facing=1, hp=5)]), HOOK)
        self.assertEqual(after.enemies[0].cell, 3)

    def test_it_stops_at_the_first_target(self):
        after, _ = fire(make_state(hero_cell=0, enemies=[enemy(2, hp=5), enemy(4, hp=5)]), HOOK)
        self.assertEqual([(e.cell, e.hp) for e in after.enemies], [(1, 4), (4, 5)])

    def test_a_shield_blocks_the_damage_but_not_the_pull(self):
        guarded = enemy(3, hp=5)
        guarded.shield = True
        after, _ = fire(make_state(hero_cell=0, enemies=[guarded]), HOOK)
        self.assertEqual((after.enemies[0].cell, after.enemies[0].hp, after.enemies[0].shield), (1, 5, False))

    def test_a_heavy_target_stays_put(self):
        heavy = enemy(3, hp=5)
        heavy.movable = False
        after, _ = fire(make_state(hero_cell=0, enemies=[heavy]), HOOK)
        self.assertEqual((after.enemies[0].cell, after.enemies[0].hp), (3, 4))

    def test_nothing_in_range_is_a_wasted_attack(self):
        _, outcome = fire(make_state(hero_cell=0, enemies=[enemy(4)]), Attack("GrapplingHook", 1, [1, 2], first_target=True))
        self.assertEqual(outcome.wasted_attacks, 1)

    def test_the_hook_then_melee_combo_is_valued(self):
        # Katana alone can't reach. Hook first pulls it in, and the two together kill.
        def stack(attacks):
            state = make_state(hero_cell=0, enemies=[enemy(3, hp=3)])
            tiles = [Tile(a, cooldown=3, charge=3, in_queue=True) for a in attacks]
            state.tiles, state.queue_tiles = tiles, list(tiles)
            state.hero.queue = list(attacks)
            return leaf_terms(state)["stack"]
        self.assertGreater(stack([KATANA, HOOK]), stack([HOOK]))
        self.assertGreater(stack([KATANA, HOOK]), stack([KATANA]))

    def test_it_will_fire_the_combo_in_the_right_order(self):
        state = make_state(hero_cell=0, enemies=[enemy(3, hp=3)])
        katana, hook = Tile(KATANA, cooldown=3, charge=3, in_queue=True), Tile(HOOK, cooldown=3, charge=3, in_queue=True)
        state.tiles, state.queue_tiles = [katana, hook], [katana, hook]
        state.hero.queue = [KATANA, HOOK]
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.terms.get("kills", 0), 60)
        self.assertIn("GrapplingHook > Katana", best.labels[0])


WAVE_KATANA = Attack("Katana", 2, [1], first_target=True, effect="Shockwave")
WAVE_SPEAR = Attack("Spear", 2, [1, 2], effect="Shockwave")


class ShockwaveTest(unittest.TestCase):
    def hp_of(self, state):
        return [(e.cell, e.hp) for e in state.enemies]

    def test_alone_it_does_nothing_extra(self):
        # As played: every firing on an isolated target in the live run dealt only the tile's damage.
        after, outcome = fire(make_state(hero_cell=0, enemies=[enemy(1, hp=5)]), WAVE_KATANA)
        self.assertEqual(self.hp_of(after), [(1, 3)])
        self.assertEqual(outcome.enemy_damage, 2)

    def test_a_touching_enemy_is_hit_and_so_is_the_target_again(self):
        after, outcome = fire(make_state(hero_cell=0, enemies=[enemy(1, hp=5), enemy(2, hp=5)]), WAVE_KATANA)
        self.assertEqual(self.hp_of(after), [(1, 2), (2, 4)])
        self.assertEqual(outcome.enemy_damage, 4)

    def test_it_runs_through_a_whole_chain(self):
        state = make_state(hero_cell=0, enemies=[enemy(1, hp=5), enemy(2, hp=5), enemy(3, hp=5)])
        after, _ = fire(state, WAVE_KATANA)
        self.assertEqual(self.hp_of(after), [(1, 2), (2, 4), (3, 4)])

    def test_a_gap_stops_it(self):
        state = make_state(hero_cell=0, enemies=[enemy(1, hp=5), enemy(3, hp=5)])
        after, _ = fire(state, WAVE_KATANA)
        self.assertEqual(self.hp_of(after), [(1, 3), (3, 5)])

    def test_the_hero_stops_it_and_takes_nothing(self):
        # The enemy behind the hero is only connected through the hero.
        state = make_state(hero_cell=1, enemies=[enemy(0, facing=1, hp=5), enemy(2, hp=5)])
        after, outcome = fire(state, WAVE_KATANA)
        self.assertEqual(self.hp_of(after), [(0, 5), (2, 3)])
        self.assertEqual(outcome.hp_lost, 0)

    def test_killing_the_target_still_sets_it_off(self):
        after, outcome = fire(make_state(hero_cell=0, enemies=[enemy(1, hp=2), enemy(2, hp=5)]), WAVE_KATANA)
        self.assertEqual(self.hp_of(after), [(2, 4)])
        self.assertEqual(outcome.kills, 1)

    def test_a_shield_on_the_target_doesnt_stop_it_and_blocks_only_the_first_hit(self):
        guarded = enemy(1, hp=5)
        guarded.shield = True
        after, _ = fire(make_state(hero_cell=0, enemies=[guarded, enemy(2, hp=5)]), WAVE_KATANA)
        self.assertEqual(self.hp_of(after), [(1, 4), (2, 4)])

    def test_a_shield_in_the_chain_blocks_its_hit(self):
        guarded = enemy(2, hp=5)
        guarded.shield = True
        after, _ = fire(make_state(hero_cell=0, enemies=[enemy(1, hp=5), guarded]), WAVE_KATANA)
        self.assertEqual(self.hp_of(after), [(1, 2), (2, 5)])
        self.assertFalse(after.enemies[1].shield)

    def test_it_can_kill_for_kill_credit(self):
        after, outcome = fire(make_state(hero_cell=0, enemies=[enemy(1, hp=5), enemy(2, hp=1)]), WAVE_KATANA)
        self.assertEqual((self.hp_of(after), outcome.kills), ([(1, 2)], 1))

    def test_each_target_of_a_spear_sets_off_its_own(self):
        state = make_state(hero_cell=0, enemies=[enemy(1, hp=9), enemy(2, hp=9)])
        after, _ = fire(state, WAVE_SPEAR)
        # Each takes 2 from the Spear, and 1 from each of the two shockwaves.
        self.assertEqual(self.hp_of(after), [(1, 5), (2, 5)])

    def test_a_boss_dying_ends_it(self):
        state = make_state(hero_cell=0, enemies=[shogun(cell=1, hp=2), enemy(2, hp=5)])
        after, outcome = fire(state, WAVE_KATANA)
        self.assertEqual((after.enemies, outcome.kills), ([], 2))

    def test_a_statue_in_the_chain_earns_little(self):
        state = make_state(hero_cell=0, enemies=[shogun(cell=1, hp=20), statue(cell=2)])
        _, outcome = fire(state, WAVE_KATANA)
        self.assertEqual((outcome.enemy_damage, outcome.tank_damage), (3, 1))

    def test_a_loaded_stack_counts_the_extra_damage(self):
        def stack(attack):
            state = make_state(hero_cell=0, enemies=[enemy(1, hp=9), enemy(2, hp=9)])
            tile = Tile(attack, cooldown=3, charge=3, in_queue=True)
            state.tiles, state.queue_tiles = [tile], [tile]
            state.hero.queue = [attack]
            return leaf_terms(state)["stack"]
        self.assertGreater(stack(WAVE_KATANA), stack(KATANA))

    def test_it_raises_no_warning(self):
        tile = {"attack": {"name": "Spear", "effect": "Shockwave"}}
        self.assertEqual(unmodeled_content({"tiles": [tile], "hero": {"queue": []}, "enemies": [], "skills": []}), [])


class LightningTest(unittest.TestCase):
    LIGHTNING = Attack("Lightning", 2, [1, 2, 3, 4, 5, 6])

    def fire(self, enemies, hero_cell=0):
        state = make_state(hero_cell=hero_cell, enemies=enemies)
        state.cells = 7
        after, outcome = fire(state, self.LIGHTNING)
        return [e.hp for e in after.enemies], outcome

    def test_it_strikes_the_farthest_agent_ahead(self):
        self.assertEqual(self.fire([enemy(1, hp=5), enemy(4, hp=5)])[0], [5, 3])

    def test_it_passes_over_a_thorns_enemy(self):
        thorns = enemy(4, hp=5)
        thorns.kind = "Thorns"
        self.assertEqual(self.fire([enemy(1, hp=5), thorns])[0], [3, 5])

    def test_with_only_thorns_ahead_it_does_nothing(self):
        thorns = enemy(4, hp=5)
        thorns.kind = "Thorns"
        hps, outcome = self.fire([thorns])
        self.assertEqual((hps, outcome.wasted_attacks), ([5], 1))

    def test_nobody_behind_counts(self):
        self.assertEqual(self.fire([enemy(1, hp=5), enemy(4, hp=5)], hero_cell=3)[0], [5, 3])

    def test_it_raises_no_warning(self):
        tile = {"attack": {"name": "Lightning", "effect": "None"}}
        self.assertEqual(unmodeled_content({"tiles": [tile], "hero": {"queue": []}, "enemies": [], "skills": []}), [])


class IeyasuTest(unittest.TestCase):
    """BossSwapAttack and BladeOfPatienceAttack in the game's code, as Ieyasu and his Swapper use them."""
    BOSS_SWAP = Attack("BossSwap", 0, [])
    BLADE = Attack("BladeOfPatience", 4, [1], first_target=True)

    def board(self, swapper_cell=5, boss_cell=6):
        swapper = Agent("Swapper", swapper_cell, 1, 30, 30, queue=[self.BOSS_SWAP], action="Attack")
        boss = Agent("IeyasuBoss", boss_cell, -1, 40, 40, queue=[Attack("Dash", 0, [1]), self.BLADE], action="Wait")
        state = make_state(hero_cell=2, enemies=[swapper, boss])
        state.cells = 9
        return state

    def test_the_swapper_trades_places_with_the_boss(self):
        after, _ = step(self.board(), Action("Wait"))
        cells = {e.kind: (e.cell, e.facing) for e in after.enemies}
        self.assertEqual(cells, {"Swapper": (6, 1), "IeyasuBoss": (5, -1)})

    def test_the_blade_grows_each_turn_it_waits(self):
        after, _ = step(self.board(), Action("Wait"))
        boss = next(e for e in after.enemies if e.kind == "IeyasuBoss")
        self.assertEqual([a.value for a in boss.queue if a.name == "BladeOfPatience"], [5])

    def test_after_the_swap_his_dash_and_blade_reach_the_hero(self):
        # On turn 16 of the Ieyasu fight, this is what F1 missed: behind the Swapper, his Dash was blocked.
        after, _ = step(self.board(), Action("Wait"))
        self.assertEqual(_threat_damage(after, after.hero.cell), 5)

    def test_the_swapper_is_a_tank_while_ieyasu_lives(self):
        state = self.board()
        swapper = state.enemies[0]
        self.assertTrue(is_tank(state, swapper))
        state.enemies[1].hp = 0
        self.assertFalse(is_tank(state, swapper))

    def test_it_raises_no_warning(self):
        row = {"tiles": [], "hero": {"queue": []}, "skills": [],
               "enemies": [{"kind": "Swapper", "queue": [{"name": "BossSwap", "effect": "None"}]},
                           {"kind": "IeyasuBoss", "queue": [{"name": "BladeOfPatience", "effect": "None"}]}]}
        self.assertEqual(unmodeled_content(row), [])


class TrapTest(unittest.TestCase):
    """TrapAttack and Trap in the game's code: placed on the cell ahead, set off only by an enemy moving onto it."""
    TRAP = Attack("Trap", 3, [1])
    HOOK = Attack("GrapplingHook", 1, [1, 2, 3, 4, 5, 6], first_target=True)

    def board(self, enemies, hero_cell=2, traps=()):
        state = make_state(hero_cell=hero_cell, enemies=enemies)
        state.cells = 7
        state.traps = [{"cell": c, "damage": 3, "effect": "None"} for c in traps]
        return state

    def test_it_goes_on_the_cell_ahead(self):
        after, _ = fire(self.board([enemy(6, hp=9)]), self.TRAP)
        self.assertEqual(after.traps, [{"cell": 3, "damage": 3, "effect": "None"}])

    def test_an_enemy_walking_onto_it_takes_the_damage_once(self):
        walker = enemy(4, hp=9, action="MoveLeft")
        after, outcome = step(self.board([walker], traps=[3]), Action("Wait"))
        self.assertEqual((after.enemies[0].hp, after.traps, outcome.enemy_damage), (6, [], 3))

    def test_the_hero_can_stand_on_it(self):
        after, outcome = step(self.board([enemy(6, hp=9)], traps=[3]), Action("MoveRight"))
        self.assertEqual((after.hero.cell, len(after.traps), outcome.hp_lost), (3, 1, 0))

    def test_two_traps_on_one_cell_both_go_off(self):
        # As on the last turn of the Shogun fight in logs/run7_part3: two 5-damage traps took it from 10 to 0.
        state = self.board([enemy(6, hp=9)], traps=[3, 3])
        after, _ = fire(state, self.HOOK)
        self.assertEqual(([e.hp for e in after.enemies], after.traps), ([2], []))  # 1 from the hook, 3 from each

    def test_placed_under_an_enemy_it_waits(self):
        after, _ = fire(self.board([enemy(3, hp=9)]), self.TRAP)
        self.assertEqual((after.enemies[0].hp, len(after.traps)), (9, 1))

    def test_the_hook_pulls_an_enemy_onto_it(self):
        after, outcome = fire(self.board([enemy(6, hp=9)], traps=[3]), self.HOOK)
        self.assertEqual((after.enemies[0].cell, after.enemies[0].hp, outcome.enemy_damage), (3, 5, 4))

    def test_a_planted_trap_is_worth_part_of_its_damage(self):
        self.assertAlmostEqual(leaf_terms(self.board([enemy(6, hp=9)], traps=[3]))["traps"], 12)

    def test_loading_a_trap_tile_is_worth_something(self):
        state = self.board([enemy(6, hp=9)])
        state.tiles = [Tile(self.TRAP, cooldown=3, charge=3)]
        load = next(c for c in rank_actions(state, depth=1) if c.actions[0].kind == "PlayTile")
        self.assertGreater(load.terms.get("stack", 0), 0)

    def test_read_from_the_log(self):
        row = {"cells": 5, "tiles": [], "enemies": [], "traps": [{"cell": 2, "damage": 3, "effect": "Curse", "armed": True}],
               "hero": {"kind": "H", "cell": 0, "facing": "Right", "hp": 9, "maxHp": 9, "shield": False, "queue": [],
                        "action": "Wait", "special": {"charge": 3, "cooldown": 3}}}
        self.assertEqual(state_from_log(row).traps, [{"cell": 2, "damage": 3, "effect": "Curse"}])


class StriderTest(unittest.TestCase):
    """StriderEnemy.Move in the game's code: it runs to the last free cell that way, rather than one cell."""

    def strider(self, cell, action="MoveRight"):
        s = enemy(cell, facing=1, hp=4, action=action)
        s.kind = "Strider"
        return s

    def test_it_runs_until_something_stops_it(self):
        after, _ = step(make_state(hero_cell=4, enemies=[self.strider(0)]), Action("Wait"))
        self.assertEqual(after.enemies[0].cell, 3)

    def test_or_the_wall(self):
        state = make_state(hero_cell=0, enemies=[self.strider(2)])
        state.cells = 9
        after, _ = step(state, Action("Wait"))
        self.assertEqual(after.enemies[0].cell, 8)

    def test_someone_ahead_going_the_same_way_moves_first(self):
        walker = enemy(3, facing=1, action="MoveRight")
        state = make_state(hero_cell=0, enemies=[self.strider(1), walker])
        state.cells = 7
        after, _ = step(state, Action("Wait"))
        self.assertEqual(sorted(e.cell for e in after.enemies), [3, 4])

    def test_fumiko_moves_the_same_way(self):
        boss = self.strider(0)
        boss.kind = "FumikoBoss"
        after, _ = step(make_state(hero_cell=4, enemies=[boss]), Action("Wait"))
        self.assertEqual(after.enemies[0].cell, 3)

    def test_a_cursed_hero_takes_double_once(self):
        state = make_state(hero_cell=2, enemies=[enemy(3, action="Attack", queue=[KATANA])])
        state.hero.curse = True
        after, outcome = step(state, Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.hero.curse), (4, False))

    def test_it_raises_no_warning(self):
        row = {"tiles": [], "hero": {"queue": []}, "skills": [],
               "enemies": [{"kind": "Strider", "traits": ["Dash"], "queue": []}]}
        self.assertEqual(unmodeled_content(row), [])


class WardenTest(unittest.TestCase):
    """WardenEnemy.Die in the game's code: it explodes for 2 on its own cell and both beside it."""

    def warden(self, cell, hp=1):
        w = enemy(cell, hp=hp)
        w.kind = "Warden"
        return w

    def test_killing_one_beside_the_hero_costs_2(self):
        _, outcome = fire(make_state(hero_cell=2, enemies=[self.warden(3)]), KATANA)
        self.assertEqual((outcome.kills, outcome.hp_lost), (1, 2))

    def test_it_hits_the_enemy_on_its_other_side(self):
        after, outcome = fire(make_state(hero_cell=0, enemies=[self.warden(1), enemy(2, hp=3)]), KATANA)
        self.assertEqual(([(e.cell, e.hp) for e in after.enemies], outcome.hp_lost), ([(2, 1)], 2))

    def test_one_warden_sets_off_the_next(self):
        enemies = [self.warden(2), self.warden(3), enemy(4, hp=3)]
        after, outcome = fire(make_state(hero_cell=0, enemies=enemies), ARROW)
        self.assertEqual(([(e.cell, e.hp) for e in after.enemies], outcome.kills, outcome.hp_lost), ([(4, 1)], 2, 0))

    def test_a_shield_blocks_it(self):
        state = make_state(hero_cell=2, enemies=[self.warden(3)])
        state.hero.shield = True
        _, outcome = fire(state, KATANA)
        self.assertEqual(outcome.hp_lost, 0)

    def test_one_that_survives_doesnt(self):
        _, outcome = fire(make_state(hero_cell=2, enemies=[self.warden(3, hp=5)]), KATANA)
        self.assertEqual(outcome.hp_lost, 0)

    def test_f1_doesnt_kill_it_from_beside_it(self):
        # Swirl loaded, a 1 HP Warden adjacent: firing now kills it but takes the blast.
        best = rank_actions(make_state(hero_cell=2, enemies=[self.warden(3)], queue=["Swirl"]), depth=1)[0]
        self.assertNotEqual(best.actions[0].kind, "Attack")
        self.assertEqual(best.terms.get("hp_lost", 0), 0)


class IceTest(unittest.TestCase):
    """Freezing, from Attack.ProcessAttackEffects and Enemy.ApplyIceStatusCoroutine in the game's code."""
    ICE_KATANA = Attack("Katana", 1, [1], first_target=True, effect="Ice")

    def attacker(self, hp=9):
        return enemy(3, hp=hp, action="Attack", queue=[KATANA])

    def test_it_freezes_for_4_and_cancels_this_turns_attack(self):
        state = make_state(hero_cell=2, enemies=[self.attacker()])
        after, outcome = fire(state, self.ICE_KATANA)
        # 4 turns of ice, less this turn's end. The Katana stays loaded for when it thaws.
        self.assertEqual((outcome.hp_lost, after.enemies[0].ice, [a.name for a in after.enemies[0].queue]),
                         (0, 3, ["Katana"]))

    def test_an_unfreezable_enemy_still_attacks(self):
        target = self.attacker()
        target.freezable = False
        _, outcome = fire(make_state(hero_cell=2, enemies=[target]), self.ICE_KATANA)
        self.assertEqual(outcome.hp_lost, 2)

    def test_the_unfreezable_trait_is_read_from_the_log(self):
        row = {"cells": 5, "tiles": [], "skills": [],
               "enemies": [{"kind": "X", "cell": 3, "facing": "Left", "hp": 3, "maxHp": 3, "shield": False,
                            "queue": [], "action": "Wait", "traits": ["Unfreezable"]}],
               "hero": {"kind": "H", "cell": 0, "facing": "Right", "hp": 9, "maxHp": 9, "shield": False, "queue": [],
                        "action": "Wait", "special": {"charge": 3, "cooldown": 3}}}
        self.assertFalse(state_from_log(row).enemies[0].freezable)

    def test_loading_with_a_full_queue_sends_a_tile_back_first(self):
        state = make_state(enemies=[enemy(4)], queue=["Swirl", "Arrow"])
        katana, spear = Tile(KATANA, cooldown=3, charge=3), Tile(Attack("Spear", 3, [1, 2]), cooldown=3, charge=3)
        katana.in_queue = True
        state.tiles += [katana, spear]
        state.queue_tiles.append(katana)
        state.hero.queue.append(KATANA)
        loads = {(a.tile, a.replace) for a in legal_actions(state) if a.kind == "PlayTile"}
        self.assertEqual(loads, {(3, 0), (3, 1), (3, 2)})
        after, _ = step(state, Action("PlayTile", 3, replace=0))
        self.assertEqual([t.attack.name for t in after.queue_tiles], ["Arrow", "Katana", "Spear"])
        self.assertEqual([a.name for a in after.hero.queue], ["Arrow", "Katana", "Spear"])
        self.assertFalse(after.tiles[0].in_queue)
        self.assertTrue(after.tiles[0].ready)
        self.assertEqual(Action("PlayTile", 3, replace=0).label(state), "PlayTile Spear (Swirl to hand)")

    def test_a_fresh_freeze_is_worth_half_a_kill(self):
        # The turn it's frozen on is played out, so a fresh freeze shows 3 turns left: half of 60 + 10 per HP.
        state = make_state(hero_cell=0, enemies=[enemy(4, hp=9, queue=[KATANA])])
        state.enemies[0].ice = 3
        self.assertEqual(leaf_terms(state)["ice"], 75)

    def test_a_freeze_is_worth_less_as_its_ice_runs_out(self):
        state = make_state(hero_cell=0, enemies=[enemy(4, hp=9)])
        state.enemies[0].ice = 1
        self.assertEqual(leaf_terms(state)["ice"], 25)

    def test_loading_an_ice_tile_counts_the_freeze_it_would_land(self):
        state = make_state(hero_cell=2, enemies=[enemy(3, hp=9, queue=[KATANA])])
        state.tiles = [Tile(self.ICE_KATANA, cooldown=3, charge=3)]
        load = next(c for c in rank_actions(state, depth=1) if c.actions[0].kind == "PlayTile")
        plain = make_state(hero_cell=2, enemies=[enemy(3, hp=9, queue=[KATANA])])
        plain.tiles = [Tile(KATANA, cooldown=3, charge=3)]
        plain_load = next(c for c in rank_actions(plain, depth=1) if c.actions[0].kind == "PlayTile")
        self.assertGreater(load.terms["stack"], plain_load.terms["stack"])
        self.assertEqual(load.terms["effects"], 0.5 * WEIGHTS["future_discount"])


class EliteTest(unittest.TestCase):
    """Elite types in the game's code: Double Strike plays an attack twice, Reactive Shield shields itself when hit."""

    def test_double_strike_hits_twice(self):
        # As the Archer did on turn 10 of fight 7 in logs/run8: two Arrows for 2 each.
        archer = enemy(5, hp=4, action="Attack", queue=[Attack("Arrow", 2, list(range(1, 11)), first_target=True,
                                                               effect="DoubleStrike")])
        _, outcome = step(make_state(hero_cell=3, enemies=[archer]), Action("Wait"))
        self.assertEqual(outcome.hp_lost, 4)

    def test_the_second_strike_targets_afresh(self):
        # The first Katana kills the enemy in front, so the second finds nobody there.
        _, outcome = fire(make_state(hero_cell=2, enemies=[enemy(3, hp=2)]),
                          Attack("Katana", 2, [1], first_target=True, effect="DoubleStrike"))
        self.assertEqual((outcome.kills, outcome.enemy_damage), (1, 2))

    def reactive(self, shield=False):
        target = enemy(3, hp=9)
        target.elite = "ReactiveShield"
        target.shield = shield
        return target

    def test_reactive_shield_gains_one_when_hurt(self):
        after, _ = fire(make_state(hero_cell=2, enemies=[self.reactive()]), KATANA)
        self.assertEqual((after.enemies[0].hp, after.enemies[0].shield), (7, True))

    def test_not_when_its_shield_took_the_hit(self):
        after, _ = fire(make_state(hero_cell=2, enemies=[self.reactive(shield=True)]), KATANA)
        self.assertEqual((after.enemies[0].hp, after.enemies[0].shield), (9, False))

    def test_a_second_hit_in_the_volley_meets_the_new_shield(self):
        after, _ = fire(make_state(hero_cell=2, enemies=[self.reactive()]),
                        Attack("Katana", 2, [1], first_target=True, effect="DoubleStrike"))
        self.assertEqual((after.enemies[0].hp, after.enemies[0].shield), (7, False))

    def test_known_elites_raise_no_warning(self):
        row = {"tiles": [], "hero": {"queue": []}, "skills": [],
               "enemies": [{"kind": "X", "queue": [], "elite": e} for e in ("ReactiveShield", "DoubleStrike", "Quick")]}
        self.assertEqual(unmodeled_content(row), [])


class ShadowKamaTest(unittest.TestCase):
    """ShadowKamaAttack in the game's code: the first agent its range finds, and nobody else."""

    def test_it_strikes_2_ahead_past_anyone_between(self):
        after, _ = fire(make_state(hero_cell=0, enemies=[enemy(1, hp=9), enemy(2, hp=9)]), Attack("ShadowKama", 3, [2]))
        self.assertEqual([e.hp for e in after.enemies], [9, 6])

    def test_with_a_wider_range_only_the_first_found(self):
        after, _ = fire(make_state(hero_cell=0, enemies=[enemy(2, hp=9), enemy(3, hp=9)]), Attack("ShadowKama", 3, [2, 3]))
        self.assertEqual([e.hp for e in after.enemies], [6, 9])


class PotionTest(unittest.TestCase):
    """Each potion's Effect in the game's code, and the player's rules for when F1 uses one."""

    def pinned(self, two=False):
        # The hero between enemies or against the wall, with no tiles and no special move: nothing dodges.
        right = enemy(3, hp=9, action="Attack", queue=[KATANA])
        enemies = [enemy(1, facing=1, hp=9, action="Attack", queue=[KATANA]), right] if two else [right]
        state = make_state(hero_cell=2 if two else 0, enemies=enemies, swap_charge=0)
        if not two:
            right.cell = 1
        state.tiles = []
        return state

    def plan(self, state):
        return potion_plan(state, rank_actions(state, depth=1))

    def test_each_potion_is_used_up(self):
        state = make_state(enemies=[enemy(3)])
        state.potions = ["Shield", "Shield"]
        self.assertEqual(apply_potion(state, "Shield").potions, ["Shield"])

    def test_effects(self):
        state = make_state(enemies=[enemy(3, hp=9, action="MoveLeft")])
        state.hero.hp = 5
        state.potions = list(SIMULATED_POTIONS)
        self.assertEqual(apply_potion(state, "Edamame").hero.hp, 8)
        self.assertTrue(apply_potion(state, "Shield").hero.shield)
        frozen = apply_potion(state, "MassIce").enemies[0]
        self.assertEqual((frozen.ice, frozen.action), (ICE_TURNS, "Wait"))
        flipped = apply_potion(state, "RainOfMirrors").enemies[0]
        self.assertEqual((flipped.facing, flipped.action), (1, "MoveRight"))
        self.assertEqual(apply_potion(state, "MassPoison").enemies[0].poison, 3)
        self.assertTrue(apply_potion(state, "MassCurse").enemies[0].curse)
        state.tiles[0].charge = 0
        state.swap_charge = 0
        cooled = apply_potion(state, "CoolUp")
        self.assertEqual((cooled.tiles[0].ready, cooled.swap_charge), (True, cooled.swap_cooldown))

    def test_heal_only_when_none_of_it_is_wasted(self):
        state = make_state(enemies=[enemy(4)])
        state.potions = ["Edamame"]
        state.hero.hp = 8
        self.assertEqual(self.plan(state)[0], None)
        state.hero.hp = 7
        self.assertEqual(self.plan(state)[0], "Edamame")

    def test_the_shield_is_preferred_when_it_saves_as_much(self):
        state = self.pinned()
        state.potions = ["MassIce", "Shield"]
        self.assertEqual(self.plan(state)[0], "Shield")

    def test_freeze_time_when_it_stops_more_than_one_hit(self):
        state = self.pinned(two=True)
        state.potions = ["Shield", "MassIce"]
        self.assertEqual(self.plan(state)[0], "MassIce")

    def test_cool_up_avoids_damage_by_recharging_swap(self):
        state = self.pinned()
        state.potions = ["CoolUp"]
        self.assertEqual(self.plan(state)[0], "CoolUp")  # The swap gets the hero past the Katana.

    def test_cool_up_comes_first_when_it_saves_as_much(self):
        state = self.pinned()
        state.potions = ["Shield", "CoolUp"]
        self.assertEqual(self.plan(state)[0], "CoolUp")

    def test_nothing_defensive_without_damage_coming(self):
        state = make_state(enemies=[enemy(4)])
        state.potions = ["Shield", "MassIce", "RainOfMirrors"]
        self.assertEqual(self.plan(state)[0], None)

    def test_attacking_potions_only_with_every_slot_full(self):
        state = make_state(hero_cell=2, enemies=[enemy(3, hp=4)], queue=["Swirl"])
        state.potions = ["MassCurse", "Shield", "Shield"]
        ranked = rank_actions(state, depth=1)
        self.assertEqual(potion_plan(state, ranked)[0], "MassCurse")  # Doubles Swirl's 2 into a kill.
        state.potion_slots = 4
        self.assertEqual(potion_plan(state, ranked)[0], None)
        ranked[0].score = -1000  # However hard the board, with a slot free.
        self.assertEqual(potion_plan(state, ranked)[0], None)

    def test_big_pockets_adds_a_slot(self):
        row = {"cells": 5, "tiles": [], "enemies": [], "skills": [{"name": "BigPockets", "level": 1}],
               "hero": {"kind": "H", "cell": 0, "facing": "Right", "hp": 9, "maxHp": 9, "shield": False, "queue": [],
                        "action": "Wait", "special": {"charge": 3, "cooldown": 3}}}
        self.assertEqual(state_from_log(row).potion_slots, 4)

    def test_d6_is_the_last_resort_against_damage(self):
        state = self.pinned(two=True)
        state.potions = ["D6"]
        self.assertEqual(self.plan(state)[0], "D6")
        state.potions = ["D6", "Shield"]
        self.assertEqual(self.plan(state)[0], "Shield")

    def test_no_d6_without_damage_coming(self):
        state = make_state(enemies=[enemy(4)])
        state.potions = ["D6"]
        self.assertEqual(self.plan(state)[0], None)


class DynamicBoostTest(unittest.TestCase):
    """DynamicBoostSkill in the game's code: after an attack that moves or turns the hero, its later hits that turn get
    the skill's level added. The move attack's own hit doesn't: the game raises its event after that hit."""

    def test_a_free_play_dash_first_boosts_what_follows(self):
        # The Jujitsuka's kit in logs/run9: a Free Play Dash closes in and turns the boost on, so Sai's counter on an
        # enemy about to attack does 2 x 2 + 1 = 5 and kills it. Without the boost it leaves 1 HP and takes the Katana.
        def best(bonus):
            state = jujitsuka(hero_cell=0, enemies=[enemy(3, hp=5, action="Attack", queue=[KATANA])])
            sai = Tile(Attack("Sai", 2, [1], first_target=True), 5, 5, in_queue=True)
            state.tiles = [Tile(Attack("Dash", 0, [1, 2, 3, 4, 5, 6]), 3, 3, free_play=True), sai]
            state.queue_tiles, state.hero.queue = [sai], [sai.attack]
            state.dynamic_bonus = bonus
            return rank_actions(state, depth=1)[0].labels[0]
        self.assertEqual(best(1), "Attack Dash (free) > Sai")
        self.assertNotEqual(best(0)[:6], "Attack")
    SHARP_TURN = Attack("TurnAround", 1, [-1, 1])

    def volley(self, attacks, level=1):
        state = make_state(hero_cell=3, enemies=[enemy(2, hp=9), enemy(4, hp=9)])
        state.cells = 7
        state.dynamic_bonus = level
        tiles = [Tile(a, cooldown=3, charge=3, in_queue=True) for a in attacks]
        state.tiles, state.queue_tiles, state.hero.queue = tiles, list(tiles), list(attacks)
        after, _ = step(state, Action("Attack"))
        return sorted((e.cell, 9 - e.hp) for e in after.enemies)

    def test_a_hit_after_sharp_turn_is_boosted(self):
        # Sharp Turn hits both sides for 1, then Katana, now facing left, hits cell 2 for 2 plus 1.
        self.assertEqual(self.volley([self.SHARP_TURN, KATANA]), [(2, 4), (4, 1)])

    def test_the_turn_itself_isnt(self):
        self.assertEqual(self.volley([self.SHARP_TURN]), [(2, 1), (4, 1)])

    def test_nothing_without_the_skill(self):
        self.assertEqual(self.volley([self.SHARP_TURN, KATANA], level=0), [(2, 3), (4, 1)])

    def test_flipping_doesnt_turn_it_on(self):
        state = make_state(hero_cell=3, enemies=[enemy(2, hp=9)])
        state.dynamic_bonus = 1
        after, _ = step(state, Action("Flip"))
        self.assertFalse(after.boosted)

    def test_it_lasts_only_the_turn(self):
        state = make_state(hero_cell=3, enemies=[enemy(2, hp=9), enemy(4, hp=9)])
        state.dynamic_bonus = 1
        state.boosted = True
        after, _ = step(state, Action("Wait"))
        self.assertFalse(after.boosted)


class SniperSkillTest(unittest.TestCase):
    """SniperSkill in the game's code: the hero's hits on targets 4 or more cells away get its level added,
    before a curse doubles them. Shockwave and collision hits aren't the hero's own."""
    LIGHTNING = Attack("Lightning", 2, [1, 2, 3, 4, 5, 6])

    def hit_from(self, distance, level=1, curse=False, attack=None):
        target = enemy(distance, hp=9)
        target.curse = curse
        state = make_state(hero_cell=0, enemies=[target])
        state.cells = 9
        state.sniper_bonus = level
        after, _ = fire(state, attack or self.LIGHTNING)
        return 9 - after.enemies[0].hp

    def test_four_cells_away_adds_its_level(self):
        self.assertEqual((self.hit_from(3), self.hit_from(4), self.hit_from(6, level=2)), (2, 3, 4))

    def test_a_curse_doubles_the_bonus_too(self):
        self.assertEqual(self.hit_from(4, curse=True), 6)

    def test_a_shockwave_hit_gets_none(self):
        state = make_state(hero_cell=0, enemies=[enemy(4, hp=9), enemy(5, hp=9)])
        state.cells = 9
        state.sniper_bonus = 1
        wave = Attack("Lightning", 2, [1, 2, 3, 4], effect="Shockwave")
        after, _ = fire(state, wave)
        self.assertEqual([e.hp for e in after.enemies], [5, 8])

    def test_read_from_the_log(self):
        row = {"cells": 5, "tiles": [], "enemies": [], "skills": [{"name": "Sniper", "level": 2}],
               "hero": {"kind": "H", "cell": 0, "facing": "Right", "hp": 9, "maxHp": 9, "shield": False, "queue": [],
                        "action": "Wait", "special": {"charge": 3, "cooldown": 3}}}
        self.assertEqual(state_from_log(row).sniper_bonus, 2)

    def test_it_makes_long_reach_worth_standing_off_for(self):
        def best_distance(bonus):
            scores = {}
            for distance in range(1, 6):
                state = make_state(hero_cell=0, enemies=[enemy(distance, hp=9)])
                state.cells = 9
                state.tiles = [Tile(self.LIGHTNING, cooldown=2, charge=2)]
                state.sniper_bonus = bonus
                terms = leaf_terms(state)
                scores[distance] = terms["reach"] + terms["stand_off"]
            return max(scores, key=lambda d: (round(scores[d], 6), -d))
        self.assertEqual(best_distance(0), 2)
        self.assertEqual(best_distance(1), 4)


class SharpTurnTest(unittest.TestCase):
    """TurnAround in the game's code: the user turns around first, then strikes what's in range that way."""
    SHARP_TURN = Attack("TurnAround", 2, [1])

    def with_free_turn(self, enemies, queue=(), hero_cell=3):
        state = make_state(hero_cell=hero_cell, enemies=enemies, queue=queue)
        state.cells = 7
        state.tiles.append(Tile(self.SHARP_TURN, cooldown=3, charge=3, free_play=True))
        return state

    def test_it_turns_then_strikes_behind(self):
        after, outcome = fire(make_state(hero_cell=3, enemies=[enemy(2, hp=5)]), self.SHARP_TURN)
        self.assertEqual((after.hero.facing, after.enemies[0].hp, outcome.wasted_attacks), (-1, 3, 0))

    def test_turning_alone_isnt_a_wasted_attack(self):
        after, outcome = fire(make_state(hero_cell=3, enemies=[enemy(5, hp=5)]), self.SHARP_TURN)
        self.assertEqual((after.hero.facing, outcome.wasted_attacks), (-1, 0))

    def test_as_a_free_tile_the_next_tile_fires_the_new_way(self):
        state = self.with_free_turn([enemy(2, hp=5)], queue=["Swirl"])
        state.tiles[0].attack = Attack("Katana", 2, [1])
        sharp = len(state.tiles) - 1
        after, _ = step(state, Action("Attack", order=(sharp, 0)))
        self.assertEqual(after.enemies[0].hp, 1)

    def test_it_can_be_fired_from_hand_with_nothing_loaded(self):
        state = self.with_free_turn([enemy(2, hp=5)])
        attacks = [a for a in legal_actions(state) if a.kind == "Attack"]
        self.assertEqual([a.label(state) for a in attacks], ["Attack TurnAround (free)"])

    def test_it_raises_no_warning(self):
        tile = {"attack": {"name": "TurnAround", "effect": "None", "tileEffect": "FreePlay"}}
        self.assertEqual(unmodeled_content({"tiles": [tile], "hero": {"queue": []}, "enemies": [], "skills": []}), [])


class KeepingSmokeBombTest(unittest.TestCase):
    SMOKE = Attack("SmokeBomb", 1, [1, 2, 3, 4, 5, 6], first_target=True)

    def with_smoke(self, enemies, hero_cell=0, loaded=True, charge=5):
        state = ronin(hero_cell=hero_cell, enemies=enemies)
        state.cells = 7
        state.swap_charge = 0  # Leaves the shove out of it: see KeepingOtherMovesTest.
        tile = Tile(self.SMOKE, cooldown=5, charge=charge, in_queue=loaded)
        state.tiles = [tile]
        state.queue_tiles = [tile] if loaded else []
        state.hero.queue = [self.SMOKE] if loaded else []
        return state

    def test_a_loaded_one_with_a_target_is_worth_keeping(self):
        self.assertEqual(leaf_terms(self.with_smoke([enemy(3, hp=9)]))["escape"], 12)

    def test_one_in_hand_is_worth_a_little_less(self):
        # Loaded, it can dodge this turn. But any attack would spend it, so loading adds only a little.
        self.assertEqual(leaf_terms(self.with_smoke([enemy(3, hp=9)], loaded=False))["escape"], 8)

    def test_a_three_damage_tile_beats_it_to_the_queue_when_flanked(self):
        # v1.5 loaded the Smoke Bomb here, since only a loaded one counted as a way out.
        state = self.with_smoke([enemy(0, facing=1, hp=9), enemy(5, hp=9)], hero_cell=3, loaded=False)
        state.tiles.append(Tile(Attack("Spear", 3, [1, 2]), cooldown=3, charge=3))
        self.assertEqual(rank_actions(state, depth=1)[0].labels[0], "PlayTile Spear")

    def test_a_kill_from_here_doesnt_cancel_one_in_hand(self):
        state = self.with_smoke([enemy(3, hp=1)], loaded=False)
        spear = Tile(Attack("Spear", 3, [1, 2, 3]), cooldown=3, charge=3, in_queue=True)
        state.tiles.append(spear)
        state.queue_tiles = [spear]
        state.hero.queue = [spear.attack]
        self.assertEqual(leaf_terms(state)["escape"], 8)

    def test_one_on_cooldown_is_worth_nothing(self):
        self.assertEqual(leaf_terms(self.with_smoke([enemy(3, hp=9)], loaded=False, charge=2))["escape"], 0)

    def test_it_needs_someone_to_reach(self):
        behind = self.with_smoke([enemy(0, facing=1, hp=9)], hero_cell=3)
        self.assertEqual(leaf_terms(behind)["escape"], 4)

    def test_it_needs_a_movable_target(self):
        heavy = enemy(3, hp=9)
        heavy.movable = False
        self.assertEqual(leaf_terms(self.with_smoke([heavy]))["escape"], 4)

    def test_kept_it_counts_in_full_even_if_it_would_kill_from_here(self):
        # Whether it's about to go off is the stack's to weigh, scoring the volley against the board it leaves.
        self.assertEqual(leaf_terms(self.with_smoke([enemy(3, hp=1)]))["escape"], 12)

    def test_it_still_fires_for_a_kill(self):
        best = rank_actions(self.with_smoke([enemy(3, hp=1)]), depth=1)[0]
        self.assertEqual(best.terms.get("kills", 0), 60)

    def test_it_still_fires_to_dodge(self):
        # A Katana is coming. Trading places leaves the attacker facing away, with the hero behind it.
        attacker = enemy(1, facing=-1, hp=9, action="Attack", queue=[KATANA])
        attacker.facing = -1
        state = self.with_smoke([attacker], hero_cell=0)
        state.swap_charge = 0
        state.hero.facing = 1
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.terms.get("hp_lost", 0), 0)


class KeepingOtherMovesTest(unittest.TestCase):
    """Every move that repositions the hero or an enemy is worth something kept, by how flexible it is."""
    HOOK = Attack("GrapplingHook", 1, [1, 2, 3, 4, 5, 6], first_target=True)
    SHADOW_DASH = Attack("ShadowDash", 1, [1, 2, 3, 4, 5, 6])

    def with_tile(self, attack, enemies, loaded=True, shove_charged=False):
        state = ronin(hero_cell=0, enemies=enemies)
        state.cells = 7
        if not shove_charged:
            state.swap_charge = 0
        tile = Tile(attack, cooldown=3, charge=3, in_queue=loaded)
        state.tiles = [tile]
        state.queue_tiles = [tile] if loaded else []
        state.hero.queue = [attack] if loaded else []
        return state

    def test_a_charged_shove(self):
        state = self.with_tile(self.HOOK, [enemy(3, hp=9)], shove_charged=True)
        state.tiles[0].charge = 0
        self.assertEqual(leaf_terms(state)["escape"], 6)

    def test_with_two_way_move_it_covers_both_sides(self):
        state = self.with_tile(self.HOOK, [enemy(3, hp=9)], shove_charged=True)
        state.tiles[0].charge = 0
        state.two_way_swap = True
        self.assertEqual(leaf_terms(state)["escape"], 9)

    def test_a_hook_loaded_in_hand_and_with_nobody_to_pull(self):
        # Bringing an enemy closer almost never gets the hero out of trouble.
        self.assertAlmostEqual(leaf_terms(self.with_tile(self.HOOK, [enemy(3, hp=9)]))["escape"], 1)
        self.assertAlmostEqual(leaf_terms(self.with_tile(self.HOOK, [enemy(3, hp=9)], loaded=False))["escape"], 2 / 3)
        heavy = enemy(3, hp=9)
        heavy.movable = False
        self.assertAlmostEqual(leaf_terms(self.with_tile(self.HOOK, [heavy]))["escape"], 1 / 3)

    def test_the_hook_sets_up_a_short_reach_tile(self):
        spear = Tile(Attack("Spear", 4, [1, 2]), cooldown=5, charge=0)
        lightning = Tile(Attack("Lightning", 3, [1, 2, 3, 4, 5, 6]), cooldown=2, charge=0)
        alone = self.with_tile(self.HOOK, [enemy(3, hp=9)])
        self.assertEqual(leaf_terms(alone)["setup"], 0)
        alone.tiles.append(lightning)
        self.assertEqual(leaf_terms(alone)["setup"], 0)  # Lightning reaches them where they are.
        alone.tiles.append(spear)
        self.assertEqual(leaf_terms(alone)["setup"], 4)  # The Spear counts even while cooling down.
        in_hand = self.with_tile(self.HOOK, [enemy(3, hp=9)], loaded=False)
        in_hand.tiles.append(spear)
        self.assertAlmostEqual(leaf_terms(in_hand)["setup"], 4 * 2 / 3)

    def load_choice(self, wave_damage, plain_damage, effect="Shockwave"):
        # The plain tile comes first, so a tie would go to it.
        state = self.with_tile(Attack("Katana", plain_damage, [1, 2]), [enemy(5, hp=9)], loaded=False)
        state.tiles.append(Tile(Attack("Katana", wave_damage, [1, 2], effect=effect), cooldown=3, charge=3))
        best = next(c for c in rank_actions(state, depth=1) if c.actions[0].kind == "PlayTile")
        return state.tiles[best.actions[0].tile].attack

    def test_the_curse_version_of_an_identical_tile_is_loaded_first(self):
        self.assertEqual(self.load_choice(2, 2, effect="Curse").effect, "Curse")
        self.assertEqual(self.load_choice(2, 3, effect="Curse").value, 3)

    def test_the_shockwave_version_of_an_identical_tile_is_loaded_first(self):
        self.assertEqual(self.load_choice(2, 2).effect, "Shockwave")

    def test_but_not_over_a_point_more_damage(self):
        self.assertEqual(self.load_choice(2, 3).value, 3)

    def test_it_counts_while_loaded(self):
        state = self.with_tile(Attack("Spear", 4, [1, 2], effect="Shockwave"), [enemy(5, hp=9)])
        self.assertEqual(leaf_terms(state)["effects"], 0.5)

    def test_a_shadow_dash(self):
        self.assertEqual(leaf_terms(self.with_tile(self.SHADOW_DASH, [enemy(3, hp=9)]))["escape"], 9)

    def test_each_beyond_the_best_counts_for_half(self):
        state = self.with_tile(self.SHADOW_DASH, [enemy(3, hp=9)], shove_charged=True)
        self.assertEqual(leaf_terms(state)["escape"], 12)

    def test_a_kill_from_here_doesnt_cancel_a_loaded_tile_kept(self):
        # The shove, 6, and half the hook's 1. The kill the hook could make is the stack's to weigh.
        state = self.with_tile(self.HOOK, [enemy(3, hp=1)], shove_charged=True)
        self.assertEqual(leaf_terms(state)["escape"], 6.5)


class KeepingSwapTest(unittest.TestCase):
    def test_a_charged_swap_is_a_way_out_kept(self):
        self.assertEqual(leaf_terms(make_state(enemies=[enemy(3)]))["escape"], 12)

    def test_one_charging_is_worth_nothing(self):
        state = make_state(enemies=[enemy(3)])
        state.swap_charge = state.swap_cooldown - 1
        self.assertEqual(leaf_terms(state)["escape"], 0)

    def test_going_backward_too_makes_it_worth_more(self):
        state = make_state(enemies=[enemy(3)])
        state.two_way_swap = True
        self.assertEqual(leaf_terms(state)["escape"], 18)

    def test_a_kill_from_here_doesnt_cancel_it(self):
        # Firing tiles never spends a Swap, unlike a loaded Smoke Bomb.
        state = make_state(hero_cell=2, enemies=[enemy(3, hp=1)], queue=[KATANA])
        self.assertEqual(leaf_terms(state)["escape"], 12)

    def test_nobody_to_swap_with_yet_doesnt_cancel_it(self):
        heavy = enemy(3)
        heavy.movable = False
        self.assertEqual(leaf_terms(make_state(enemies=[heavy]))["escape"], 12)

    def swap_damage_board(self, damage):
        state = make_state(hero_cell=2, enemies=[enemy(3, hp=9)])
        state.swap_damage = damage
        return rank_actions(state, depth=1)[0].labels[0]

    def test_two_damage_isnt_worth_spending_it_for(self):
        self.assertNotIn("(swap)", self.swap_damage_board(2))

    def test_three_damage_is(self):
        self.assertIn("(swap)", self.swap_damage_board(3))


class KitPositionTest(unittest.TestCase):
    SPEAR = Attack("Spear", 2, [1, 2])
    HOOK = Attack("GrapplingHook", 1, [1, 2, 3, 4, 5, 6], first_target=True)
    SMOKE = Attack("SmokeBomb", 1, [1, 2, 3, 4, 5, 6], first_target=True)

    def kit(self, *tiles, hero_cell=3, enemies=(), swap=False):
        state = make_state(hero_cell=hero_cell, enemies=list(enemies))
        state.cells = 9
        if not swap:
            state.special = "PushSpecialMove"
        state.tiles = [Tile(attack, cooldown=5, charge=5 - wait) for attack, wait in tiles]
        return state

    def best_distance(self, *tiles, swap=False):
        """Where the hero would rather stand from a lone enemy, by reach and stand-off: the nearest of the best."""
        scores = {}
        for distance in range(1, 6):
            terms = leaf_terms(self.kit(*tiles, hero_cell=1, enemies=[enemy(1 + distance, hp=9)], swap=swap))
            scores[distance] = terms["reach"] + terms["stand_off"]
        return max(scores, key=lambda d: (round(scores[d], 6), -d))

    def test_the_swap_hero_follows_its_tiles_too(self):
        self.assertEqual(self.best_distance((KATANA, 0), swap=True), 1)
        self.assertEqual(self.best_distance((self.SPEAR, 0), (self.HOOK, 0), swap=True), 2)

    def test_melee_without_swap_still_has_to_be_adjacent(self):
        self.assertEqual(self.best_distance((KATANA, 0)), 1)

    def test_a_spear_stands_at_its_full_reach(self):
        self.assertEqual(self.best_distance((self.SPEAR, 0)), 2)

    def test_long_reach_stands_off(self):
        self.assertEqual(self.best_distance((self.HOOK, 0)), 2)

    def test_a_tile_on_cooldown_counts_for_less(self):
        ready = leaf_terms(self.kit((self.SPEAR, 0), enemies=[enemy(5)]))["reach"]
        waiting = leaf_terms(self.kit((self.SPEAR, 3), enemies=[enemy(5)]))["reach"]
        self.assertLess(waiting, ready)
        self.assertGreater(waiting, 0)

    def test_an_adjacent_enemy_costs_something_whatever_the_kit(self):
        for tiles in (((self.SPEAR, 0),), ((KATANA, 0),), ()):
            self.assertEqual(leaf_terms(self.kit(*tiles, hero_cell=3, enemies=[enemy(4)]))["stand_off"], -1.5)

    def test_too_far_earns_less_reach(self):
        near = leaf_terms(self.kit((self.SPEAR, 0), hero_cell=3, enemies=[enemy(5)]))["reach"]
        far = leaf_terms(self.kit((self.SPEAR, 0), hero_cell=1, enemies=[enemy(6)]))["reach"]
        self.assertLess(far, near)

    def test_a_swap_on_cooldown_is_no_way_out(self):
        state = self.kit((self.SPEAR, 0), enemies=[enemy(0, facing=1), enemy(6)], swap=True)
        state.swap_charge = 0
        self.assertEqual(leaf_terms(state)["surrounded"], -15)

    def test_flanked_with_no_way_out_is_much_worse(self):
        enemies = [enemy(0, facing=1), enemy(6)]
        self.assertEqual(leaf_terms(self.kit((self.SPEAR, 0), enemies=enemies))["surrounded"], -15)
        self.assertEqual(leaf_terms(self.kit((self.SPEAR, 0), enemies=enemies, swap=True))["surrounded"], -6)

    def test_surrounded_with_no_way_out_is_much_worse(self):
        enemies = [enemy(2, facing=1), enemy(4)]
        self.assertEqual(leaf_terms(self.kit((self.SPEAR, 0), enemies=enemies))["surrounded"], -50)
        self.assertEqual(leaf_terms(self.kit((self.SPEAR, 0), enemies=enemies, swap=True))["surrounded"], -20)

    def test_a_ready_smoke_bomb_that_reaches_someone_is_a_way_out(self):
        enemies = [enemy(0, facing=1), enemy(6)]
        self.assertFalse(_has_way_out(self.kit((self.SMOKE, 2), enemies=enemies)))
        in_hand = self.kit((self.SMOKE, 0), enemies=enemies)
        self.assertTrue(_has_way_out(in_hand))
        self.assertEqual(leaf_terms(in_hand)["surrounded"], -6)
        in_hand.tiles[0].in_queue = True
        in_hand.queue_tiles = [in_hand.tiles[0]]
        in_hand.hero.queue = [self.SMOKE]
        self.assertTrue(_has_way_out(in_hand))

    def test_one_with_nobody_to_reach_isnt(self):
        heavy = enemy(6)
        heavy.movable = False
        state = self.kit((self.SMOKE, 0), enemies=[enemy(0, facing=1), heavy])
        state.tiles[0].in_queue = True
        state.queue_tiles = [state.tiles[0]]
        self.assertFalse(_has_way_out(state))


class WarningsTest(unittest.TestCase):
    def notes(self, enemy_row, skills=()):
        return unmodeled_content({"tiles": [], "hero": {"queue": []}, "enemies": [enemy_row], "skills": list(skills)})

    def test_summon_is_ignored_on_purpose(self):
        row = {"kind": "X", "queue": [{"name": "Summon", "effect": "DoubleStrike"}], "traits": []}
        self.assertEqual(self.notes(row), [])

    def test_harmless_traits_raise_no_warning(self):
        row = {"kind": "X", "queue": [], "traits": ["Aggro", "Heavy", "Quick", "Unfreezable"]}
        self.assertEqual(self.notes(row), [])

    def test_unfriendly_fire_raises_no_warning(self):
        self.assertEqual(self.notes({"kind": "X", "queue": [], "traits": []}, ["UnfriendlyFire"]), [])

    def test_unknown_things_still_do(self):
        self.assertEqual(self.notes({"kind": "X", "queue": [], "traits": ["Odd"]}), ["X trait Odd"])




class ReactiveShieldTest(unittest.TestCase):
    """ReactiveShieldSkill in the game's code: once the hero takes damage and lives, it gets a shield if it had none."""

    def board(self, queue):
        state = make_state(enemies=[enemy(3, action="Attack", queue=queue)])
        state.reactive_shield = True
        return state

    def test_taking_damage_brings_a_shield(self):
        after, outcome = step(self.board([KATANA]), Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.hero.shield), (2, True))

    def test_it_blocks_the_next_hit_the_same_turn(self):
        after, outcome = step(self.board([KATANA, KATANA]), Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.hero.shield), (2, False))

    def test_a_blocked_hit_brings_none(self):
        state = self.board([KATANA])
        state.hero.shield = True
        after, outcome = step(state, Action("Wait"))
        self.assertEqual((outcome.hp_lost, after.hero.shield), (0, False))

    def test_a_hit_still_costs_half_a_shield_or_more(self):
        # The new shield doesn't make a hit free: going without one is worth half a shield with the skill.
        from evaluator import _shield_value
        before = self.board([KATANA])
        after, _ = step(before, Action("Wait"))
        self.assertEqual(_shield_value(after) - _shield_value(before), WEIGHTS["shield"] / 2)
        self.assertGreater(-WEIGHTS["hp_lost"], WEIGHTS["shield"] / 2)


def shadow(hero_cell=2, facing=1, enemies=(), swap_charge=4):
    state = make_state(hero_cell=hero_cell, facing=facing, enemies=enemies, swap_charge=swap_charge)
    state.cells = 7
    state.special = "PhaseSpecialMove"
    state.hero.kind = "Shadow"
    return state


class ShadowDashTest(unittest.TestCase):
    """ShadowHero in the game's code: every move is a dash to the last free cell that way."""

    def test_a_move_dashes_up_to_the_next_enemy(self):
        after, _ = step(shadow(hero_cell=1, enemies=[enemy(5)]), Action("MoveRight"))
        self.assertEqual(after.hero.cell, 4)

    def test_a_move_dashes_to_the_wall(self):
        after, _ = step(shadow(hero_cell=4, enemies=[enemy(5)]), Action("MoveLeft"))
        self.assertEqual(after.hero.cell, 0)

    def test_others_still_step_one_cell(self):
        state = shadow(hero_cell=1, enemies=[enemy(5)])
        state.hero.kind = "Wanderer"
        self.assertEqual(step(state, Action("MoveRight"))[0].hero.cell, 2)

    def test_the_stack_only_counts_cells_a_dash_reaches(self):
        # A Katana needs the enemy adjacent: one dash right gets there, from four cells away.
        state = shadow(hero_cell=0, enemies=[enemy(5)])
        katana = Tile(KATANA, 3, 3, in_queue=True)
        state.tiles, state.queue_tiles, state.hero.queue = [katana], [katana], [KATANA]
        self.assertGreater(leaf_terms(state)["stack"], 0)
        state.hero.kind = "Wanderer"
        self.assertEqual(leaf_terms(state)["stack"], 0)


class PhaseSpecialMoveTest(unittest.TestCase):
    """PhaseSpecialMove in the game's code: through the agents ahead to the first free cell past them."""

    def test_it_passes_a_line_of_enemies_and_nobody_moves(self):
        state = shadow(enemies=[enemy(3), enemy(4)])
        after, _ = step(state, Action("MoveRight"))
        self.assertEqual((after.hero.cell, [e.cell for e in after.enemies], after.swap_charge), (5, [3, 4], 0))

    def test_it_dodges_what_the_enemy_passed_aims_at_its_old_cell(self):
        state = shadow(enemies=[enemy(3, action="Attack", queue=[KATANA])])
        after, outcome = step(state, Action("MoveRight"))
        self.assertEqual((after.hero.cell, outcome.hp_lost), (4, 0))

    def test_it_goes_through_an_enemy_that_cant_be_moved(self):
        wall = enemy(3)
        wall.movable = False
        self.assertTrue(can_use_special(shadow(enemies=[wall]), 1))

    def test_not_with_no_free_cell_before_the_wall(self):
        self.assertFalse(can_use_special(shadow(hero_cell=4, enemies=[enemy(5), enemy(6)]), 1))

    def test_only_forward_without_two_way_move(self):
        state = shadow(enemies=[enemy(1)])
        self.assertFalse(can_use_special(state, -1))
        state.two_way_swap = True
        self.assertTrue(can_use_special(state, -1))

    def test_damaging_move_hits_every_one_passed(self):
        # PhaseSpecialMove.Perform applies the effect in a loop over the agents crossed; logs/run15 shows Mamushi
        # Move poisoning both enemies a Phase passed.
        state = shadow(enemies=[enemy(3), enemy(4)])
        state.swap_damage = 1
        after, _ = step(state, Action("MoveRight"))
        self.assertEqual([e.hp for e in after.enemies], [2, 2])

    def test_a_charged_phase_counts_as_escape(self):
        state = shadow(enemies=[enemy(3)])
        kept = leaf_terms(state)
        state.swap_charge = 0
        self.assertGreater(kept["escape"], leaf_terms(state).get("escape", 0))


class CrossbowTest(unittest.TestCase):
    """CrossbowAttack in the game's code: a loaded shot hits the first two in range and empties; empty, it reloads."""
    LOADED = Attack("Crossbow", 3, list(range(1, 7)))

    def board(self, value, enemies):
        state = make_state(enemies=enemies)
        state.cells = 7
        bow = Tile(dataclasses.replace(self.LOADED, value=value), 5, 5, in_queue=True, base_value=3)
        state.tiles, state.queue_tiles, state.hero.queue = [bow], [bow], [bow.attack]
        return state

    def test_a_shot_hits_the_first_two_and_empties_it(self):
        after, outcome = step(self.board(3, [enemy(3, hp=5), enemy(4, hp=5), enemy(5, hp=5)]), Action("Attack"))
        self.assertEqual([e.hp for e in after.enemies], [2, 2, 5])
        self.assertEqual((after.tiles[0].attack.value, after.tiles[0].charge), (0, 0))

    def test_empty_it_reloads_and_hits_nobody(self):
        after, outcome = step(self.board(0, [enemy(3)]), Action("Attack"))
        self.assertEqual((after.enemies[0].hp, after.tiles[0].attack.value, outcome.reloads), (3, 3, 1))

    def test_the_board_it_came_from_keeps_its_value(self):
        state = self.board(3, [enemy(3)])
        step(state, Action("Attack"))
        self.assertEqual(state.tiles[0].attack.value, 3)

    def test_a_reload_isnt_a_wasted_attack(self):
        # logs/run12: F1 could never fire a reload, since attacks firing at nothing are dropped, so it kept
        # loading the empty Crossbow and sending it back to hand.
        state = self.board(0, [enemy(0, facing=1)])
        _, outcome = step(state, Action("Attack"))
        self.assertEqual(outcome.wasted_attacks, 0)
        self.assertIn("Attack", [line.labels[0] for line in rank_actions(state)])

    def test_its_pierce_is_worth_more_than_its_damage_loaded(self):
        state = self.board(3, [enemy(5, hp=5)])
        terms = leaf_terms(state)
        self.assertAlmostEqual(terms["loaded"], WEIGHTS["loaded_damage"] * 3 * WEIGHTS["pierce"]["Crossbow"])

    def test_a_reload_is_worth_what_its_loaded_tile_holds(self):
        # The reload and the loaded term read the same values, pierce included, so they move together.
        loaded = leaf_terms(self.board(3, [enemy(5, hp=5)]))["loaded"]
        _, outcome = step(self.board(0, [enemy(5, hp=5)]), Action("Attack"))
        from evaluator import outcome_terms
        self.assertAlmostEqual(outcome_terms(outcome, False, 1)["reload"], WEIGHTS["ready_tile"] + loaded)

    def test_a_free_play_reload_joins_an_attack_from_hand(self):
        state = self.board(0, [enemy(3, hp=2)])
        bow = state.tiles[0]
        bow.in_queue, bow.free_play = False, True
        swirl = Tile(SWIRL, 3, 3, in_queue=True)
        state.tiles = [swirl, bow]
        state.queue_tiles, state.hero.queue = [swirl], [SWIRL]
        best = rank_actions(state)[0]
        self.assertTrue(best.labels[0].startswith("Attack") and "Crossbow" in best.labels[0], best.labels[0])
        self.assertGreater(best.terms["reload"], 0)

    def test_a_free_play_tile_alone_is_an_attack_with_the_queue_empty(self):
        state = self.board(0, [enemy(3)])
        bow = state.tiles[0]
        bow.in_queue, bow.free_play = False, True
        state.queue_tiles, state.hero.queue = [], []
        self.assertIn(Action("Attack", order=(0,)), legal_actions(state))

    def test_tied_values_stay_tied(self):
        escapes = WEIGHTS["escape_values"]
        self.assertEqual(escapes["PhaseSpecialMove"], escapes["SwapSpecialMove"])
        self.assertEqual(escapes["ThrowSpecialMove"], escapes["PushSpecialMove"])
        for name in ("SmokeBomb", "ShadowDash", "Charge"):
            self.assertEqual(escapes["Back" + name], escapes[name])

    def test_a_loaded_reload_is_worth_firing(self):
        # Nobody in range, so only the reload makes the stack worth anything.
        state = self.board(0, [])
        state.enemies = [enemy(0, facing=1)]
        self.assertGreater(leaf_terms(state)["stack"], 0)


class ReachByMovementTest(unittest.TestCase):
    """Reach credit counts the actions it really takes to get in range, not the cells."""

    def katana_board(self, hero_cell, enemies, kind="Wanderer"):
        state = shadow(hero_cell=hero_cell, enemies=enemies)
        state.hero.kind = kind
        katana = Tile(KATANA, 3, 3, in_queue=True)
        state.tiles, state.queue_tiles, state.hero.queue = [katana], [katana], [KATANA]
        return state

    def test_a_walker_pays_a_quarter_per_step(self):
        from evaluator import _reach_value
        state = self.katana_board(1, [enemy(4)])
        self.assertAlmostEqual(_reach_value(state, state.enemies[0]), WEIGHTS["reach"] * 2 * 0.5)

    def test_the_shadow_gets_there_in_one_dash(self):
        from evaluator import _reach_value
        state = self.katana_board(1, [enemy(4)], kind="Shadow")
        self.assertAlmostEqual(_reach_value(state, state.enemies[0]), WEIGHTS["reach"] * 2 * 0.75)

    def test_nobody_walks_through_a_blocker(self):
        from evaluator import _reach_value
        # The 1 HP Ashigaru is the target; the 3 HP one stands between. A Katana can't get to it by walking.
        state = self.katana_board(1, [enemy(2), enemy(4, hp=1)])
        self.assertEqual(_reach_value(state, state.enemies[1]), 0.0)

    def test_a_tile_facing_away_pays_a_flip(self):
        from evaluator import _reach_value
        state = self.katana_board(3, [enemy(4)])
        self.assertAlmostEqual(_reach_value(state, state.enemies[0]), WEIGHTS["reach"] * 2)
        state.hero.facing = -1
        self.assertAlmostEqual(_reach_value(state, state.enemies[0]), WEIGHTS["reach"] * 2 * 0.75)

    def test_back_strike_needs_the_target_behind(self):
        # logs/run12: with Kowa in front, Back Strike counted as if it could hit him.
        from evaluator import _reach_value
        state = self.katana_board(2, [enemy(3, hp=6)])
        back = Tile(Attack("BackStrike", 3, [-1], first_target=True, effect="DoubleStrike"), 3, 3)
        state.tiles = [back]
        state.queue_tiles, state.hero.queue = [], []
        self.assertAlmostEqual(_reach_value(state, state.enemies[0]), WEIGHTS["reach"] * 3 * 0.75)

    def test_a_phase_past_the_blocker_counts_as_its_use(self):
        from evaluator import _kept_moves, _reach_gain
        state = self.katana_board(1, [enemy(2), enemy(4, hp=1)], kind="Shadow")
        state.special = "PhaseSpecialMove"
        # Phasing to cell 3 puts the Katana on the 1 HP target, one action away.
        self.assertAlmostEqual(_reach_gain(state, "special"), WEIGHTS["reach"] * 1 * 0.75)
        # It counts as one of the Phase's uses, the larger: here its escape value.
        self.assertEqual(_kept_moves(state)["move_reach"], 0.0)


class BackStrikeTest(unittest.TestCase):
    """BackStrikeAttack in the game's code: the first agent on the cell behind, a plain hit."""
    BACK_STRIKE = Attack("BackStrike", 3, [-1], first_target=True)

    def test_it_hits_behind_and_not_ahead(self):
        state = make_state(enemies=[enemy(1, facing=1, hp=5), enemy(3, hp=5)])
        after, outcome = fire(state, self.BACK_STRIKE)
        self.assertEqual([e.hp for e in after.enemies], [2, 5])
        row = {"tiles": [{"attack": {"name": "BackStrike"}}], "hero": {"queue": []}, "enemies": [], "skills": []}
        self.assertEqual(unmodeled_content(row), [])


class MamushiMoveTest(unittest.TestCase):
    """MamushiMoveSkill in the game's code: the special move poisons its target, before a shove pushes it."""

    def test_the_shove_poisons_and_pushes(self):
        state = ronin(enemies=[enemy(3)])
        state.special_poison = True
        after, _ = step(state, Action("MoveRight"))
        target = after.enemies[0]
        # Poisoned for 3, and the first tick lands at the end of this turn.
        self.assertEqual((target.cell, target.poison, target.hp), (4, 2, 2))

    def test_no_poison_on_a_target_damaging_move_kills(self):
        state = ronin(enemies=[enemy(3, hp=1)])
        state.special_poison, state.swap_damage = True, 1
        after, outcome = step(state, Action("MoveRight"))
        self.assertEqual((after.enemies, outcome.kills), ([], 1))


class HeroMirrorTest(unittest.TestCase):
    """MirrorAttack used by the hero: a Free Play tile, cooldown 6, that moves its user across the room's middle."""
    MIRROR = Attack("Mirror", 0, [])

    def test_the_hero_trades_places_across_the_middle_and_both_turn(self):
        state = make_state(hero_cell=1, enemies=[enemy(2), enemy(3)])
        after, outcome = fire(state, self.MIRROR)
        cells = sorted((e.cell, e.facing) for e in after.enemies)
        self.assertEqual((after.hero.cell, after.hero.facing, cells), (3, -1, [(1, 1), (2, -1)]))
        self.assertEqual(outcome.wasted_attacks, 0)

    def test_not_across_an_immovable_enemy(self):
        wall = enemy(3)
        wall.movable = False
        _, outcome = fire(make_state(hero_cell=1, enemies=[wall]), self.MIRROR)
        self.assertEqual(outcome.wasted_attacks, 1)

    def test_a_free_play_mirror_in_hand_is_worth_as_much_as_loaded(self):
        from evaluator import _kept_moves
        state = make_state(hero_cell=1, enemies=[enemy(3)], swap_charge=0)
        state.tiles = [Tile(self.MIRROR, 6, 6, free_play=True)]
        state.queue_tiles, state.hero.queue = [], []
        self.assertEqual(_kept_moves(state)["escape"], WEIGHTS["escape_values"]["Mirror"])


class TwinTessenTest(unittest.TestCase):
    """TwinTessenAttack in the game's code: hits both neighbours, then pushes each movable one away."""
    TESSEN = Attack("TwinTessen", 1, [-1, 1])

    def test_it_hits_both_sides_and_pushes_them_apart(self):
        state = make_state(hero_cell=3, enemies=[enemy(2, facing=1), enemy(4)])
        state.cells = 7
        after, outcome = fire(state, self.TESSEN)
        self.assertEqual(sorted((e.cell, e.hp) for e in after.enemies), [(0, 2), (6, 2)])
        self.assertEqual(outcome.enemy_damage, 2)

    def test_a_push_into_someone_hits_both(self):
        state = make_state(hero_cell=1, enemies=[enemy(2), enemy(4)])
        after, _ = fire(state, self.TESSEN)
        self.assertEqual(sorted((e.cell, e.hp) for e in after.enemies), [(3, 1), (4, 2)])

    def test_a_heavy_enemy_is_hit_but_not_pushed(self):
        heavy = enemy(2)
        heavy.movable = False
        after, _ = fire(make_state(hero_cell=1, enemies=[heavy]), self.TESSEN)
        self.assertEqual((after.enemies[0].cell, after.enemies[0].hp), (2, 2))


class CloseCombatTest(unittest.TestCase):
    """CloseCombatSkill in the game's code: its level added to the hero's hits on an adjacent enemy, unmoved."""

    def test_an_adjacent_hit_gets_the_bonus(self):
        state = make_state(enemies=[enemy(3, hp=5)], queue=["Swirl"])
        state.close_bonus = 1
        after, outcome = step(state, Action("Attack"))
        self.assertEqual((after.enemies[0].hp, outcome.enemy_damage), (2, 3))

    def test_not_at_range(self):
        state = make_state(enemies=[enemy(4, hp=5)], queue=["Arrow"])
        state.close_bonus = 1
        after, _ = step(state, Action("Attack"))
        self.assertEqual(after.enemies[0].hp, 3)

    def test_not_on_a_move_attacks_own_hit(self):
        # A Charge runs the hero next to the enemy: its own hit moved the hero, so no bonus, but the Katana after it
        # begins from where the Charge left it, and gets one.
        state = make_state(hero_cell=0, enemies=[enemy(4, hp=9)])
        charge, katana = Tile(CHARGE, 3, 3, in_queue=True), Tile(KATANA, 3, 3, in_queue=True)
        state.tiles, state.queue_tiles, state.hero.queue = [charge, katana], [charge, katana], [CHARGE, KATANA]
        state.close_bonus = 1
        after, _ = step(state, Action("Attack"))
        self.assertEqual(after.enemies[0].hp, 9 - 1 - 3)

    def test_read_from_the_log(self):
        row = {"skills": [{"name": "CloseCombat", "level": 2}]}
        from rules import unmodeled_content
        self.assertNotIn("skill CloseCombat", unmodeled_content({"tiles": [], "hero": {"queue": []}, "enemies": [],
                                                                  "skills": row["skills"]}))


class BackStabberTest(unittest.TestCase):
    """BackStabberSkill in the game's code: its level added to a directional hit from behind the target."""

    def board(self, enemy_facing):
        state = make_state(enemies=[enemy(3, facing=enemy_facing, hp=5)], queue=["Swirl"])
        state.backstab_bonus = 1
        return state

    def test_from_behind_it_gets_the_bonus(self):
        # The enemy at 3 faces right, away from the hero at 2.
        after, _ = step(self.board(1), Action("Attack"))
        self.assertEqual(after.enemies[0].hp, 2)

    def test_not_from_the_front(self):
        after, _ = step(self.board(-1), Action("Attack"))
        self.assertEqual(after.enemies[0].hp, 3)

    def test_not_with_a_tile_that_isnt_directional(self):
        state = self.board(1)
        bolt = Attack("Lightning", 2, [1], first_target=True, directional=False)
        after, _ = fire(state, bolt)
        self.assertEqual(after.enemies[0].hp, 3)


class ComboTest(unittest.TestCase):
    """The kill streak (CombatManager.OnEnemyDied) and Triple Combo Heal (TripleComboHealSkill.UponComboKill)."""

    def triple(self, hero_hp=7):
        state = make_state(enemies=[enemy(1, facing=1, hp=1), enemy(3, hp=1)], queue=["Swirl", "Arrow"])
        state.enemies.append(enemy(4, hp=1))
        state.hero.hp = hero_hp
        state.triple_heal = True
        return state

    def test_the_third_kill_in_a_turn_heals_one(self):
        after, outcome = step(self.triple(), Action("Attack"))
        self.assertEqual((outcome.combo_kills, outcome.healed, after.hero.hp), (2, 1, 8))

    def test_no_heal_past_full_hp(self):
        after, outcome = step(self.triple(hero_hp=10), Action("Attack"))
        self.assertEqual((outcome.healed, after.hero.hp), (0, 10))

    def test_the_streak_starts_again_each_turn(self):
        state = self.triple()
        after, _ = step(state, Action("Wait"))
        self.assertEqual(after.kill_streak, 0)

    def test_a_heal_is_worth_what_a_lost_hp_costs(self):
        from evaluator import outcome_terms
        _, outcome = step(self.triple(), Action("Attack"))
        self.assertEqual(outcome_terms(outcome, False)["healed"], -WEIGHTS["hp_lost"])

    def test_random_combo_effects_are_valued(self):
        from evaluator import outcome_terms
        state = self.triple()
        state.enemies.append(enemy(6, hp=5))
        state.enemies.append(enemy(5, hp=5))
        state.chilling_combo = state.combo_curse = True
        _, outcome = step(state, Action("Attack"))
        # Two combo kills, each with enemies left to pick from: each effect counts its worst case, more than nothing.
        self.assertGreater(outcome_terms(outcome, False)["combos"], 0)

    def test_a_random_effect_counts_its_least_valuable_target(self):
        from evaluator import freeze_worth
        state = self.triple()
        state.enemies.append(enemy(6, hp=5))
        state.enemies.append(enemy(5, hp=2))
        state.chilling_combo = True
        _, outcome = step(state, Action("Attack"))
        # First combo kill: the 1 HP enemy, the 2 HP one and the 5 HP one could be frozen; the least is the 1 HP one.
        # Second: the 2 HP one and the 5 HP one; the least, the 2 HP one.
        least = freeze_worth(state, enemy(0, hp=1)) + freeze_worth(state, enemy(0, hp=2))
        self.assertAlmostEqual(outcome.combo_random, least)

    def test_one_possible_target_is_simulated(self):
        state = self.triple()
        state.enemies.append(enemy(6, hp=5))
        state.chilling_combo = state.combo_curse = True
        after, outcome = step(state, Action("Attack"))
        # The first combo kill leaves two to pick from, random; the second leaves one, which gets both.
        last = after.enemies[0]
        self.assertEqual((last.ice > 0, last.curse, outcome.combo_random > 0), (True, True, True))

    def test_combo_recharge_refills_the_tile_making_the_kill(self):
        state = self.triple()
        state.combo_recharge = 4
        after, _ = step(state, Action("Attack"))
        # Swirl (cooldown 3) killed two, the second a combo kill: 4 back, capped at 3. Arrow (cooldown 5) killed the
        # third: 4 back, one short of ready.
        self.assertEqual([t.charge for t in after.tiles], [3, 4])


class MonomancerTest(unittest.TestCase):
    """MonomancerSkill in the game's code: its level added to the hero's hits on an attack with one tile queued."""

    def test_a_single_tile_gets_the_bonus(self):
        state = make_state(enemies=[enemy(3, hp=5)], queue=["Swirl"])
        state.mono_bonus = 1
        after, _ = step(state, Action("Attack"))
        self.assertEqual(after.enemies[0].hp, 2)

    def test_two_tiles_dont(self):
        state = make_state(enemies=[enemy(3, hp=9)], queue=["Swirl", "Arrow"])
        state.mono_bonus = 1
        after, _ = step(state, Action("Attack"))
        self.assertEqual(after.enemies[0].hp, 9 - 2 - 2)

    def test_big_pockets_adds_a_slot_per_level(self):
        row = {"cells": 5, "hero": {"kind": "Wanderer", "cell": 0, "facing": "Right", "hp": 10, "maxHp": 10,
               "shield": False, "queue": [], "action": "Wait", "special": {"name": "SwapSpecialMove", "charge": 4,
               "cooldown": 4}}, "enemies": [], "tiles": [], "skills": [{"name": "BigPockets", "level": 2}]}
        self.assertEqual(state_from_log(row).potion_slots, 5)


def chain_master(hero_cell=3, facing=1, enemies=(), swap_charge=4):
    state = make_state(hero_cell=hero_cell, facing=facing, enemies=enemies, swap_charge=swap_charge)
    state.cells = 7
    state.hero.kind = "ChainMaster"
    state.special = "SwapTossSpecialMove"
    return state


class SwapTossSpecialMoveTest(unittest.TestCase):
    """SwapTossSpecialMove in the game's code: the agents on either side of the hero trade places, the hero staying."""

    def test_the_enemy_in_front_goes_behind_facing_away(self):
        after, _ = step(chain_master(enemies=[enemy(4)]), Action("MoveRight"))
        self.assertEqual((after.hero.cell, after.enemies[0].cell, after.enemies[0].facing, after.swap_charge),
                         (3, 2, -1, 0))

    def test_both_sides_trade_places(self):
        after, _ = step(chain_master(enemies=[enemy(4, hp=1), enemy(2, facing=1, hp=2)]), Action("MoveRight"))
        self.assertEqual(sorted((e.cell, e.hp) for e in after.enemies), [(2, 1), (4, 2)])

    def test_damaging_move_hits_each_one_moved(self):
        state = chain_master(enemies=[enemy(4), enemy(2, facing=1)])
        state.swap_damage = 1
        after, outcome = step(state, Action("MoveRight"))
        self.assertEqual(outcome.enemy_damage, 2)

    def test_needs_both_cells_beside_the_hero(self):
        self.assertFalse(can_use_special(chain_master(hero_cell=0, enemies=[enemy(1)]), 1))

    def test_a_heavy_one_on_either_side_stops_it(self):
        heavy = enemy(2, facing=1)
        heavy.movable = False
        self.assertFalse(can_use_special(chain_master(enemies=[enemy(4), heavy]), 1))
        self.assertTrue(can_use_special(chain_master(enemies=[enemy(4)]), 1))

    def test_only_the_way_the_hero_faces_without_two_way_move(self):
        state = chain_master(enemies=[enemy(2, facing=1)])
        self.assertFalse(can_use_special(state, -1))
        state.two_way_swap = True
        self.assertTrue(can_use_special(state, -1))

    def test_the_label_says_swap_toss(self):
        self.assertEqual(Action("MoveRight").label(chain_master(enemies=[enemy(4)])), "MoveRight (swap toss)")


class MeteorHammerTest(unittest.TestCase):
    """MeteorHammerAttack in the game's code: the first agent in range ahead, then, only if there was one, whoever is
    right behind the attacker."""
    HAMMER = Attack("MeteorHammer", 2, [1, 2, 3], first_target=True)

    def test_it_ricochets_onto_the_one_behind(self):
        after, outcome = fire(make_state(enemies=[enemy(4), enemy(1, facing=1)]), self.HAMMER)
        self.assertEqual(sorted((e.cell, e.hp) for e in after.enemies), [(1, 1), (4, 1)])
        self.assertEqual(outcome.enemy_damage, 4)

    def test_no_ricochet_with_nobody_in_front(self):
        after, outcome = fire(make_state(enemies=[enemy(1, facing=1)]), self.HAMMER)
        self.assertEqual((after.enemies[0].hp, outcome.wasted_attacks), (3, 1))

    def test_only_the_first_ahead(self):
        after, _ = fire(make_state(enemies=[enemy(3), enemy(4)]), self.HAMMER)
        self.assertEqual(sorted(e.hp for e in after.enemies), [1, 3])


class HookbladeTest(unittest.TestCase):
    """HookbladeAttack in the game's code: on each kill the attacker steps into the cell and strikes again for 1 less,
    while someone is in front."""
    HOOK = Attack("Hookblade", 2, [1], first_target=True)

    def test_a_kill_steps_in_and_strikes_the_next_for_less(self):
        state = make_state(hero_cell=1, enemies=[enemy(2, hp=2), enemy(3, hp=3)])
        after, outcome = fire(state, self.HOOK)
        self.assertEqual((after.hero.cell, [e.hp for e in after.enemies if e.alive]), (2, [2]))
        self.assertEqual(outcome.kills, 1)

    def test_it_chains_while_each_hit_kills(self):
        state = make_state(hero_cell=0, enemies=[enemy(1, hp=2), enemy(2, hp=1), enemy(3, hp=3)])
        after, _ = fire(state, self.HOOK)
        # 2 kills the first, 1 the second, and the third takes 0.
        self.assertEqual((after.hero.cell, [e.hp for e in after.enemies if e.alive]), (2, [3]))

    def test_no_kill_no_step(self):
        after, _ = fire(make_state(hero_cell=1, enemies=[enemy(2, hp=3)]), self.HOOK)
        self.assertEqual((after.hero.cell, after.enemies[0].hp), (1, 1))

    def test_a_kill_with_nobody_next_still_steps_in(self):
        after, _ = fire(make_state(hero_cell=1, enemies=[enemy(2, hp=2), enemy(4)]), self.HOOK)
        self.assertEqual(after.hero.cell, 2)

    def test_the_tile_keeps_its_value(self):
        state = make_state(hero_cell=0, enemies=[enemy(1, hp=2), enemy(2, hp=3)])
        after, _ = fire(state, self.HOOK)
        self.assertEqual(after.tiles[-1].attack.value, 2)


class ChikaraCrushTest(unittest.TestCase):
    """ChikaraCrushSkill in the game's code: its level added to every push collision an enemy takes."""

    def test_both_in_a_collision_take_more(self):
        state = make_state(hero_cell=1, enemies=[enemy(2, hp=5), enemy(4, hp=5)])
        state.chikara_bonus = 1
        after, _ = fire(state, PUNCH)
        # The punch's 1, then 2 each for the collision.
        self.assertEqual(sorted(e.hp for e in after.enemies), [2, 3])

    def test_not_on_a_hit_or_a_trap(self):
        state = make_state(enemies=[enemy(3, hp=5)], queue=["Swirl"])
        state.chikara_bonus = 2
        after, _ = step(state, Action("Attack"))
        self.assertEqual(after.enemies[0].hp, 3)

    def test_read_from_the_log(self):
        row = {"cells": 5, "tiles": [], "enemies": [], "skills": [{"name": "ChikaraCrush", "level": 2}],
               "hero": {"kind": "H", "cell": 0, "facing": "Right", "hp": 9, "maxHp": 9, "shield": False, "queue": [],
                        "action": "Wait", "special": {"charge": 3, "cooldown": 3}}}
        self.assertEqual(state_from_log(row).chikara_bonus, 2)
        self.assertNotIn("skill ChikaraCrush", unmodeled_content(row))


class HookbladePerfectStrikeTest(unittest.TestCase):
    """CombatManager.OnPreciseKill: any exact kill while a Perfect Strike tile is in progress recharges it, so a hit
    anywhere along the Hookblade's chain counts."""

    def charge_after(self, *hps):
        hook = Attack("Hookblade", 2, [1], first_target=True, effect="PerfectStrike")
        state = make_state(hero_cell=0, enemies=[enemy(i + 1, hp=hp) for i, hp in enumerate(hps)])
        after, _ = fire(state, hook, cooldown=5)
        return next(t for t in after.tiles if t.attack.name == "Hookblade").charge

    def test_an_exact_kill_later_in_the_chain_counts(self):
        # 2 overkills the first, then 1 kills the second exactly.
        self.assertEqual(self.charge_after(1, 1), 5)

    def test_overkills_alone_dont(self):
        self.assertEqual(self.charge_after(1, 3), 0)


if __name__ == "__main__":
    unittest.main()
