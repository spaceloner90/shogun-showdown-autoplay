"""Lookahead for F2 and deeper: the hero's next few turns played out with the real enemy AI.

Each turn is the hero's action, then the enemies' telegraphed actions, simulated by rules.step, and at its end each
enemy chooses its next telegraph through enemy_ai.py. A line scores what happens on every turn (damage, kills, HP
lost, as F1's events) plus the position it ends in (F1's position score, stack included, and the threat no answer
removes). A turn whose enemy actions are all known counts in full; a turn with any unknown (an enemy the AI can't
predict, an unidentified tile, a wave about to arrive) counts at F1's future discount, from there on.

To stay fast: all of this turn's actions are searched, but deeper turns only follow the BEAM best by a cheap score
(the turn's events plus the position without its stack), the full position score is only taken at the end of a
line, and a board reached twice by different orders is only searched once.
"""
from __future__ import annotations

import time

from evaluator import (WEIGHTS, Line, _cheapest_hit, _kept_terms, fight_won, leaf_terms, outcome_terms,
                       unanswerable_damage)
from rules import SIMULATED_POTIONS, UNKNOWN_COPY, UNKNOWN_TILE, apply_potion, legal_actions, step

# What a turn counts for when something in it isn't known. A wave about to arrive keeps F1's future discount: new
# enemies do nothing the turn they come in and don't change what's already there. An enemy whose action is only
# guessed counts much less, so damage certain now beats damage later that relies on it, as the player asked.
UNKNOWN_ACTION = 0.5
# Only for ties: of two lines that score the same, the one whose events come sooner wins, its events counted this
# much less for each turn later. Known turns aren't discounted in the score itself, so without this a kill could be
# put off forever at no cost, and was (logs/run14 turn 20; a lone Twin Tachi in the simulator, never attacked).
SOONER = 0.9
BEAM = 4
LEAF_BEAM = 2  # On the last turn, only this many of the BEAM get the full position score.


def _actions_known(state):
    return all(e.known and not any(a.name in (UNKNOWN_TILE, UNKNOWN_COPY) for a in e.queue)
               for e in state.enemies if e.alive)


def _wave_coming(state):
    return state.turns_until_wave is not None and not state.last_wave and state.turns_until_wave <= 1


def certain(state):
    """Whether the coming turn is fully known: every enemy's telegraph and tiles, and no wave about to arrive."""
    return _actions_known(state) and not _wave_coming(state)


def _factor(state):
    """A turn whose enemy actions are guessed counts for less, and so does one with a wave about to arrive among
    enemies still there, as the player set: who comes isn't simulated. A wave into a cleared room ends the line."""
    if not _actions_known(state):
        return UNKNOWN_ACTION
    return WEIGHTS["future_discount"] if _wave_coming(state) else 1.0


def state_key(state):
    """Everything about a board that the rest of a line depends on, so two orders reaching it search it once."""
    hero = state.hero
    index = {id(t): i for i, t in enumerate(state.tiles)}
    return (
        hero.cell, hero.facing, hero.hp, hero.shield, hero.curse, hero.poison, hero.ice,
        tuple((t.attack.name, t.attack.value, t.charge, t.in_queue, t.just_played) for t in state.tiles),
        tuple(index[id(t)] for t in state.queue_tiles),
        state.swap_charge, state.turns_until_wave, state.wave_held_at, tuple(state.potions),
        tuple(state.lit_cells) if state.lit_cells is not None else None, state.nobunaga_hp_last_turn,
        repr(state.traps), repr(state.hazards),
        tuple((e.kind, e.cell, e.facing, e.hp, e.max_hp, e.shield, e.curse, e.poison, e.ice, e.action, e.known,
               e.tile_to_play, e.last_tile, e.elite, tuple((a.name, a.value, a.target_cell) for a in e.queue))
              for e in state.enemies),
    )


