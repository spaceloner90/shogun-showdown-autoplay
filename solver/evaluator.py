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
- Where to stand depends on the kit, the same rule for every hero: credit for each tile that can reach the
  target from here, and a small cost for each enemy adjacent. Being flanked or surrounded is much worse
  with no way out.
- Three rules every score keeps, from research/design.md: having more never scores lower, a tile has one
  use at a time, and terms that read the tiles only give credit. test_principles.py checks the first.
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
import heapq
import math
import itertools
from dataclasses import dataclass, field

from rules import (EDAMAME_HEAL, ICE_TURNS, ONE_ENEMY_WAVE_CAP, PHASE, QUEUE_CAP, SMOKE_BOMBS, SNIPER_DISTANCE, SWAP, UNKNOWN_COPY, UNKNOWN_TILE, Action, Attack, Outcome, State, Tile,
                   apply_attack, apply_potion, armored, can_use_special, enemy_cells, fight_won, fireable_attacks, free_hand_tiles, is_tank, fire_crossbow, legal_actions, move_destination, perform_special,
                   spring_traps, step, strike_cell, targets_of)

VERSION = "v2.12"  # Unvetted: see research/unvetted.md for what real logs haven't confirmed.

WEIGHTS = {
    # What happens along the line.
    "hp_lost": -100.0,        # Per HP. The goal is to clear the battle without losing any.
    "death": -10000.0,
    "enemy_damage": 10.0,     # Per enemy HP removed by the hero.
    "tank_damage": 2.5,       # Per HP removed from a tank that will die with its boss anyway.
    "poison_turn": 8.0,       # Per turn of poison left on an enemy, like damage another enemy deals.
    "ice_vs_kill": 0.5,       # A freshly frozen enemy is worth this share of killing it, as the player asked: it does
                              # nothing for 4 turns, which in practice is nearly as good. Less as its ice runs out.
    # Potions. Each is used on a key press of its own, and the next press analyzes the board it leaves.
    "heal_at_missing": EDAMAME_HEAL,  # Use Edamame once the hero is missing at least what it heals, so none is wasted.
    "trap_planted": 0.4,      # A trap on the ground, as a share of what its damage is worth. Only enemies set
                              # one off, so it's all upside: the player's read is a third to half.
    "shove_cell": 4.0,        # Per cell an enemy is shoved. Space to load in, but melee wants them close too.
    "kill": 60.0,
    "win": 10000.0,           # Winning the fight this turn at no HP cost, in effect infinite: nothing beats it, as the
                              # player put it. A win that costs HP this turn earns nothing extra, so a safe win a turn
                              # later can still come first, rather than spend HP that carries into the next fight.
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
        # The Phase: past the adjacent enemy and any behind it, like the Swap (tied to it below).
        "SmokeBomb": 12.0,                          # Past the first target, at any range. BackSmokeBomb is tied.
        "ShadowDash": 9.0,                          # Behind a target, past everyone in between. BackShadowDash too.
        "PushSpecialMove": 6.0,                     # Pushes an adjacent enemy away, without a tile. Not past it.
        # The Throw: the enemy behind over to the front and away, a shove from behind (tied to the shove below).
        "Dash": 6.0,                                # Away to the last free cell, but only into open space.
        "DragonPunch": 4.0,                         # Pushes the target away, as a tile.
        "Charge": 4.0,                              # To the last free cell, but next to whoever is there. BackCharge too.
        "GrapplingHook": 1.0,                       # Moves the target, but toward the hero: almost never helps.
    },
    # What keeping a move that brings an enemy in is worth, per point of damage of the strongest short-reach tile
    # in the kit, which can exploit it. On top of its escape value, and with the same modifiers.
    "setup_values": {"GrapplingHook": 1.0},
    "short_reach": 2,         # A tile reaching no farther than this needs enemies brought in.
    # Per loaded tile with each effect, for what the effect may do once it lands, beyond what the stack sees from here.
    # Tiebreaks: each prefers the version of a tile with the effect over an identical plain one, but never over a
    # tile doing a point more damage. A Shockwave's chains need enemies bunched up. A curse's worth depends on who it
    # lands on, which the stack doesn't score.
    "loaded_effects": {"Shockwave": 0.5, "Curse": 0.5, "Ice": 0.5},
    # How much more a tile that can hit two in a line is worth than its stated damage, where its potential is
    # valued (loaded damage and reach), as with an effect: what it does when fired counts as it happens. First
    # guesses: the Crossbow hits any 2 across its whole range, so it lines up a double far more often than the
    # Spear, which needs them on the 2 cells ahead.
    "pierce": {"Crossbow": 1.5, "Spear": 1.25},
    "escape_in_hand": 2 / 3,  # A tile in hand rather than loaded. Loading adds only a little, so it doesn't beat
                              # a high damage tile to the queue, since any attack would spend it.
    "escape_no_target": 1 / 3,  # One that acts on a target, with nobody it can act on.
    "escape_others": 0.5,     # Each escape beyond the best, which helps less.
    "escape_two_way": 1.5,    # A special move with Two Way Move covers both sides, so it's worth this much more.
    "curse": 0.5,             # Fraction of what a curse would add to the hero's next hit on that enemy.
    "wound": 0.5,             # With Scar Strike in the deck, the share of its damage on each wounded enemy, as the
                              # player asked: a 1-damage chip on an enemy at full health is worth half as much again.
    "shield": 100.0,          # Holding a shield, worth about 1 HP. Hits average 1.4, but it may go unused.
    "facing_ideal": 6.0,      # Facing the enemy we most want to hit.
    "facing_other": 2.0,      # Facing an enemy, but not that one.
    # Per point of damage a tile can deal the ideal target from where the hero stands, up to its HP, discounted per
    # turn until the tile is ready. Each cell the hero would have to move to bring the tile in range takes off a
    # share, so closing in pays a little per cell.
    "reach": 4.0,
    "reach_falloff": 0.25,
    "surrounded": -20.0,      # Enemies directly on both sides.
    "flanked": -6.0,          # Enemies on both sides, at any distance.
    "no_way_out": 2.5,        # How much worse those are with no charged Swap and no charged Smoke Bomb that reaches.
    "stand_off": -1.5,        # Per enemy adjacent to the hero, whatever its tiles: so a kit that hits as hard
                              # from further away stands off. Small, so a melee kit still closes in.
    "enemy_hp_left": -4.0,    # Per enemy HP still in the room.
    "wave_pressure": -3.0,    # Per enemy HP in the room, scaled up as the next wave gets close.
}

