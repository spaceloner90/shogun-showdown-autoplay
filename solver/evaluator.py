"""The evaluator and search: tries the hero's possible action sequences and scores where they lead.

Nothing is remembered between turns. Each turn the search runs from the current position, and only
the first action of the best line gets played. A queued tile has no fixed target: what it's worth
is recalculated from the board each time.

Enemies do what they telegraphed on the first simulated turn. After that their actions are unknown,
so they stay put. The enemy AI is never used here: only what a player can see.

Only depth 1 is in use, so everything a plan needs has to show up in how a position is scored.

research/design.md has the reasoning behind all of this. Principles, from how the game plays:
- Every attack is telegraphed and the hero acts first, so being in range isn't dangerous by itself.
  It's dangerous when there's no answer: no kill available and nowhere safe to step.
- The hero has priority, so backing away at the last moment is a fine way to dodge. Closing in with
  nothing to threaten them with isn't worth much.
- Facing the ideal target and not being surrounded matter more than distance.
- Killing fast matters, because the next wave arrives on a timer and can overload the room.
- Queue edits are free, so a loaded tile commits to nothing: it can be reordered or taken back when
  firing. Loading early is an option worth having even with nothing in range yet.
- A Free Play tile in hand is as good as loaded, since it can join any attack for free. So it's only
  ever played as part of an attack, and it counts toward a stack from the hand.
- A kill is worth far more than the same damage as a wound, and one volley doing the work of several
  saves turns. So what a stack could do counts even when it needs a step or a flip to get there.
  Bosses need no special handling: when no stack can reach a kill, there's no kill to value.
- A curse doubles the enemy's next hit, so it's worth what that adds to the hero's next attack, which
  is worth more when it turns a wound into a kill. It's worth nothing on an enemy that dies.
- A hero's shield blocks a whole hit, and most hits can't be dodged, so it's best kept for one of those.
  Spending it on a hit that could have been dodged has a cost.
- An enemy's shield is different: it has to be removed anyway, so it counts as extra HP, equal to the
  hero's weakest tile, since that's the cheapest way to remove it. Breaking one earns that credit.
- Where to stand depends on the kit, the same rule for every hero: the farthest distance its tiles do
  the most damage from. A melee kit comes out at 1. Being flanked or surrounded is much worse with no
  way out.
- A move that repositions the hero or an enemy is worth something kept, by how flexible it is, so
  firing one for its damage alone gives up more than the tile. These are values on the move itself,
  not lookahead.
- When a boss dies, everyone else dies too. Ordinary summons are still real threats worth killing, but
  the Shogun's statues are only there to get in the way, so the boss comes first.

All the weights are first guesses, kept together here so they're easy to change.

Versions: bump VERSION with any change that can alter a choice (weights, scoring, search, or the
simulation in rules.py), commit it, and tag the commit evaluator-<version>. Every report, analysis
and decision in the logs records the version it came from.
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field

from rules import (ONE_ENEMY_WAVE_CAP, QUEUE_CAP, SMOKE_BOMBS, SNIPER_DISTANCE, SWAP, UNKNOWN_TILE, Action, Attack, Outcome, State,
                   apply_attack, can_use_special, enemy_cells, fireable_attacks, is_tank, legal_actions, perform_special,
                   spring_traps, step, strike_cell, targets_of)

VERSION = "v1.19"  # Unvetted: see research/unvetted.md for what real logs haven't confirmed.

WEIGHTS = {
    # What happens along the line.
    "hp_lost": -100.0,        # Per HP. The goal is to clear the battle without losing any.
    "death": -10000.0,
    "enemy_damage": 10.0,     # Per enemy HP removed by the hero.
    "tank_damage": 2.5,       # Per HP removed from a tank that will die with its boss anyway.
    "poison_turn": 8.0,       # Per turn of poison left on an enemy, like damage another enemy deals.
    "trap_planted": 0.4,      # A trap on the ground, as a share of what its damage is worth. Only enemies set
                              # one off, so it's all upside: the player's read is a third to half.
    "shove_cell": 4.0,        # Per cell an enemy is shoved. Space to load in, but melee wants them close too.
    "kill": 60.0,
    "friendly_damage": 8.0,   # Per enemy HP removed by another enemy.
    "future_discount": 0.85,  # The same result one turn later is worth this fraction.
    "no_response": -60.0,     # Per point of threatened damage the hero's best answer leaves.

    # How good the final position is.
    # What firing the stack would be worth, by how many moves and flips it takes to get there.
    "stack_fractions": (0.6, 0.45, 0.35, 0.25),
    "ready_tile": 2.0,        # Per tile that's charged, in hand or queue.
    "loaded_damage": 2.0,     # Per point of damage in the queue, whether or not anything's in range.
    "swap_ready": 3.0,        # Having the special move charged, so spending it has a cost.
    # What keeping each repositioning move is worth, charged and loaded. First guesses from how flexible each is,
    # to tune later.
    "escape_values": {
        "SwapSpecialMove": 12.0,                    # Past an adjacent enemy, any time, without a tile.
        "SmokeBomb": 12.0, "BackSmokeBomb": 12.0,   # Past the first target, at any range.
        "ShadowDash": 9.0, "BackShadowDash": 9.0,   # Behind a target, past everyone in between.
        "PushSpecialMove": 6.0,                     # Pushes an adjacent enemy away, without a tile. Not past it.
        "Dash": 6.0,                                # Away to the last free cell, but only into open space.
        "DragonPunch": 4.0,                         # Pushes the target away, as a tile.
        "Charge": 4.0, "BackCharge": 4.0,           # To the last free cell, but next to whoever is there.
        "GrapplingHook": 1.0,                       # Moves the target, but toward the hero: almost never helps.
    },
    # What keeping a move that brings an enemy in is worth, per point of damage of the strongest short-reach tile
    # in the kit, which can exploit it. On top of its escape value, and with the same modifiers.
    "setup_values": {"GrapplingHook": 1.0},
    "short_reach": 2,         # A tile reaching no farther than this needs enemies brought in.
    "shockwave_loaded": 0.5,  # Per loaded Shockwave tile, for chains it may find once enemies bunch up, beyond any
                              # the stack sees from here. A tiebreak: it prefers the Shockwave version of a tile
                              # over an identical plain one, but never over a tile doing a point more damage.
    "escape_in_hand": 2 / 3,  # A tile in hand rather than loaded. Loading adds only a little, so it doesn't beat
                              # a high damage tile to the queue, since any attack would spend it.
    "escape_no_target": 1 / 3,  # One that acts on a target, with nobody it can act on.
    "escape_others": 0.5,     # Each escape beyond the best, which helps less.
    "escape_two_way": 1.5,    # A special move with Two Way Move covers both sides, so it's worth this much more.
    "curse": 0.5,             # Fraction of what a curse would add to the hero's next hit on that enemy.
    "shield": 100.0,          # Holding a shield, worth about 1 HP. Hits average 1.4, but it may go unused.
    "facing_ideal": 6.0,      # Facing the enemy we most want to hit.
    "facing_other": 2.0,      # Facing an enemy, but not that one.
    "distance": -2.0,         # Per cell of gap between the hero and the ideal target.
    "unarmed_distance": 0.25, # The share of that which still applies with nothing to threaten them.
    "surrounded": -20.0,      # Enemies directly on both sides.
    "flanked": -6.0,          # Enemies on both sides, at any distance.
    "no_way_out": 2.5,        # How much worse those are with no charged Swap and no charged Smoke Bomb that reaches.
    "crowding": -3.0,         # Per cell an enemy is closer than the hero's tiles need it to be. -10 stalls fights.
    "max_standoff": 3,        # The furthest a kit prefers to stand off, so it doesn't run to the wall.
    "enemy_hp_left": -4.0,    # Per enemy HP still in the room.
    "wave_pressure": -3.0,    # Per enemy HP in the room, scaled up as the next wave gets close.
}

# An enemy's newly played tile isn't identified in the simulation. Assume a short, ordinary attack.
ASSUMED_UNKNOWN = Attack("Assumed", 2, [1], first_target=True)


@dataclass
class Line:
    """One evaluated sequence of hero actions."""
    actions: list[Action]
    score: float
    labels: list[str]
    terms: dict[str, float] = field(default_factory=dict)
    # How good the position is right after the first action. Only used to break ties, so that of
    # two lines ending in the same place, the one improving things sooner wins.
    position_next_turn: float = 0.0

    @property
    def sort_key(self):
        return round(self.score, 2), self.position_next_turn


def _light_copy(state):
    """A copy of the board that attacks can change. Tiles and the queue are shared, so leave those alone."""
    trial = copy.copy(state)
    trial.hero = copy.copy(state.hero)
    trial.enemies = [copy.copy(e) for e in state.enemies]
    return trial


def _preview_fire(state, attacks, cell=None, flip=False):
    """Fires these attacks on a copy of the board, from `cell` if given. Returns the copy and the outcome."""
    trial = _light_copy(state)
    if cell is not None:
        trial.hero.cell = cell
    if flip:
        trial.hero.facing = -trial.hero.facing
    outcome = Outcome()
    for attack in attacks:
        before = enemy_cells(trial)
        apply_attack(trial, trial.hero, attack, outcome)
        spring_traps(trial, outcome, before)
    return trial, outcome


def _cheapest_hit(state):
    """The damage of the weakest tile available: what it costs to remove an enemy's shield."""
    tiles = [t.attack.value for t in state.tiles if t.attack.value > 0]
    ready = [t.attack.value for t in state.tiles if t.attack.value > 0 and (t.in_queue or t.ready)]
    return min(ready or tiles or [1])


