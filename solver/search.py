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

from evaluator import (WEIGHTS, Line, _cheapest_hit, _kept_terms, fight_won, leaf_terms, outcome_terms,
                       unanswerable_damage)
from rules import UNKNOWN_COPY, UNKNOWN_TILE, legal_actions, step

BEAM = 4
LEAF_BEAM = 2  # On the last turn, only this many of the BEAM get the full position score.


def certain(state):
    """Whether the coming turn is fully known: every enemy's telegraph and tiles, and no wave about to arrive."""
    if state.turns_until_wave is not None and not state.last_wave and state.turns_until_wave <= 1:
        return False
    for enemy in state.enemies:
        if enemy.alive and (not enemy.known or any(a.name in (UNKNOWN_TILE, UNKNOWN_COPY) for a in enemy.queue)):
            return False
    return True


def _factor(state):
    return 1.0 if certain(state) else WEIGHTS["future_discount"]


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


def _turn(state, action):
    """One turn: the next board, what it scored, and whether the line ends there or wastes a tile."""
    following, outcome = step(state, action)
    dead = not following.hero.alive
    score = sum(outcome_terms(outcome, dead, _cheapest_hit(state)).values())
    won = not dead and fight_won(following)
    if won and outcome.hp_lost == 0:
        score += WEIGHTS["win"]
    wasted = action.kind == "Attack" and outcome.wasted_attacks > 0
    return following, score, dead or won, wasted


def _leaf(state):
    if not state.hero.alive:
        return 0.0
    return sum(leaf_terms(state).values()) + WEIGHTS["no_response"] * unanswerable_damage(state)


def _cheap(state):
    return sum(_kept_terms(state).values()) if state.hero.alive else 0.0


class Search:
    def __init__(self, beam=BEAM, leaf_beam=LEAF_BEAM):
        self.beam = beam
        self.leaf_beam = leaf_beam
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


def rank_lines(state, depth, beam=BEAM, leaf_beam=LEAF_BEAM):
    """Every action available now, best first, each with the best line after it over `depth` turns in all."""
    search = Search(beam, leaf_beam)
    lines = []
    for action in legal_actions(state):
        following, score, final, wasted = _turn(state, action)
        factor = _factor(following)
        if final or depth == 1:
            later, rest = search.leaf(following), []
        else:
            later, rest = search.value(following, depth - 1)
        lines.append(Line([action] + [a for a, _ in rest], score + factor * later,
                          [action.label(state)] + [label for _, label in rest],
                          {"this turn": score, "after": factor * later}, _cheap(following), wasted))
    lines = [line for line in lines if not line.wasted]
    lines.sort(key=lambda line: line.sort_key, reverse=True)
    return lines