# Values defined as equal to others are tied here, so changing one changes them all.
_ESCAPES = WEIGHTS["escape_values"]
_ESCAPES["PhaseSpecialMove"] = _ESCAPES["SwapSpecialMove"]
_ESCAPES["ThrowSpecialMove"] = _ESCAPES["PushSpecialMove"]
for _name in ("SmokeBomb", "ShadowDash", "Charge"):
    _ESCAPES["Back" + _name] = _ESCAPES[_name]

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
    # Whether the first action fires a tile that does nothing. Sending it back instead is a free queue edit that
    # leaves the board the same and the tile ready, so such a line is never the better one, and it's left out.
    wasted: bool = False

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
    """The damage of the weakest tile in the deck: what it costs to remove an enemy's shield. The whole deck rather
    than the ready tiles, so a weak tile coming ready doesn't make breaking a shield worth less (rule 1)."""
    return min((t.attack.value for t in state.tiles if t.attack.value > 0), default=1)


def _effective_hp(state, enemy):
    hp = enemy.hp
    # Damage to the Side twin comes off the Main twin, so the Main twin's HP is what it takes to win.
    if enemy.kind == "TwinSideBoss":
        hp = next((e.hp for e in state.enemies if e.kind == "TwinMainBoss" and e.alive), hp)
    return hp + (_cheapest_hit(state) if enemy.shield else 0)