def _effective_hp(state, enemy):
    hp = enemy.hp
    # Damage to the Side twin comes off the Main twin, so the Main twin's HP is what it takes to win.
    if enemy.kind == "TwinSideBoss":
        hp = next((e.hp for e in state.enemies if e.kind == "TwinMainBoss" and e.alive), hp)
    return hp + (_cheapest_hit(state) if enemy.shield else 0)


def _volley_value(outcome, cheapest_hit):
    broken = outcome.shields_broken * cheapest_hit * WEIGHTS["enemy_damage"]
    return (outcome.enemy_damage * WEIGHTS["enemy_damage"] + outcome.tank_damage * WEIGHTS["tank_damage"]
            + outcome.kills * WEIGHTS["kill"] + broken + outcome.shove_cells * WEIGHTS["shove_cell"])


def _stack_value(state):
    """What the queue is worth: its best volley from anywhere nearby, less the moves needed to get there.

    Firing order is free, so every order is tried. Only the hero moves here: enemies stay put.
    """
    attacks_available = fireable_attacks(state)
    if not attacks_available:
        return 0.0
    fractions = WEIGHTS["stack_fractions"]
    cheapest_hit = _cheapest_hit(state)
    poison_now = _poison_value(state)
    traps_now = _trap_value(state)

    def volley(attacks, cell, flip):
        trial, outcome = _preview_fire(state, attacks, cell, flip)
        # Measured after the whole volley, so poison on an enemy that then dies is worth nothing. Traps it plants
        # count the same way.
        return (_volley_value(outcome, cheapest_hit) + _poison_value(trial) - poison_now
                + _trap_value(trial) - traps_now)

    best = 0.0
    orders = list(itertools.permutations(attacks_available, min(len(attacks_available), QUEUE_CAP)))
    for direction in (0, -1, 1):
        for steps in range(0 if direction == 0 else 1, 1 if direction == 0 else len(fractions)):
            cell = state.hero.cell + direction * steps
            if not 0 <= cell < state.cells or state.occupant(cell) is not None:
                break
            for flip in (False, True):
                actions = steps + flip
                if actions >= len(fractions):
                    continue
                for attacks in orders:
                    best = max(best, volley(attacks, cell, flip) * fractions[actions])
    # Staying put is covered above only for an occupied-free start, which the hero's own cell isn't.
    for flip in (False, True):
        for attacks in orders:
            best = max(best, volley(attacks, None, flip) * fractions[int(flip)])
    return best


