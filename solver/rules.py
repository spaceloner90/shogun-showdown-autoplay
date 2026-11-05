"""Simulates one combat turn of the first battle. See research/rules.md for the rules.

Only uses what a player can see: enemies do what they telegraphed this turn, and after that their
actions are unknown, so they're treated as waiting. New enemies and wave spawns aren't predicted.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

QUEUE_CAP = 3
ONE_ENEMY_WAVE_CAP = 6

# Attacks that hit only the first agent in range. Anything else in MODELED hits everyone in range.
SINGLE_TARGET = {"Arrow", "Katana"}
MODELED = {"Arrow", "Katana", "Swirl"}

# An enemy tile being played. Its identity isn't visible until it lands in the queue.
UNKNOWN_TILE = "Unknown"


@dataclass
class Attack:
    name: str
    value: int
    range: list[int]


@dataclass
class Tile:
    attack: Attack
    cooldown: int
    charge: int
    in_queue: bool = False
    just_played: bool = False

    @property
    def ready(self):
        return self.charge >= self.cooldown


@dataclass
class Agent:
    kind: str
    cell: int
    facing: int  # +1 is right, -1 is left
    hp: int
    max_hp: int
    shield: bool = False
    queue: list[Attack] = field(default_factory=list)
    action: str = "Wait"  # Only meaningful for enemies.
    moved: bool = False

    @property
    def alive(self):
        return self.hp > 0

    @property
    def move_dir(self):
        return {"MoveLeft": -1, "MoveRight": 1}.get(self.action, 0)


@dataclass
class State:
    cells: int
    hero: Agent
    enemies: list[Agent]
    tiles: list[Tile]  # Queue order is kept in hero.queue, by Tile identity in queue_tiles.
    queue_tiles: list[Tile]
    swap_charge: int
    swap_cooldown: int
    turns_until_wave: int | None = None
    last_wave: bool = False

    def occupant(self, cell):
        if self.hero.alive and self.hero.cell == cell:
            return self.hero
        for enemy in self.enemies:
            if enemy.alive and enemy.cell == cell:
                return enemy
        return None


@dataclass
class Outcome:
    """What one simulated turn did."""
    hp_lost: int = 0
    enemy_damage: int = 0
    kills: int = 0
    friendly_damage: int = 0
    wasted_attacks: int = 0
    unmodeled: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Action:
    kind: str  # Wait, MoveLeft, MoveRight, Flip, Attack or PlayTile
    tile: int | None = None  # Index into state.tiles for PlayTile.

    def label(self, state):
        return f"PlayTile {state.tiles[self.tile].attack.name}" if self.kind == "PlayTile" else self.kind


def state_from_log(row):
    """Builds a State from a 'state' line of state.jsonl."""
    def attack(data):
        return Attack(data["name"], data["value"] or 0, list(data["range"]))

    def agent(data):
        return Agent(
            kind=data["kind"],
            cell=data["cell"],
            facing=-1 if data["facing"] == "Left" else 1,
            hp=data["hp"],
            max_hp=data["maxHp"],
            shield=data["shield"],
            queue=[attack(a) for a in data["queue"]],
            action=data["action"],
        )

    tiles = [
        Tile(
            attack=attack(t["attack"]),
            cooldown=t["attack"]["cooldown"],
            charge=t["attack"]["cooldown"] - t["turnsBeforeCharged"],
            in_queue="AttackQueue" in t["where"],
        )
        for t in row["tiles"]
    ]
    hero = agent(row["hero"])
    hero.action = "Wait"

    # The log gives the queue's order by attack. Match each entry to a tile in the queue.
    available = [t for t in tiles if t.in_queue]
    queue_tiles = []
    for queued in hero.queue:
        match = next(t for t in available if t.attack.name == queued.name)
        available.remove(match)
        queue_tiles.append(match)

    special = row["hero"].get("special") or {}
    wave = row.get("wave")
    return State(
        cells=row["cells"],
        hero=hero,
        enemies=[agent(e) for e in row["enemies"]],
        tiles=tiles,
        queue_tiles=queue_tiles,
        swap_charge=special.get("charge", 0),
        swap_cooldown=special.get("cooldown", 4),
        turns_until_wave=wave["turnsUntilNext"] if wave else None,
        last_wave=wave["isLast"] if wave else False,
    )


def can_swap(state, direction):
    """Swap only works in the facing direction, when charged, into an occupied cell."""
    return (
        direction == state.hero.facing
        and state.swap_charge >= state.swap_cooldown
        and state.occupant(state.hero.cell + direction) is not None
    )


def legal_actions(state, allow_swap=False):
    """The actions to consider. Swap is off for v0 because no fight log has shown it working yet."""
    hero = state.hero
    actions = [Action("Wait"), Action("Flip")]
    for kind, direction in (("MoveLeft", -1), ("MoveRight", 1)):
        target = hero.cell + direction
        if not 0 <= target < state.cells:
            continue
        if state.occupant(target) is None or (allow_swap and can_swap(state, direction)):
            actions.append(Action(kind))
    if len(hero.queue) < QUEUE_CAP:
        for index, tile in enumerate(state.tiles):
            if tile.ready and not tile.in_queue:
                actions.append(Action("PlayTile", index))
    if hero.queue:
        actions.append(Action("Attack"))
    return actions


def targets_of(state, attacker, attack):
    """The agents an attack hits right now, nearest first in range order."""
    hits = []
    for offset in attack.range:
        agent = state.occupant(attacker.cell + attacker.facing * offset)
        if agent is not None:
            hits.append(agent)
            if attack.name in SINGLE_TARGET:
                break
    return hits


def apply_attack(state, attacker, attack, outcome):
    if attack.name == UNKNOWN_TILE:
        return
    if attack.name not in MODELED and attack.name not in outcome.unmodeled:
        outcome.unmodeled.append(attack.name)
    hits = targets_of(state, attacker, attack)
    if not hits and attacker is state.hero:
        outcome.wasted_attacks += 1
    for target in hits:
        if target.shield:
            target.shield = False
            continue
        damage = min(attack.value, target.hp)
        target.hp -= damage
        if target is state.hero:
            outcome.hp_lost += damage
        elif attacker is state.hero:
            outcome.enemy_damage += damage
            if not target.alive:
                outcome.kills += 1
        else:
            # An enemy hitting an ally still removes HP from the room.
            outcome.friendly_damage += damage
            if not target.alive:
                outcome.kills += 1


def fire_hero_queue(state, outcome):
    for attack, tile in zip(state.hero.queue, state.queue_tiles):
        apply_attack(state, state.hero, attack, outcome)
        tile.charge = 0
        tile.just_played = True
        tile.in_queue = False
    state.hero.queue = []
    state.queue_tiles = []


def hero_action(state, action, outcome):
    hero = state.hero
    swapped = False
    if action.kind == "Attack":
        fire_hero_queue(state, outcome)
    elif action.kind == "Flip":
        hero.facing = -hero.facing
    elif action.kind == "PlayTile":
        tile = state.tiles[action.tile]
        tile.in_queue = True
        hero.queue.append(tile.attack)
        state.queue_tiles.append(tile)
    elif action.kind in ("MoveLeft", "MoveRight"):
        direction = -1 if action.kind == "MoveLeft" else 1
        target = hero.cell + direction
        occupant = state.occupant(target)
        if occupant is not None:
            occupant.cell = hero.cell
            swapped = True
            state.swap_charge = 0
        hero.cell = target
    return swapped


def enemy_move(state, enemy):
    """Moves an enemy one cell, also moving an enemy ahead that's about to go the same way."""
    if enemy.moved:
        return
    direction = enemy.move_dir
    target = enemy.cell + direction
    enemy.moved = True
    if not 0 <= target < state.cells:
        return
    occupant = state.occupant(target)
    if occupant is None:
        enemy.cell = target
    elif (
        occupant is not state.hero
        and not occupant.moved
        and occupant.move_dir == direction
        and 0 <= target + direction < state.cells
        and state.occupant(target + direction) is None
    ):
        enemy_move(state, occupant)
        if state.occupant(target) is None:
            enemy.cell = target


