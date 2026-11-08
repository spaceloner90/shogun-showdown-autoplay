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
    for name in ("run2_complete", "run3_v03", "run3_part2", "run4", "run5_full", "run6", "run7", "run8")
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


def at_seq(seq, log):
    """The logged state with this sequence number."""
    return state_from_log(next(r for r in ROWS[log] if r.get("seq") == seq))


class QueueEdits(unittest.TestCase):
    def test_loads_with_a_swap_to_break_a_stalemate(self):
        # Run 8, fight 11: the queue full with Swirl, Shadow Kama and Arrow, and F1 waited every turn since it couldn't
        # load anything. Sending Swirl back to load Shadow Dash sets up killing both.
        best = rank_actions(at_seq(4651, "run8"), depth=1)[0]
        self.assertEqual(best.labels[0], "PlayTile ShadowDash (Swirl to hand)")

    def test_never_fires_shadow_kama_at_nothing(self):
        # Run 8, fight 14: Shadow Kama loaded with nobody 2 cells ahead. It used to fire anyway, as that took it out of
        # where the hero wants to stand. It goes back to hand instead.
        for seq in (5818, 3570, 1269):
            for line in rank_actions(at_seq(seq, "run8"), depth=1):
                self.assertFalse(line.wasted, line.labels[0])
            best = rank_actions(at_seq(seq, "run8"), depth=1)[0]
            self.assertIn("ShadowKama to hand", best.labels[0])


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


class GrapplerAsPlayed(unittest.TestCase):
    """The 15-wave fight, where a shield took the hook, the pull still happened, and the Katana landed."""

    def test_simulates_the_hook_and_katana_as_they_happened(self):
        rows = ROWS["run3_part2"]
        hook_row = next(i for i, r in enumerate(rows) if r.get("event") == "attack" and "GrapplingHook" in r["text"])
        fight = sum(r.get("event") == "combat_start" for r in rows[:hook_row]) - 1
        after, outcome = step(position(fight, rows[hook_row]["turn"], "run3_part2"), Action("MoveRight"))
        self.assertEqual((after.hero.cell, after.hero.shield, after.hero.hp, outcome.hp_lost), (3, False, 7, 2))


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
    # Since v1.27, a sure kill now against a likely bigger volley next turn is a near tie: 105.9 to kill the Archer now,
    # 105.7 to line up both. The player chose to deploy it and see, rather than tune the weights behind it.
    @unittest.expectedFailure
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


class SniperAsPlayed(unittest.TestCase):
    """Run 4, the first with Snipers. v0.11 stayed on the locked cell and took every one of these."""

    def test_steps_off_instead_of_taking_the_shot(self):
        for fight, turn in ((4, 22), (4, 37), (6, 16), (7, 19)):
            self.assertEqual(choice(fight, turn, "run4").terms.get("hp_lost", 0), 0, (fight, turn))

    def test_can_take_the_shot_to_clear_two_enemies_at_once(self):
        # Fight 7, turn 15: firing kills the Archer and Ashigaru. Dodging leaves both, and the Archer's shot.
        best = choice(7, 15, "run4")
        self.assertEqual(best.actions[0].kind, "Attack")
        self.assertEqual(best.terms.get("kills", 0) / 60, 2)

    def test_stepping_off_dodged_it_as_played(self):
        # Turn 5 of fight 4: the hero moved right off cell 3, and the game showed no hit.
        _, outcome = step(position(4, 5, "run4"), Action("MoveRight"))
        self.assertEqual(outcome.hp_lost, 0)

    def test_the_shot_passes_over_the_ashigaru_in_between(self):
        # Turn 15 of fight 7: the shot hit the hero behind the Ashigaru, and left the Ashigaru alone.
        state = position(7, 15, "run4")
        after, outcome = step(state, Action("Wait"))
        self.assertEqual(outcome.hp_lost, 2)
        self.assertEqual(next(e.hp for e in after.enemies if e.kind == "Ashigaru"), 3)