def _hit_value(enemy, damage):
    value = min(damage, enemy.hp) * WEIGHTS["enemy_damage"]
    return value + WEIGHTS["kill"] if damage >= enemy.hp else value


def _curse_value(state):
    """What the curses on enemies are worth: a fraction of how much better each makes the next hit there.

    That compares the hero's best hit with the curse against the best without it, with a discount for
    each turn until a tile is ready. Both are capped by the enemy's health, so a curse adds nothing to
    an enemy that a ready tile would kill anyway. When tiles are ready to fire, the stack's value
    already includes the doubled damage, so this adds nothing.
    """
    if fireable_attacks(state):
        return 0.0
    total = 0.0
    for enemy in state.enemies:
        if not enemy.alive or not enemy.curse or is_tank(state, enemy):
            continue
        with_curse = without_curse = 0.0
        for tile in state.tiles:
            value = tile.attack.value
            discount = WEIGHTS["future_discount"] ** max(0, tile.cooldown - tile.charge)
            with_curse = max(with_curse, _hit_value(enemy, value * 2) * discount)
            without_curse = max(without_curse, _hit_value(enemy, value) * discount)
        total += with_curse - without_curse
    return total * WEIGHTS["curse"]


def _threat_damage(state, cell):
    """Damage the attacks visible in enemy queues would do to a hero standing at `cell`.

    Plays them out on a copy, so a first-target attack is blocked by anyone in the way, and a dash
    carries its enemy into range of whatever it fires next.
    """
    trial = _light_copy(state)
    trial.hero.cell = cell
    trial.hero.hp = 1000  # Only here to count damage, so the hero mustn't fall over midway.
    outcome = Outcome()
    for enemy in trial.enemies:
        if not enemy.alive or enemy.ice > 0:
            continue
        for attack in enemy.queue:
            attack = ASSUMED_UNKNOWN if attack.name == UNKNOWN_TILE else attack
            apply_attack(trial, enemy, attack, outcome)
    # Whatever is marked on the cells for the coming turn.
    for hazard in state.hazards:
        if trial.hero.cell in hazard["groups"][0]:
            strike_cell(trial, None, trial.hero.cell, hazard["damage"], outcome, hazard.get("heals_boss", True))
    return outcome.hp_lost