def resolve_enemies(state, outcome):
    # The game acts in the order it sorted at the end of last turn, even if a Swap has since
    # changed who is further left. state.enemies is already in that order.
    enemies = list(state.enemies)
    for enemy in enemies:
        if not enemy.alive:
            continue
        if enemy.action == "FlipLeft":
            enemy.facing = -1
        elif enemy.action == "FlipRight":
            enemy.facing = 1
        elif enemy.move_dir:
            enemy_move(state, enemy)
    for enemy in enemies:
        if enemy.alive and enemy.action == "Attack" and state.hero.alive:
            for attack in list(enemy.queue):
                if enemy.alive:
                    apply_attack(state, enemy, attack, outcome)
            enemy.queue = []
    for enemy in enemies:
        if enemy.alive and enemy.action == "PlayTile":
            enemy.queue.append(Attack(UNKNOWN_TILE, 0, []))


def end_turn(state, swapped):
    for tile in state.tiles:
        if not tile.just_played and tile.charge < tile.cooldown:
            tile.charge += 1
        tile.just_played = False
    if not swapped and state.swap_charge < state.swap_cooldown:
        state.swap_charge += 1
    state.enemies = sorted((e for e in state.enemies if e.alive), key=lambda e: e.cell)
    if state.turns_until_wave is not None:
        if len(state.enemies) == 1:
            state.turns_until_wave = min(state.turns_until_wave, ONE_ENEMY_WAVE_CAP)
        state.turns_until_wave -= 1
    for enemy in state.enemies:
        enemy.moved = False
        enemy.action = "Wait"  # What it does next isn't known until the game shows it.


def step(state, action):
    """Returns the state after one full turn, and what happened. The input isn't changed."""
    next_state = copy.deepcopy(state)
    outcome = Outcome()
    swapped = hero_action(next_state, action, outcome)
    resolve_enemies(next_state, outcome)
    end_turn(next_state, swapped)
    return next_state, outcome