def _turn(state, action, now=False):
    """One turn: the next board, what it scored, and whether the line ends there or wastes a tile. As in F1, ending
    the fight at no HP cost beats anything only on the turn being chosen (`now`): a win later in a line counts for
    its kills, or every line ending in one would tie, and the search would keep putting it off.

    A line also ends where the next wave arrives in a cleared room, scored by the board it lands on: who comes isn't
    simulated, so playing on scored an empty board, where a tile spent would be back before the end of the line and
    look free. A wave landing among enemies still there doesn't end it: what they do next is known, and ending there
    hid their next attacks (v3.6 lost HP that way in the fight simulation)."""
    following, outcome = step(state, action)
    dead = not following.hero.alive
    score = sum(outcome_terms(outcome, dead, _cheapest_hit(state), state.combo_skills).values())
    won = not dead and fight_won(following)
    if now and won and outcome.hp_lost == 0:
        score += WEIGHTS["win"]
    wasted = action.kind == "Attack" and outcome.wasted_attacks > 0
    cleared = following.wave_landed and not any(e.alive for e in following.enemies)
    return following, score, dead or won or cleared, wasted


def _leaf(state):
    if not state.hero.alive:
        return 0.0
    return sum(leaf_terms(state).values()) + WEIGHTS["no_response"] * unanswerable_damage(state)


def _cheap(state):
    return sum(_kept_terms(state).values()) if state.hero.alive else 0.0


class OutOfTime(Exception):
    pass


class Search:
    def __init__(self, beam=BEAM, leaf_beam=LEAF_BEAM, deadline=None):
        self.beam = beam
        self.leaf_beam = leaf_beam
        self.deadline = deadline  # A time.time() after which the search gives up, so a worker frees up at once.
        self.memo = {}
        self.leaves = {}
        self.nodes = 0

    def leaf(self, state):
        key = state_key(state)
        if key not in self.leaves:
            self.leaves[key] = _leaf(state)
        return self.leaves[key]

    def value(self, state, depth):
        """The best this board can score over `depth` more turns, how soon its events come (for ties), and the line
        that does it, as (action, label)."""
        if depth == 0:
            return self.leaf(state), 0.0, []
        key = (state_key(state), depth)
        if key in self.memo:
            return self.memo[key]
        if self.deadline is not None and time.time() > self.deadline:
            raise OutOfTime
        children = []
        for action in legal_actions(state):
            following, score, final, wasted = _turn(state, action)
            self.nodes += 1
            if wasted:
                continue
            factor = _factor(following)
            children.append((score + factor * _cheap(following), action, following, score, final, factor))
        children.sort(key=lambda c: c[0], reverse=True)
        best = (float("-inf"), 0.0, [])
        for _, action, following, score, final, factor in children[:self.beam if depth > 1 else self.leaf_beam]:
            if final:
                total, sooner, rest = score + factor * self.leaf(following), score, []
            else:
                later, later_sooner, rest = self.value(following, depth - 1)
                total, sooner = score + factor * later, score + SOONER * later_sooner
            if (round(total, 6), sooner) > (round(best[0], 6), best[1]):
                best = (total, sooner, [(action, action.label(state))] + rest)
        if best[0] == float("-inf"):
            best = (self.leaf(state), 0.0, [])
        self.memo[key] = best
        return best


def line_for(state, action, depth, search):
    """The best line over `depth` turns starting with `action`."""
    following, score, final, wasted = _turn(state, action, now=True)
    factor = _factor(following)
    if final or depth == 1:
        later, later_sooner, rest = search.leaf(following), 0.0, []
    else:
        later, later_sooner, rest = search.value(following, depth - 1)
    # Ties go to the line whose events come sooner, not to the position left after this turn, as F1 does: that kept
    # tiles loaded and put a kill off turn after turn. Only lines equal in that too go by that position: otherwise
    # Wait, listed first, won them, with a tile left to load later in the line (logs/run17).
    return Line([action] + [a for a, _ in rest], score + factor * later,
                [action.label(state)] + [label for _, label in rest],
                {"this turn": score, "after": factor * later}, score + SOONER * later_sooner, wasted,
                _leaf(following))


def _sorted(lines, state=None):
    lines = [line for line in lines if not line.wasted]
    lines.sort(key=lambda line: line.sort_key, reverse=True)
    return _keep_the_guarantee(state, lines) if state is not None else lines


def _clears_room(state, action):
    """Whether this action now kills the last enemy with a wave still to come, which brings it at once, at no HP
    cost: the player's condition for weighing whether to put it off is that the wave can be finished without losing
    life. Clearing it at a cost is no reason to hold back the lines that don't."""
    following, outcome = step(state, action)
    return following.wave_landed and not any(e.alive for e in following.enemies) and outcome.hp_lost == 0


