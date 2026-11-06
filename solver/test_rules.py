"""Tests for rules the fight logs haven't exercised yet, such as Swap and flipping.

Run with: python solver/test_rules.py
"""
import unittest

from evaluator import _threat_damage, leaf_terms, rank_actions, unanswerable_damage
from rules import Action, Agent, Attack, State, Tile, legal_actions, step, unmodeled_content

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

    def test_a_curse_is_worthless_when_the_best_ready_tile_already_kills(self):
        # Swirl kills this 3hp enemy anyway, so helping Arrow do it too adds nothing.
        state = make_state(enemies=[enemy(3, hp=3)])
        state.enemies[0].curse = True
        state.tiles[0].attack = Attack("Swirl", 3, [-1, 1])
        self.assertEqual(leaf_terms(state)["curse"], 0)

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

    def test_a_loaded_stack_counts_the_curse_only_once(self):
        state = make_state(enemies=[enemy(3, hp=9)], queue=["Swirl"])
        state.enemies[0].curse = True
        terms = leaf_terms(state)
        self.assertEqual(terms["curse"], 0)
        plain = make_state(enemies=[enemy(3, hp=9)], queue=["Swirl"])
        self.assertGreater(terms["stack"], leaf_terms(plain)["stack"])

    def test_fires_the_curse_first_when_stacked(self):
        state = self._with_curse_arrow([enemy(3, hp=9)], queue=("Swirl", "Arrow"))
        best = rank_actions(state, depth=1)[0]
        self.assertEqual(best.actions[0], Action("Attack", order=(1, 0)))

    def test_understood_skills_get_no_warning_and_others_do(self):
        row = {"tiles": [], "hero": {"queue": []}, "enemies": [],
               "skills": [{"name": "Fortress", "level": 1}, {"name": "BigPockets", "level": 1}, {"name": "Sniper", "level": 1}]}
        self.assertEqual(unmodeled_content(row), ["skill Sniper"])

    def test_curse_gets_no_warning(self):
        row = {"tiles": [{"attack": {"name": "Arrow", "effect": "Curse", "tileEffect": "None"}}],
               "hero": {"queue": [], "curse": True}, "enemies": [], "skills": []}
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
        # With a queued Arrow and an enemy only behind, flipping beats firing into empty cells.
        state = make_state(enemies=[enemy(0, facing=1, hp=2)], queue=["Arrow"])
        ranked = [line.actions[0].kind for line in rank_actions(state, depth=2)]
        self.assertLess(ranked.index("Flip"), ranked.index("Attack"))

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
        armed = make_state(hero_cell=0, enemies=[enemy(4)])
        unarmed = make_state(hero_cell=0, enemies=[enemy(4)])
        for tile in unarmed.tiles:
            tile.charge = 0
        self.assertLess(leaf_terms(armed)["distance"], leaf_terms(unarmed)["distance"])

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