def _threat_after_special(state, direction):
    trial = _light_copy(state)
    perform_special(trial, direction, Outcome())
    trial.enemies = [e for e in trial.enemies if e.alive]
    return _threat_damage(trial, trial.hero.cell)


def unanswerable_damage(state):
    """Threatened damage left after the hero's best answer next turn.

    The answers are stepping aside, using the special move on an enemy, or firing the queue and removing
    whoever it kills. When nothing removes the threat entirely, the answer leaving the least still counts.
    """
    hero = state.hero
    best = _threat_damage(state, hero.cell)
    if best == 0:
        return 0
    for direction in (-1, 1):
        cell = hero.cell + direction
        if 0 <= cell < state.cells:
            if state.occupant(cell) is None:
                best = min(best, _threat_damage(state, cell))
            elif can_use_special(state, direction):
                best = min(best, _threat_after_special(state, direction))
    attacks_available = fireable_attacks(state)
    for attacks in itertools.permutations(attacks_available, min(len(attacks_available), QUEUE_CAP)):
        if not attacks:
            break
        trial, _ = _preview_fire(state, attacks)
        trial.enemies = [e for e in trial.enemies if e.alive]
        best = min(best, _threat_damage(trial, trial.hero.cell))
    return best


def ideal_target(state):
    """The enemy to focus: the quickest kill, then the closest. Only uses what's on the board."""
    enemies = [e for e in state.enemies if e.alive]
    if not enemies:
        return None
    enemies = [e for e in enemies if not is_tank(state, e)] or enemies
    return min(enemies, key=lambda e: (_effective_hp(state, e), abs(e.cell - state.hero.cell)))


def _threat_presented(state, target):
    """From 0 to 1, how much of the target's HP the hero could deal soon: loaded, ready or nearly ready."""
    damage = 0
    for tile in state.tiles:
        if tile.in_queue or tile.cooldown - tile.charge <= 1:
            damage += tile.attack.value
    return min(1.0, damage / max(1, _effective_hp(state, target)))