class WinningRun(unittest.TestCase):
    """The run that confirmed v1, with the log's own fight numbers. These replay what the game did."""

    def test_the_bomb_as_played(self):
        # Fight 28: Hideyoshi threw it on turn 21 and it hit the hero, who stayed on cell 6, on turn 23.
        state = position(28, 21, "run5_full")
        state, thrown = step(state, Action("Wait"))
        self.assertEqual(thrown.hp_lost, 0)
        for enemy in state.enemies:
            enemy.queue, enemy.action = [], "Wait"
        state, waited = step(state, Action("Wait"))
        state, blast = step(state, Action("Wait"))
        self.assertEqual((waited.hp_lost, blast.hp_lost), (0, 3))

    def test_leaves_the_blast_given_the_warning(self):
        # Turn 22 of that fight, with what the mod now logs. The hero has to start moving this turn.
        state = position(28, 22, "run5_full")
        state.hazards = [{"damage": 3, "groups": [[], [5, 6]], "heals_boss": False}]
        self.assertEqual(rank_actions(state, depth=1)[0].labels[0], "MoveLeft")

    def test_poison_as_played(self):
        # Final boss, turn 11: 26 HP with 2 turns left. It lost 1 and had 1 left on turn 12.
        state = position(30, 11, "run5_full")
        boss = next(e for e in state.enemies if e.kind == "ShogunPhase1Boss")
        self.assertEqual((boss.hp, boss.poison), (26, 2))
        after, _ = step(state, Action("Wait"))
        boss = next(e for e in after.enemies if e.kind == "ShogunPhase1Boss")
        self.assertEqual((boss.hp, boss.poison), (25, 1))

    def test_still_makes_the_dragon_punch_play(self):
        # Final boss, turn 8: shoves the boss into the Yari Master, then Arrow lands.
        best = choice(30, 8, "run5_full")
        self.assertEqual(best.actions[0].kind, "Attack")
        self.assertEqual(best.terms.get("hp_lost", 0), 0)


class RoninAsPlayed(unittest.TestCase):
    """The first Ronin run, on v1.2, which spent Smoke Bomb for 1 damage with nothing left to dodge with."""

    def fires_smoke(self, fight, turn):
        state = position(fight, turn, "run6")
        action = rank_actions(state, depth=1)[0].actions[0]
        if action.kind != "Attack":
            return False
        fired = state.queue_tiles if action.order is None else [state.tiles[i] for i in action.order]
        return any(t.attack.name == "SmokeBomb" for t in fired)

    def test_keeps_it_rather_than_jump_in_for_1_damage(self):
        self.assertFalse(self.fires_smoke(1, 14))
        self.assertFalse(self.fires_smoke(3, 6))
        self.assertFalse(self.fires_smoke(3, 24))

    def test_still_takes_the_boss_kill(self):
        # Fight 3, turn 36: Smoke Bomb, then the hook, then Spear finishes Rei and ends the fight. From v1.27 to v2.0
        # it stepped away instead, since nothing valued winning. The TwinTachi dying with him counts as a kill too.
        best = choice(3, 36, "run6")
        self.assertEqual((best.terms.get("kills", 0), "win" in best.terms), (120, True))

    def test_still_fires_it_to_get_out_of_a_hit(self):
        # Fight 2, turn 10: pinned at the wall with a Katana coming.
        self.assertEqual(choice(2, 10, "run6").terms.get("hp_lost", 0), 0)

    def test_a_held_bomb_would_have_dodged_rei(self):
        # Fight 3, turn 28: the hero took 2 from Charge and Dragon Punch with the bomb on cooldown.
        rows = ROWS["run6"]
        start = [i for i, r in enumerate(rows) if r.get("event") == "combat_start"][3]
        row = json.loads(json.dumps(next(r for r in rows[start:] if r["type"] == "state" and r["turn"] == 28)))
        for tile in row["tiles"]:
            if tile["attack"]["name"] == "SmokeBomb":
                tile.update(where="HeroAttackQueue", charged=True, turnsBeforeCharged=0)
                row["hero"]["queue"] = [tile["attack"]]
        best = rank_actions(state_from_log(row), depth=1)[0]
        self.assertEqual(best.terms.get("hp_lost", 0), 0)

    def test_the_hook_pulls_as_played(self):
        # Fight 2, turn 45: the hook pulled the Ashigaru next to the hero, as predicted.
        after, _ = step(position(2, 45, "run6"), Action("Attack"))
        self.assertTrue(any(abs(e.cell - after.hero.cell) == 1 for e in after.enemies))


