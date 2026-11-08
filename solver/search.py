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
from rules import UNKNOWN_COPY, UNKNOWN_TILE, legal_actions, step

# What a turn counts for when something in it isn't known. A wave about to arrive keeps F1's future discount: new
# enemies do nothing the turn they come in and don't change what's already there. An enemy whose action is only
# guessed counts much less, so damage certain now beats damage later that relies on it, as the player asked.
UNKNOWN_ACTION = 0.5
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
        state.swap_charge, state.turns_until_wave, tuple(state.potions),
        tuple(state.lit_cells) if state.lit_cells is not None else None, state.nobunaga_hp_last_turn,
        repr(state.traps), repr(state.hazards),
        tuple((e.kind, e.cell, e.facing, e.hp, e.max_hp, e.shield, e.curse, e.poison, e.ice, e.action, e.known,
               e.tile_to_play, e.last_tile, e.elite, tuple((a.name, a.value, a.target_cell) for a in e.queue))
              for e in state.enemies),
    )


def _turn(state, action, now=False):
    """One turn: the next board, what it scored, and whether the line ends there or wastes a tile. As in F1, ending
    the fight at no HP cost beats anything only on the turn being chosen (`now`): a win later in a line counts for
    its kills, or every line ending in one would tie, and the search would keep putting it off."""
    following, outcome = step(state, action)
    dead = not following.hero.alive
    score = sum(outcome_terms(outcome, dead, _cheapest_hit(state)).values())
    won = not dead and fight_won(following)
    if now and won and outcome.hp_lost == 0:
        score += WEIGHTS["win"]
    wasted = action.kind == "Attack" and outcome.wasted_attacks > 0
    return following, score, dead or won, wasted


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
        """The best this board can score over `depth` more turns, and the line that does it, as (action, label)."""
        if depth == 0:
            return self.leaf(state), []
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
        best = (float("-inf"), [])
        for _, action, following, score, final, factor in children[:self.beam if depth > 1 else self.leaf_beam]:
            if final:
                total, rest = score + factor * self.leaf(following), []
            else:
                later, rest = self.value(following, depth - 1)
                total = score + factor * later
            if total > best[0]:
                best = (total, [(action, action.label(state))] + rest)
        if best[0] == float("-inf"):
            best = (self.leaf(state), [])
        self.memo[key] = best
        return best


def line_for(state, action, depth, search):
    """The best line over `depth` turns starting with `action`."""
    following, score, final, wasted = _turn(state, action, now=True)
    factor = _factor(following)
    if final or depth == 1:
        later, rest = search.leaf(following), []
    else:
        later, rest = search.value(following, depth - 1)
    return Line([action] + [a for a, _ in rest], score + factor * later,
                [action.label(state)] + [label for _, label in rest],
                {"this turn": score, "after": factor * later}, _cheap(following), wasted)


def _sorted(lines):
    lines = [line for line in lines if not line.wasted]
    lines.sort(key=lambda line: line.sort_key, reverse=True)
    return lines


def rank_lines(state, depth, beam=BEAM, leaf_beam=LEAF_BEAM, deadline=None):
    """Every action available now, best first, each with the best line after it over `depth` turns in all. None if
    a `deadline` (a time.time()) passes first."""
    search = Search(beam, leaf_beam, deadline)
    try:
        return _sorted([line_for(state, action, depth, search) for action in legal_actions(state)])
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
                line.position_next_turn, line.wasted)


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
                found[depth] = _sorted([_as(lines[rep], state, a) for rep, members in groups.items() for a in members])
        return found
    return collect


def rank_lines_parallel(state, depth, pool, beam=BEAM, leaf_beam=LEAF_BEAM):
    """rank_lines with each of this turn's actions searched by its own worker from `pool`. Boards reached under two
    different first actions get searched twice, the price of not sharing memory between workers."""
    jobs = [(state, action, depth, beam, leaf_beam, None) for action in legal_actions(state)]
    return _sorted(list(pool.map(_line_task, jobs)))