def preferred_distance(state):
    """How far from an enemy the hero wants to stand, from what its tiles can reach.

    The farthest distance where the tiles it will have soon do the most damage, so reach is used to stay
    out of trouble. A melee kit comes out at 1. The same rule for every hero. Sniper's bonus counts too,
    and with it the hero may stand off as far as the bonus starts.
    """
    soon = [t for t in state.tiles if t.attack.value > 0 and (t.in_queue or t.cooldown - t.charge <= 1)]
    tiles = soon or [t for t in state.tiles if t.attack.value > 0]
    farthest = max(WEIGHTS["max_standoff"], SNIPER_DISTANCE if state.sniper_bonus else 0)
    reach = {d: sum(t.attack.value + (state.sniper_bonus if d >= SNIPER_DISTANCE else 0)
                    for t in tiles if d in map(abs, t.attack.range))
             for d in range(1, farthest + 1)}
    most = max(reach.values())
    return max(d for d, damage in reach.items() if damage == most) if most else 1


def _swap_charged(state):
    """A charged Swap is a way out, whoever is around. It needs nobody adjacent yet, since closing in is what
    brings enemies next to the hero, and requiring it had F1 walk up to them just so the way out would count.
    Nor does it need anyone swappable now: that made killing the last one look bad, though more will come."""
    return state.special == SWAP and state.swap_charge >= state.swap_cooldown


def _ready_smoke_bombs(state):
    """Charged Smoke Bombs, in hand or loaded, each with whether it reaches someone it can trade places with.

    Either counts as a way out when flanked: counting only loaded ones had F1 load it over the Spear just to
    keep one. How much more a loaded one is worth is left to the escape value."""
    return [(t, any(a.movable for a in targets_of(state, state.hero, t.attack)[:1]))
            for t in state.tiles if t.attack.name in SMOKE_BOMBS and t.ready]


def _has_way_out(state):
    """Whether the hero can get past enemies that close in: a charged Swap, or a ready Smoke Bomb that reaches
    someone."""
    return _swap_charged(state) or any(reaches for _, reaches in _ready_smoke_bombs(state))


def _position_terms(state):
    target = ideal_target(state)
    if target is None:
        return {}
    hero = state.hero
    ahead = [e for e in state.enemies if e.alive and (e.cell - hero.cell) * hero.facing > 0]
    if target in ahead:
        facing = WEIGHTS["facing_ideal"]
    else:
        facing = WEIGHTS["facing_other"] if ahead else 0.0

    left = [e for e in state.enemies if e.alive and e.cell < hero.cell]
    right = [e for e in state.enemies if e.alive and e.cell > hero.cell]
    surrounded = 0.0
    if left and right:
        adjacent = state.occupant(hero.cell - 1) is not None and state.occupant(hero.cell + 1) is not None
        surrounded = WEIGHTS["surrounded"] if adjacent else WEIGHTS["flanked"]
        if not _has_way_out(state):
            surrounded *= WEIGHTS["no_way_out"]

    # Closing in matters less with nothing to threaten them with.
    floor = WEIGHTS["unarmed_distance"]
    armed = floor + (1.0 - floor) * _threat_presented(state, target)
    preferred = preferred_distance(state)
    nearest = min(abs(e.cell - hero.cell) for e in state.enemies if e.alive and not is_tank(state, e)) \
        if any(e.alive and not is_tank(state, e) for e in state.enemies) else preferred
    return {
        "facing": facing,
        "distance": WEIGHTS["distance"] * armed * max(0, abs(target.cell - hero.cell) - preferred),
        "crowding": WEIGHTS["crowding"] * max(0, preferred - nearest),
        "surrounded": surrounded,
    }


def _pressure_terms(state):
    hp_left = sum(_effective_hp(state, e) for e in state.enemies
                  if e.alive and e.kind != "TwinSideBoss" and not is_tank(state, e))
    terms = {"enemy_hp_left": WEIGHTS["enemy_hp_left"] * hp_left}
    if state.turns_until_wave is not None and not state.last_wave:
        closeness = 1.0 - max(0, min(state.turns_until_wave, ONE_ENEMY_WAVE_CAP)) / ONE_ENEMY_WAVE_CAP
        terms["wave_pressure"] = WEIGHTS["wave_pressure"] * hp_left * closeness
    return terms