class RoninWithLightning(unittest.TestCase):
    """The second Ronin run, on v1.5 and v1.6: three fights with no HP lost, the last against Baru."""

    def test_lightning_strikes_past_the_closer_enemy(self):
        # Fight 1, turn 23: Lightning killed the TwinTachi on cell 4, and Spear the Ashigaru on cell 2.
        after, outcome = step(position(1, 23, "run7"), Action("Attack"))
        self.assertEqual((after.enemies, outcome.kills), ([], 2))

    def test_lightning_strikes_past_the_barricade(self):
        # Fight 2, turn 21: Spear and its Shockwave left Baru on 6, and Lightning finished at 4, as played.
        after, _ = step(position(2, 21, "run7"), Action("Attack"))
        self.assertEqual([(e.kind, e.hp) for e in after.enemies if e.kind == "BaruBoss"], [("BaruBoss", 4)])

    def test_two_shockwaves_from_one_spear(self):
        # Fight 4, turn 8: Spear hit the Guardian on 2 and the Yari Master on 1. Each set off its own chain, so the
        # Guardian on 0 took 1 from each, and the first chain's 1 let the Spear's 3 kill the 4 HP Yari Master.
        best = choice(4, 8, "run7")
        after, _ = step(position(4, 8, "run7"), best.actions[0])
        self.assertEqual(([(e.cell, e.hp) for e in after.enemies], best.terms.get("kills", 0)), ([(0, 3)], 120))

    def test_doesnt_fire_the_hook_when_lightning_alone_kills(self):
        # Fight 5, turn 4: v1.7 fired the hook and Lightning at a 2 HP Archer, putting the hook on cooldown for
        # nothing, since sending a tile back cost more than firing it.
        self.assertEqual(choice(5, 4, "run7").labels[0], "Attack Lightning (Spear, GrapplingHook to hand)")

    def test_still_puts_baru_in_front_of_the_ashigaru(self):
        # Fight 2, turn 24: Smoke Bomb and the hook moved Baru into the Ashigaru's attack, which killed him.
        best = choice(2, 24, "run7")
        # Baru's death takes the Ashigaru with him, which counts as a kill too since v2.1.
        self.assertEqual((best.terms.get("kills", 0), best.terms.get("hp_lost", 0)), (120, 0))


def final_boss_rows():
    """The first state of each turn of the final boss in the winning run."""
    rows = ROWS["run3_part2"]
    starts = [i for i, r in enumerate(rows) if r.get("event") == "combat_start"]
    start = next(i for i in reversed(starts) if rows[i + 1:] and any(
        r["type"] == "state" and r["room"] == "ShogunBossRoom" for r in rows[i:i + 5]))
    first = {}
    for row in rows[start:]:
        if row["type"] == "state" and row["enemies"]:
            first.setdefault(row["turn"], row)
    return first


class FinalBoss(unittest.TestCase):
    def test_steps_off_the_cell_the_ring_is_about_to_reach(self):
        # Turn 39: fired from cell 3 on turn 37, the ring reached the hero on cell 0 for 3 damage.
        state = state_from_log(final_boss_rows()[39])
        state.hazards = [{"damage": 3, "groups": [[0, 6]]}]
        self.assertEqual(rank_actions(state, depth=1)[0].terms.get("hp_lost", 0), 0)

    def test_the_boss_comes_first_when_it_can_be_hit(self):
        # In the first phase, whenever an attack reaches both, the line chosen shouldn't favour a statue.
        for turn, row in final_boss_rows().items():
            if not any(e["kind"] == "ShogunPhase1Boss" for e in row["enemies"]):
                continue
            best = rank_actions(state_from_log(row), depth=1)[0]
            if best.terms.get("tank_damage", 0) > 0:
                self.assertGreater(best.terms.get("enemy_damage", 0) + best.terms.get("shields_broken", 0), 0, turn)


if __name__ == "__main__":
    unittest.main()