def _volley_value(outcome, cheapest_hit):
    broken = outcome.shields_broken * cheapest_hit * WEIGHTS["enemy_damage"]
    return (outcome.enemy_damage * WEIGHTS["enemy_damage"] + outcome.tank_damage * WEIGHTS["tank_damage"]
            + outcome.kills * WEIGHTS["kill"] + broken + outcome.shove_cells * WEIGHTS["shove_cell"]
            + _reload_value(outcome))


def _loaded_worth(name, damage):
    """What a tile's damage is worth loaded, with a piercing tile's potential."""
    return WEIGHTS["loaded_damage"] * damage * WEIGHTS["pierce"].get(name, 1.0)


def _reload_value(outcome):
    """A Crossbow's reload is worth having its loaded tile ready, as the player put it: what a ready tile loaded
    with that damage holds on the position, read from the same values, so it follows any change to them. Earned when
    it fires, since that's when the reload happens; the shot it sets up counts for its own damage when that fires
    (rule 2)."""
    return WEIGHTS["ready_tile"] * outcome.reloads + _loaded_worth("Crossbow", outcome.reloaded)


def _volleys(state):
    """Every way to fire: loaded and Free Play tiles, any number of them up to what the queue holds, in every order.
    Every size, since a tile that would hurt a volley can always be left out."""
    tiles = list(state.queue_tiles) + free_hand_tiles(state)
    for size in range(1, min(len(tiles), QUEUE_CAP) + 1):
        yield from itertools.permutations(tiles, size)


def _spent(trial, fired):
    """The board a volley leaves, with its tiles out of the queue and on cooldown. A trial board shares its tiles
    with the position it came from, so they're copied first."""
    copies = {id(t): copy.copy(t) for t in trial.tiles}
    fired_ids = {id(t) for t in fired}
    trial.tiles = [copies[id(t)] for t in trial.tiles]
    trial.queue_tiles = [copies[id(t)] for t in trial.queue_tiles if id(t) not in fired_ids]
    for tile_id in fired_ids:
        copies[tile_id].in_queue = False
        copies[tile_id].charge = 0
        fire_crossbow(copies[tile_id], Outcome())
    trial.hero.queue = [t.attack for t in trial.queue_tiles]
    return trial


def _agent_key(agent):
    queue = tuple((a.name, a.value, tuple(a.range), a.first_target, a.effect, a.target_cell) for a in agent.queue)
    return (agent.kind, agent.cell, agent.facing, agent.hp, agent.max_hp, agent.shield, queue, agent.action,
            agent.curse, agent.movable, agent.poison, agent.ice, agent.freezable, agent.elite)


def _board_key(trial, fired):
    """Everything about a volley's board that its score reads, with which tiles it fired."""
    traps = tuple((t["cell"], t["damage"], t["effect"]) for t in trial.traps)
    return (frozenset(id(t) for t in fired), _agent_key(trial.hero),
            tuple(_agent_key(e) for e in trial.enemies), traps)


def _stack_value(state, kept_now):
    """What firing the loaded tiles is worth beyond keeping them: the best volley, from here or after a few moves or
    a flip.

    One tile, one use (rule 2): a volley spends its tiles, so it's credited with what it does plus how the position
    it leaves scores without them, less how this position scores with them all kept. That difference counts at the
    volley's fraction for the moves it needs, as the chance it lands, and never below nothing, since the hero can
    always keep them. Every order and size is tried. Only the hero moves here: enemies stay put.
    """
    volleys = list(_volleys(state))
    if not volleys:
        return 0.0
    fractions = WEIGHTS["stack_fractions"]
    cheapest_hit = _cheapest_hit(state)

    # Different orders often leave the same board, so each board left is scored once.
    kept_after = {}

    def gain(tiles, cell, flip):
        trial, outcome = _preview_fire(state, [t.attack for t in tiles], cell, flip)
        for tile in tiles:
            if tile.attack.name == "Crossbow" and tile.attack.value == 0:
                fire_crossbow(copy.copy(tile), outcome)
        done = _volley_value(outcome, cheapest_hit) + WEIGHTS["hp_lost"] * outcome.hp_lost
        if not trial.hero.alive:
            return done + WEIGHTS["death"]
        key = _board_key(trial, tiles)
        if key not in kept_after:
            kept_after[key] = sum(_kept_terms(_spent(trial, tiles)).values())
        return done + kept_after[key] - kept_now

    best = 0.0
    for direction in (-1, 1):
        # Each move goes where the hero's moves go: a cell at a time, or for the Shadow, a dash to the last free one.
        cell = state.hero.cell
        for steps in range(1, len(fractions)):
            cell = move_destination(state, cell, direction)
            if cell is None:
                break
            for flip in (False, True):
                actions = steps + flip
                if actions >= len(fractions):
                    continue
                for tiles in volleys:
                    best = max(best, gain(tiles, cell, flip) * fractions[actions])
    # Staying put is covered above only for an occupied-free start, which the hero's own cell isn't.
    for flip in (False, True):
        for tiles in volleys:
            best = max(best, gain(tiles, None, flip) * fractions[int(flip)])
    return best