# Repositioning tiles that act on their first target ahead, and only do so if it's there and movable.
_MOVES_TARGET = SMOKE_BOMBS | {"DragonPunch", "GrapplingHook"}


def _loaded_can_kill(state):
    """Whether the loaded tiles can kill from here, in which case the loaded ones are about to go off."""
    attacks_available = fireable_attacks(state)
    return any(attacks and _preview_fire(state, attacks)[1].kills
               for attacks in itertools.permutations(attacks_available, min(len(attacks_available), QUEUE_CAP)))


def _kept_tiles(state, values, loaded_can_kill):
    """What each charged tile named in `values` is worth kept, with the modifiers every kept move shares: less
    in hand than loaded, little with nobody to act on, and nothing loaded when the loaded tiles can kill."""
    kept = []
    for tile in state.tiles:
        if tile.attack.name not in values or not tile.ready or (tile.in_queue and loaded_can_kill):
            continue
        value = values[tile.attack.name]
        if not tile.in_queue:
            value *= WEIGHTS["escape_in_hand"]
        if tile.attack.name in _MOVES_TARGET \
                and not any(a.movable for a in targets_of(state, state.hero, tile.attack)[:1]):
            value *= WEIGHTS["escape_no_target"]
        kept.append(value)
    return kept


def _setup_value(state, loaded_can_kill):
    """A move that brings an enemy in, kept, for a short-reach tile in the kit to exploit.

    Worth more the harder the strongest such tile hits, whether or not it's charged. Bringing an enemy in also
    crowds the hero, which the crowding penalty weighs against it."""
    values = WEIGHTS["setup_values"]
    exploit = max((t.attack.value for t in state.tiles if t.attack.value > 0 and t.attack.name not in values
                   and max(map(abs, t.attack.range)) <= WEIGHTS["short_reach"]), default=0)
    return exploit * max(_kept_tiles(state, values, loaded_can_kill), default=0.0)


def _escape_value(state, loaded_can_kill=None):
    """Repositioning moves kept, of the hero or of others: each is a way to get out of trouble later.

    Each move is worth what `escape_values` guesses from its flexibility: whether it gets the hero past an
    enemy, away, or only moves the enemy, and in how many situations it works. Spending one for its damage
    alone gives that up for several turns, which is worth counting, so a Swap with Damaging Move gets used for
    damage once it hits hard enough. A special move that can go backward covers both sides, so it's worth
    more. A loaded tile can be used this turn and one in hand can't, but it's never fully relied on until it's
    fired: any attack would spend it. So loading one adds only a little. A move that acts on a target is
    worth little with nobody it can act on. If the loaded tiles can kill from here, the loaded ones go off
    with them rather than being kept, so they earn nothing: otherwise they could talk the hero out of the
    kill. Firing tiles never spends a special move. Having several helps, but each beyond the best counts for
    only part of its value.
    """
    values = WEIGHTS["escape_values"]
    if loaded_can_kill is None:
        loaded_can_kill = _loaded_can_kill(state)
    kept = _kept_tiles(state, values, loaded_can_kill)
    if state.special in values and state.swap_charge >= state.swap_cooldown:
        kept.append(values[state.special] * (WEIGHTS["escape_two_way"] if state.two_way_swap else 1.0))
    kept.sort(reverse=True)
    return sum(kept[:1]) + WEIGHTS["escape_others"] * sum(kept[1:])


def _trap_value(state):
    """Traps on the ground. Only enemies set them off, so each is worth part of its damage, for the chance one
    walks or is pulled onto it. Once it goes off it's gone, and the damage itself counts."""
    return WEIGHTS["trap_planted"] * WEIGHTS["enemy_damage"] * sum(t["damage"] for t in state.traps)