def _guaranteed_delay(state, line):
    """Whether a line holding off the kill that clears the room is sure to be safe until its wave lands: every turn
    until then fully known, no HP lost, the wave's arrival exact (not held back by a crowded room, whose next wave's
    size the log doesn't give), and the landing within the line."""
    for action in line.actions:
        if not _actions_known(state) or state.wave_held_at is not None:
            return False
        state, outcome = step(state, action)
        if outcome.hp_lost or not state.hero.alive:
            return False
        if state.wave_landed:
            return True
    return False


def _keep_the_guarantee(state, lines):
    """When a move now clears the room, the search may still put the kill off to meet the wave better set up, as the
    player asked, but only along a line guaranteed safe until the wave lands (`_guaranteed_delay`). Any other line
    goes below every line that clears the room now, keeping its order."""
    clears = {id(line): _clears_room(state, line.actions[0]) for line in lines}
    if not any(clears.values()):
        return lines
    allowed = [line for line in lines if clears[id(line)] or _guaranteed_delay(state, line)]
    kept = {id(line) for line in allowed}
    return allowed + [line for line in lines if id(line) not in kept]


def rank_lines(state, depth, beam=BEAM, leaf_beam=LEAF_BEAM, deadline=None):
    """Every action available now, best first, each with the best line after it over `depth` turns in all. None if
    a `deadline` (a time.time()) passes first."""
    search = Search(beam, leaf_beam, deadline)
    try:
        return _sorted([line_for(state, action, depth, search) for action in legal_actions(state)], state)
    except OutOfTime:
        return None


def _line_task(job):
    state, action, depth, beam, leaf_beam, deadline = job
    try:
        return line_for(state, action, depth, Search(beam, leaf_beam, deadline))
    except OutOfTime:
        return None


def _f1_task(job):
    """F1's own score for one action: the live evaluator at depth 1, exactly as rank_actions scores it."""
    from evaluator import _evaluate_action
    state, action = job
    return _evaluate_action(state, action, 1, 1.0)


def _distinct(state, actions):
    """Groups this turn's actions by what they lead to: the same board after the turn, with the same events, scores
    the same at every depth, so only one of each group needs searching. Different orders of the same attack often
    do. Returns {representative action: [the actions it stands for]}."""
    groups = {}
    for action in actions:
        following, score, final, wasted = _turn(state, action, now=True)
        key = (state_key(following), round(score, 6), final, wasted)
        groups.setdefault(key, []).append(action)
    return {members[0]: members for members in groups.values()}


def _as(line, state, action):
    """A line found for one action of a group, given to another of that group."""
    return Line([action] + line.actions[1:], line.score, [action.label(state)] + line.labels[1:], line.terms,
                line.position_next_turn, line.wasted, line.position_after)


def submit_lines(state, depths, pool, beam=BEAM, leaf_beam=LEAF_BEAM, deadlines=None):
    """Starts every depth's search at once, one job per distinct action now and depth, F1 included, and returns a
    function that waits for them and gives {depth: ranked lines}. A depth with a deadline in `deadlines` (a
    time.time()) is left out of the result if any of its jobs runs past it."""
    deadlines = deadlines or {}
    groups = _distinct(state, legal_actions(state))
    futures = {depth: {action: pool.submit(_f1_task, (state, action)) if depth == 1 else
                       pool.submit(_line_task, (state, action, depth, beam, leaf_beam, deadlines.get(depth)))
                       for action in groups}
               for depth in depths}

    def collect():
        found = {}
        for depth, jobs in futures.items():
            lines = {action: f.result() for action, f in jobs.items()}
            if all(line is not None for line in lines.values()):
                found[depth] = _sorted([_as(lines[rep], state, a) for rep, members in groups.items() for a in members],
                                       state if depth > 1 else None)
        return found
    return collect