def _hit_value(enemy, damage):
    value = min(damage, enemy.hp) * WEIGHTS["enemy_damage"]
    return value + WEIGHTS["kill"] if damage >= enemy.hp else value


def _curse_value(state):
    """What the curses on enemies are worth: a fraction of how much better each makes the next hit there.

    That's the most the curse adds to any one tile's hit, with a discount for each turn until the tile is ready,
    capped by the enemy's health, so it's worth most where it turns a wound into a kill. Every tile counts, loaded
    or not, and taking the best tile's gain means another tile can only add (rule 1). Comparing the best hit with
    the curse against the best without it didn't: a tile that kills anyway made the curse look worthless. A volley
    that would use the curse is scored on the board it leaves, where the curse is gone.
    """
    total = 0.0
    for enemy in state.enemies:
        if not enemy.alive or not enemy.curse or is_tank(state, enemy):
            continue
        best = 0.0
        for tile in state.tiles:
            value = tile.attack.value
            discount = WEIGHTS["future_discount"] ** max(0, tile.cooldown - tile.charge)
            best = max(best, (_hit_value(enemy, value * 2) - _hit_value(enemy, value)) * discount)
        total += best
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
                best = min(best, _threat_damage(state, move_destination(state, hero.cell, direction)))
            elif can_use_special(state, direction):
                best = min(best, _threat_after_special(state, direction))
    for tiles in _volleys(state):
        trial, _ = _preview_fire(state, [t.attack for t in tiles])
        trial.enemies = [e for e in trial.enemies if e.alive]
        best = min(best, _threat_damage(trial, trial.hero.cell))
    return best


def ideal_target(state):
    """The enemy to focus: the quickest kill, then the closest. Only uses what's on the board."""
    enemies = [e for e in state.enemies if e.alive]
    if not enemies:
        return None
    enemies = [e for e in enemies if not is_tank(state, e)] or enemies
    # Nobunaga off a spotlit cell can't be hurt, so another enemy comes first.
    return min(enemies, key=lambda e: (armored(state, e), _effective_hp(state, e), abs(e.cell - state.hero.cell)))


# Actions looked ahead for reach: as many as leave anything after the falloff for each (3 at a quarter off each).
REACH_ACTIONS = math.ceil(1 / WEIGHTS["reach_falloff"]) - 1


def _walk(state, start, budget):
    """Cells the hero can get to from `start` with plain moves, and the fewest moves each takes, up to `budget`."""
    occupied = {e.cell for e in state.enemies if e.alive}
    costs = {start: 0}
    frontier = [start]
    for cost in range(1, budget + 1):
        reached = []
        for cell in frontier:
            for direction in (-1, 1):
                nxt = move_destination(state, cell, direction, occupied)
                if nxt is not None and nxt not in costs:
                    costs[nxt] = cost
                    reached.append(nxt)
        frontier = reached
    return costs


_REACH_CACHE = {}