def _poison_value(state):
    """Poison still to come: good on an enemy, as far as its HP goes, and bad on the hero."""
    value = sum(min(e.poison, e.hp) * WEIGHTS["poison_turn"] for e in state.enemies
                if e.alive and e.kind != "TwinSideBoss" and not is_tank(state, e))
    return value + state.hero.poison * WEIGHTS["hp_lost"]


def leaf_terms(state: State) -> dict[str, float]:
    """Scores a position by itself, as named parts so a decision can be explained."""
    kept_names = set(WEIGHTS["escape_values"]) | set(WEIGHTS["setup_values"])
    loaded_can_kill = any(t.attack.name in kept_names and t.ready for t in state.queue_tiles) \
        and _loaded_can_kill(state)
    terms = {
        "poison": _poison_value(state),
        "traps": _trap_value(state),
        "escape": _escape_value(state, loaded_can_kill),
        "setup": _setup_value(state, loaded_can_kill),
        "effects": WEIGHTS["shockwave_loaded"] * sum(t.attack.effect == "Shockwave" for t in state.queue_tiles),
        "stack": _stack_value(state),
        "curse": _curse_value(state),
        "shield": WEIGHTS["shield"] if state.hero.shield else 0.0,
        "ready_tiles": WEIGHTS["ready_tile"] * sum(t.ready for t in state.tiles),
        # An attack can only fire what the queue holds, so anything beyond that adds nothing.
        "loaded": WEIGHTS["loaded_damage"] * sum(sorted((a.value for a in fireable_attacks(state)), reverse=True)[:QUEUE_CAP]),
        "swap_ready": WEIGHTS["swap_ready"] if state.swap_charge >= state.swap_cooldown else 0.0,
    }
    terms.update(_position_terms(state))
    terms.update(_pressure_terms(state))
    return terms


def outcome_terms(outcome: Outcome, hero_dead: bool, cheapest_hit: int = 1) -> dict[str, float]:
    return {
        "shields_broken": WEIGHTS["enemy_damage"] * cheapest_hit * outcome.shields_broken,
        "tank_damage": WEIGHTS["tank_damage"] * outcome.tank_damage,
        "shoves": WEIGHTS["shove_cell"] * outcome.shove_cells,
        "hp_lost": WEIGHTS["hp_lost"] * outcome.hp_lost,
        "death": WEIGHTS["death"] if hero_dead else 0.0,
        "enemy_damage": WEIGHTS["enemy_damage"] * outcome.enemy_damage,
        "kills": WEIGHTS["kill"] * outcome.kills,
        "friendly_damage": WEIGHTS["friendly_damage"] * outcome.friendly_damage,
    }


def _merge(total, terms, scale=1.0):
    for name, value in terms.items():
        total[name] = total.get(name, 0.0) + value * scale


def _evaluate_action(state, action, depth, scale):
    """Scores taking `action` now and then playing the best line for the remaining depth."""
    next_state, outcome = step(state, action)
    dead = not next_state.hero.alive
    terms = {}
    _merge(terms, outcome_terms(outcome, dead, _cheapest_hit(state)), scale)
    future_scale = scale * WEIGHTS["future_discount"]
    actions, labels = [action], [action.label(state)]
    position = 0.0
    if not dead:
        position = sum(leaf_terms(next_state).values())
        # Checked at every step of the line, so a plan can't hide a risky middle.
        _merge(terms, {"no_response": WEIGHTS["no_response"] * unanswerable_damage(next_state)}, future_scale)
        if depth > 1:
            best = _best_line(next_state, depth - 1, future_scale)
            actions += best.actions
            labels += best.labels
            _merge(terms, best.terms)
        else:
            _merge(terms, leaf_terms(next_state), future_scale)
    return Line(actions, sum(terms.values()), labels, terms, position)


def _best_line(state, depth, scale):
    return max((_evaluate_action(state, a, depth, scale) for a in legal_actions(state)),
               key=lambda line: line.sort_key)


def rank_actions(state: State, depth: int = 1) -> list[Line]:
    """Every action available now, best first, each with the best continuation found for it."""
    lines = [_evaluate_action(state, action, depth, 1.0) for action in legal_actions(state)]
    lines.sort(key=lambda line: line.sort_key, reverse=True)
    return lines