def rank_lines_parallel(state, depth, pool, beam=BEAM, leaf_beam=LEAF_BEAM):
    """rank_lines with each of this turn's actions searched by its own worker from `pool`. Boards reached under two
    different first actions get searched twice, the price of not sharing memory between workers."""
    jobs = [(state, action, depth, beam, leaf_beam, None) for action in legal_actions(state)]
    return _sorted(list(pool.map(_line_task, jobs)), state)


# What a potion is for, in the order preferred among those that save as much HP over the line (the player's call):
# the combat potions first, keeping the sure ones, Shield and Freeze Time, for when nothing else does it.
POTION_PREFERENCE = ("CoolUp", "MassPoison", "MassCurse", "RainOfMirrors", "Shield", "MassIce")
# Potions that answer attacks already telegraphed: turning everyone round, a shield, a freeze. Each is for damage
# coming this turn, as the player set: one drunk for a hit turns ahead does nothing a later one couldn't. The others
# hurt or recharge, which can head off a hit turns ahead, so they're judged on the whole line.
IMMEDIATE_POTIONS = {"RainOfMirrors", "Shield", "MassIce"}


def line_totals(state, line, turns=None):
    """HP the hero loses and kills made along a line, played out turn by turn: its first `turns`, or all of it."""
    lost = kills = 0
    for action in line.actions[:turns]:
        state, outcome = step(state, action)
        lost += outcome.hp_lost
        kills += outcome.kills
        if not state.hero.alive:
            break
    return lost, kills


def _least_lost(state, lines, turns=None):
    """The least HP lost over any of the ranked lines: what the hero can keep without help, whichever it chooses."""
    return min(line_totals(state, line, turns)[0] for line in lines)


def potion_choice(state, lines, after_potion, depth):
    """Which potion to use before acting, judged on the best line over `depth` turns with and without it.

    `lines` ranks this board at that depth; `after_potion` maps each potion to the ranked lines after drinking it.
    Edamame heals once missing at least what it heals, or 6 with Triple Combo Heal, which heals well on its own. Any
    potion that cuts the least HP the hero can lose is used, the one saving most, combat potions first on a tie,
    since a hit seen coming turns ahead can often be headed off by them; the immediate ones (IMMEDIATE_POTIONS) only
    for damage this turn; in the fight before the Shogun's, Freeze Time first, since it's useless against him. Never for kills alone, even with the bag full, as the player asked: a
    potion left on the ground pays a coin, and every potion is kept for heading off damage. D6, being random, is only the last resort against damage this turn that nothing else avoids. Returns
    (potion, reason) or (None, None).
    """
    from evaluator import WEIGHTS
    held = state.potions
    if not held:
        return None, None
    hero = state.hero
    heal_at = WEIGHTS["heal_at_missing_combo"] if state.triple_heal else WEIGHTS["heal_at_missing"]
    if "Edamame" in held and hero.max_hp - hero.hp >= heal_at:
        return "Edamame", f"heal: HP {hero.hp}/{hero.max_hp}"
    # Each potion against the least HP any line loses without it, not the best line's: that one may take a hit for a
    # kill, which a potion shouldn't pay for. Over the whole line, or this turn alone for the immediate ones.
    saves = []
    for name, again in after_potion.items():
        if not again:
            continue
        turns = 1 if name in IMMEDIATE_POTIONS else None
        lost = _least_lost(state, lines, turns)
        their_lost = _least_lost(apply_potion(state, name), again, turns)
        # In the fight before the Shogun's, Freeze Time comes first: it's no use against him (the player's call).
        order = (("MassIce",) + tuple(p for p in POTION_PREFERENCE if p != "MassIce")) if state.before_final             else POTION_PREFERENCE
        rank = order.index(name) if name in order else len(order)
        if their_lost < lost:
            saves.append((their_lost - lost, rank, name, lost, their_lost, turns))
    if saves:
        _, _, name, lost, their_lost, turns = min(saves)
        span = "this turn" if turns == 1 else f"over {depth} turns"
        return name, f"{span}, {lost} HP lost at best without it, {their_lost} with it"
    # No potion only for kills with the bag full any more, as the player asked: one left on the ground pays a coin,
    # and every potion is kept for heading off damage.
    now = step(state, lines[0].actions[0])[1]
    if now.hp_lost > 0 and "D6" in held:
        return "D6", f"losing {now.hp_lost} HP this turn that nothing else avoids"
    return None, None