def _reach_key(state, target, transport):
    hero = state.hero
    if transport is None or transport == "special":
        used = transport
    else:
        used = (transport.attack.name, transport.attack.value, tuple(transport.attack.range), transport.attack.effect,
                transport.in_queue, transport.free_play)
    return (state.cells, hero.kind, hero.cell, hero.facing, state.special, state.swap_charge >= state.swap_cooldown,
            state.two_way_swap, state.swap_damage, state.enemies.index(target), used,
            tuple((e.kind, e.cell, e.facing, e.hp, e.alive, e.shield, e.movable) for e in state.enemies))


def _reach_nodes(state, target, transport=None):
    """Where the hero and the target can be after a few of the hero's actions, with the fewest it takes: plain
    moves, as the hero really moves (blocked by whoever is in the way, and for the Shadow, a dash), and at most one
    use of `transport` if given ("special" for the special move, or a tile), from any cell plain moves reach, after
    a flip if need be. Enemies stay put, as in the stack. A tile in hand takes a turn to load first."""
    key = _reach_key(state, target, transport)
    if key in _REACH_CACHE:
        return _REACH_CACHE[key]
    index = state.enemies.index(target)
    best = {}

    def record(board, start_cost):
        aimed = board.enemies[index]
        if not aimed.alive:
            return
        for cell, cost in _walk(board, board.hero.cell, REACH_ACTIONS - start_cost).items():
            pair = (cell, aimed.cell)
            best[pair] = min(best.get(pair, cost + start_cost), cost + start_cost)

    record(state, 0)
    if transport is not None:
        load = 1 if transport == "special" or transport.in_queue or transport.free_play else 2
        for cell, cost in _walk(state, state.hero.cell, REACH_ACTIONS - load).items():
            for flip in (False, True):
                if cost + flip + load > REACH_ACTIONS:
                    continue
                for direction in ((-1, 1) if transport == "special" else (None,)):
                    board = _light_copy(state)
                    board.hero.cell = cell
                    if flip:
                        board.hero.facing = -board.hero.facing
                    if direction is None:
                        apply_attack(board, board.hero, transport.attack, Outcome())
                    elif can_use_special(board, direction):
                        perform_special(board, direction, Outcome())
                    else:
                        continue
                    record(board, cost + flip + load)
    if len(_REACH_CACHE) > 200_000:
        _REACH_CACHE.clear()
    _REACH_CACHE[key] = best
    return best


def _reach_total(state, target, nodes, exclude=None):
    """Each tile's best damage on the target from any of these positions, up to its HP, a quarter off for each
    action it took to get there and discounted for each turn until the tile is ready."""
    hp = _effective_hp(state, target)
    total = 0.0
    for tile in state.tiles:
        if tile.attack.value <= 0 or tile is exclude:
            continue
        reaches = set(map(abs, tile.attack.range))
        best = 0.0
        for (hero_cell, target_cell), cost in nodes.items():
            reach = abs(target_cell - hero_cell)
            if reach not in reaches:
                continue
            damage = tile.attack.value + (state.sniper_bonus if reach >= SNIPER_DISTANCE else 0)
            closeness = max(0.0, 1.0 - WEIGHTS["reach_falloff"] * cost)
            best = max(best, min(damage, hp) * closeness * WEIGHTS["pierce"].get(tile.attack.name, 1.0))
        waiting = 0 if tile.in_queue else max(0, tile.cooldown - tile.charge)
        total += best * WEIGHTS["future_discount"] ** waiting
    return total


def _reach_value(state, target):
    """Credit for each tile that can reach the target, from where the hero stands or after a few plain moves (rule
    3: only credit). Moves are walked as the hero really moves, so blockers and the Shadow's dash count. What the
    special move and movement tiles add is theirs, in `_kept_moves`, as one of their uses (rule 2).

    Each tile only adds, and more charge adds more, so having a tile never lowers it (rule 1).
    """
    if armored(state, target):
        return 0.0  # Nothing reaches him through his armor.
    return WEIGHTS["reach"] * _reach_total(state, target, _reach_nodes(state, target))


def _reach_gain(state, transport):
    """The reach credit one use of a movement ability adds on the way, beyond plain moves: another use of that
    ability, alongside its escape and setup values. Its own damage isn't counted, since using it to get there
    spends it."""
    target = ideal_target(state)
    if target is None or armored(state, target):
        return 0.0
    exclude = transport if isinstance(transport, Tile) else None
    base = _reach_total(state, target, _reach_nodes(state, target), exclude)
    moved = _reach_total(state, target, _reach_nodes(state, target, transport), exclude)
    return WEIGHTS["reach"] * max(0.0, moved - base)


def _swap_charged(state):
    """A charged Swap is a way out, whoever is around. It needs nobody adjacent yet, since closing in is what
    brings enemies next to the hero, and requiring it had F1 walk up to them just so the way out would count.
    Nor does it need anyone swappable now: that made killing the last one look bad, though more will come."""
    return state.special in (SWAP, PHASE) and state.swap_charge >= state.swap_cooldown


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

    beside = [e for e in state.enemies if e.alive and not is_tank(state, e) and abs(e.cell - hero.cell) == 1]
    return {
        "facing": facing,
        "reach": _reach_value(state, target),
        "stand_off": WEIGHTS["stand_off"] * len(beside),
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


def _kept_moves(state):
    """Repositioning moves kept, of the hero or of others, as escape and setup values.

    Escape: each move is a way out of trouble later, worth what `escape_values` guesses from its flexibility:
    whether it gets the hero past an enemy, away, or only moves the enemy, and in how many situations it works.
    Spending one for its damage alone gives that up for several turns. A special move that can go backward covers
    both sides, so it's worth more. A loaded tile can be used this turn and one in hand can't, so loading one adds a
    little. A move that acts on a target is worth little with nobody it can act on. Firing tiles never spends a
    special move.

    Setup: a move that brings an enemy in is worth more when the kit has a short-reach tile to exploit it, in
    proportion to that tile's damage, charged or not.

    One tile, one use (rule 2): a tile counts the larger of its escape and setup values, not both. Having several
    helps, but each beyond the best counts for only part of its value. Whether the loaded tiles are about to fire
    is the stack's to weigh: it scores a volley by the board it leaves, without these.
    """
    escape_values, setup_values = WEIGHTS["escape_values"], WEIGHTS["setup_values"]
    exploit = max((t.attack.value for t in state.tiles if t.attack.value > 0 and t.attack.name not in setup_values
                   and t.attack.range and max(map(abs, t.attack.range)) <= WEIGHTS["short_reach"]), default=0)
    kept = []
    for tile in state.tiles:
        name = tile.attack.name
        if not tile.ready or (name not in escape_values and name not in setup_values):
            continue
        uses = [(escape_values.get(name, 0.0), "escape"), (exploit * setup_values.get(name, 0.0), "setup")]
        value, term = max(uses)
        if not tile.in_queue:
            value *= WEIGHTS["escape_in_hand"]
        if name in _MOVES_TARGET and not any(a.movable for a in targets_of(state, state.hero, tile.attack)[:1]):
            value *= WEIGHTS["escape_no_target"]
        # Its reach gain already pays for loading it, in the actions it counts.
        kept.append(max((value, term), (_reach_gain(state, tile), "move_reach")))
    if state.special in escape_values and state.swap_charge >= state.swap_cooldown:
        escape = escape_values[state.special] * (WEIGHTS["escape_two_way"] if state.two_way_swap else 1.0)
        kept.append(max((escape, "escape"), (_reach_gain(state, "special"), "move_reach")))
    kept.sort(reverse=True)
    terms = {"escape": 0.0, "setup": 0.0, "move_reach": 0.0}
    for rank, (value, term) in enumerate(kept):
        terms[term] += value if rank == 0 else WEIGHTS["escape_others"] * value
    return terms


def _trap_value(state):
    """Traps on the ground. Only enemies set them off, so each is worth part of its damage, for the chance one
    walks or is pulled onto it. Once it goes off it's gone, and the damage itself counts."""
    return WEIGHTS["trap_planted"] * WEIGHTS["enemy_damage"] * sum(t["damage"] for t in state.traps)


def _ice_value(state):
    """Frozen enemies, doing nothing: each worth a share of killing it, by the ice it has left. The turn it's frozen
    on is already played out by the simulation, so a fresh freeze shows ICE_TURNS - 1 turns left, and counts in
    full. Nothing on one that dies, since the kill then counts instead."""
    total = 0.0
    for enemy in state.enemies:
        if not enemy.alive or enemy.ice <= 0 or is_tank(state, enemy):
            continue
        kill = WEIGHTS["kill"] + WEIGHTS["enemy_damage"] * enemy.hp
        total += WEIGHTS["ice_vs_kill"] * kill * min(1.0, enemy.ice / (ICE_TURNS - 1))
    return total


def _wound_value(state):
    """Wounded enemies, with Scar Strike in the deck, which hits every enemy below full health wherever it is: each is
    worth a share of its damage there, up to the enemy's HP. Its cooldown is short enough that it's relevant either way,
    and a kill it would make shows in the stack, as the player put it, so neither changes this. It reads the deck, not
    readiness, so it keeps rules 1 and 3, and an enemy it hits stays wounded for the next one."""
    scar = max((t.attack.value for t in state.tiles if t.attack.name == "ScarStrike"), default=0)
    if not scar:
        return 0.0
    wounded = [e for e in state.enemies if e.alive and e.hp < e.max_hp and not is_tank(state, e)
               and e.kind != "TwinSideBoss"]
    return WEIGHTS["wound"] * WEIGHTS["enemy_damage"] * sum(min(scar, e.hp) for e in wounded)


def _poison_value(state):
    """Poison still to come: good on an enemy, as far as its HP goes, and bad on the hero."""
    value = sum(min(e.poison, e.hp) * WEIGHTS["poison_turn"] for e in state.enemies
                if e.alive and e.kind != "TwinSideBoss" and not is_tank(state, e))
    return value + state.hero.poison * WEIGHTS["hp_lost"]


def _shield_value(state):
    """A shield blocks the next hit. With Reactive Shield, the next damage brings one anyway, so going without is
    only half as bad: hits alternate between blocked and taken either way, and holding one now saves a hit only
    when an odd number are left. So an unshielded hero with the skill holds half a shield's worth, and a hit costs
    its HP less half a shield, never nothing."""
    if state.hero.shield:
        return WEIGHTS["shield"]
    return WEIGHTS["shield"] / 2 if state.reactive_shield else 0.0


def _kept_terms(state):
    """Every part of a position's score except the stack: what it's worth with every tile kept."""
    terms = {
        "poison": _poison_value(state),
        "traps": _trap_value(state),
        "ice": _ice_value(state),
        **_kept_moves(state),
        "effects": sum(WEIGHTS["loaded_effects"].get(t.attack.effect, 0.0) for t in state.queue_tiles),
        "curse": _curse_value(state),
        "wounds": _wound_value(state),
        "shield": _shield_value(state),
        "ready_tiles": WEIGHTS["ready_tile"] * sum(t.ready for t in state.tiles),
        # An attack can only fire what the queue holds, so anything beyond that adds nothing.
        "loaded": sum(sorted((_loaded_worth(a.name, a.value) for a in fireable_attacks(state)), reverse=True)[:QUEUE_CAP]),
        "swap_ready": WEIGHTS["swap_ready"] if state.swap_charge >= state.swap_cooldown else 0.0,
    }
    terms.update(_position_terms(state))
    terms.update(_pressure_terms(state))
    return terms


def leaf_terms(state: State) -> dict[str, float]:
    """Scores a position by itself, as named parts so a decision can be explained."""
    terms = _kept_terms(state)
    terms["stack"] = _stack_value(state, sum(terms.values()))
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
        "reload": _reload_value(outcome),
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
    # Ending the fight now, at no HP cost, beats anything. Only for the turn being chosen: a win later in a line, or
    # one a stack could make next turn, counts for what it does, like any other kill.
    if scale == 1.0 and fight_won(next_state) and outcome.hp_lost == 0:
        _merge(terms, {"win": WEIGHTS["win"]})
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
    wasted = action.kind == "Attack" and outcome.wasted_attacks > 0
    return Line(actions, sum(terms.values()), labels, terms, position, wasted)


def _best_line(state, depth, scale):
    lines = [_evaluate_action(state, a, depth, scale) for a in legal_actions(state)]
    return max((line for line in lines if not line.wasted), key=lambda line: line.sort_key)


# In order of preference when they save as much. Cool Up recharges the special move and escape tiles, so it can avoid
# a hit too, as the player pointed out, and it comes first: it only helps in narrow situations, so when it does save
# as much, the others are worth keeping for when it can't.
DEFENSIVE_POTIONS = ("CoolUp", "Shield", "MassIce", "RainOfMirrors")
ATTACKING_POTIONS = ("MassPoison", "MassCurse", "CoolUp")


def _turn_result(state, line):
    """What this turn does if the line's first action is taken."""
    return step(state, line.actions[0])[1]


def potion_plan(state, ranked):
    """Which potion to use before this turn's action, if any, and why: the player's rules.

    Edamame heals once that wastes none of it. Shield, Freeze Time, Rain of Mirrors and Cool Up avoid damage: used
    when the best line with one loses less HP this turn than the best line without, preferring Cool Up, then the
    Shield, unless another saves more. Mass Poison, Mass Curse and Cool Up only with every potion slot full, so one
    held back would crowd out the next one found, and only if the best line with one kills more this turn, poison
    ticks included. D6 is random, so it's the last resort against damage no other potion avoids, whenever that comes,
    as the player put it. Until v1.28 these were used under pressure, below a best score set from the logs, which every scoring
    change moved, so the player dropped it. Each potion is ranked in full, since one can make a move good that F1 ranked low without it.
    Returns (potion, reason, ranked with it), or (None, None, None).
    """
    held = state.potions
    if not held:
        return None, None, None
    hero = state.hero
    if "Edamame" in held and hero.max_hp - hero.hp >= WEIGHTS["heal_at_missing"]:
        return "Edamame", f"heal: HP {hero.hp}/{hero.max_hp}", None
    best = ranked[0]
    now = _turn_result(state, best)
    # With every slot full, a potion held back only crowds out the next one found, so any that helps is used.
    full = len(held) >= state.potion_slots
    why = f"every potion slot full ({len(held)}/{state.potion_slots})"

    def with_potion(name):
        after = apply_potion(state, name)
        again = rank_actions(after, depth=1)
        return after, again, _turn_result(after, again[0])

    if now.hp_lost > 0:
        saves = []
        for name in DEFENSIVE_POTIONS:
            if name in held:
                after, again, result = with_potion(name)
                if result.hp_lost < now.hp_lost:
                    saves.append((result.hp_lost, DEFENSIVE_POTIONS.index(name), name, again))
        if saves:
            hp, _, name, again = min(saves)
            return name, f"avoids damage: {now.hp_lost} HP lost without it, {hp} with it", again
    if full:
        gains = []
        for name in ATTACKING_POTIONS:
            if name in held:
                after, again, result = with_potion(name)
                if result.kills > now.kills:
                    gains.append((result.kills, again[0].score, name, again))
        if gains:
            kills, _, name, again = max(gains, key=lambda g: (g[0], g[1]))
            return name, f"{why}: {now.kills} kills without it, {kills} with it", again
    # The last resort against a hit: D6 is random, so it's used only once no other potion avoids the damage. A potion
    # used above leaves the next key press to look again, D6 included.
    if now.hp_lost > 0 and "D6" in held:
        return "D6", f"losing {now.hp_lost} HP that nothing else avoids", None
    return None, None, None


def rank_actions(state: State, depth: int = 1) -> list[Line]:
    """Every action available now, best first, each with the best continuation found for it."""
    lines = [_evaluate_action(state, action, depth, 1.0) for action in legal_actions(state)]
    lines = [line for line in lines if not line.wasted]
    lines.sort(key=lambda line: line.sort_key, reverse=True)
    return lines
