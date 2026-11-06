"""Simulates one combat turn. See research/rules.md for the rules.

Only uses what a player can see: enemies do what they telegraphed this turn, and after that their
actions are unknown, so they're treated as waiting. New enemies and wave spawns aren't predicted.
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field

QUEUE_CAP = 3
ONE_ENEMY_WAVE_CAP = 6

# Attacks whose behaviour is fully covered by their logged range, damage and first-target flag, plus
# the dashes below. Anything else may do more than the simulator knows, and gets a warning.
MODELED = {"Arrow", "BackCharge", "BackShadowDash", "Charge", "Dash", "EarthImpale", "Katana", "ShadowDash",
           "Spear", "Swirl", "Tetsubo"}

# Attacks that move the attacker. Each value is the direction relative to the attacker's facing.
CHARGES = {"Charge": 1, "BackCharge": -1}  # Run to the last free cell, and hit whatever is next.
PLAIN_DASHES = {"Dash": 1}                 # Run to the last free cell, and hit nothing.
SHADOW_DASHES = {"ShadowDash": 1, "BackShadowDash": -1}  # Land behind a target, hitting all they pass.

# An enemy tile being played. Its identity isn't visible until it lands in the queue.
UNKNOWN_TILE = "Unknown"


@dataclass
class Attack:
    name: str
    value: int
    range: list[int]
    first_target: bool = False  # Stops at the first agent in range, rather than hitting them all.
    effect: str = "None"  # Applied to whoever it hits and doesn't kill. Only Curse is modeled.


@dataclass
class Tile:
    attack: Attack
    cooldown: int
    charge: int
    in_queue: bool = False
    just_played: bool = False
    free_play: bool = False  # Loading this tile doesn't use the turn, so it can join any attack.

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
    curse: bool = False  # The next hit that deals damage is doubled, and uses up the curse.

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
    sent_back: int = 0  # Queued tiles returned to hand instead of firing. Each costs a turn to reload.
    unmodeled: list[str] = field(default_factory=list)


def _tile_name(state, tile):
    """A tile's name, with its damage added when the deck has another of that name that hits differently."""
    name = tile.attack.name
    if any(t is not tile and t.attack.name == name and t.attack.value != tile.attack.value for t in state.tiles):
        return f"{name} ({tile.attack.value})"
    return name


@dataclass(frozen=True)
class Action:
    kind: str  # Wait, MoveLeft, MoveRight, Flip, Attack or PlayTile
    tile: int | None = None  # Index into state.tiles for PlayTile.
    # For Attack: which tiles to fire and in what order, as indexes into state.tiles. Queue edits and
    # Free Play tiles from hand cost nothing, so they happen as part of the attack. None fires the
    # whole queue as it stands.
    order: tuple[int, ...] | None = None

    def label(self, state):
        if self.kind == "PlayTile":
            return f"PlayTile {_tile_name(state, state.tiles[self.tile])}"
        if self.kind == "Attack" and self.order is not None:
            fired = [state.tiles[i] for i in self.order]
            kept = [_tile_name(state, t) for t in state.queue_tiles if not any(t is f for f in fired)]
            text = "Attack " + " > ".join(
                _tile_name(state, t) + ("" if t.in_queue else " (free)") for t in fired)
            return f"{text} ({', '.join(kept)} to hand)" if kept else text
        if self.kind in ("MoveLeft", "MoveRight"):
            direction = -1 if self.kind == "MoveLeft" else 1
            if state.occupant(state.hero.cell + direction) is not None:
                return f"{self.kind} (swap)"
        return self.kind


def state_from_log(row):
    """Builds a State from a 'state' line of state.jsonl."""
    def attack(data):
        return Attack(data["name"], data["value"] or 0, list(data["range"]), bool(data["closestTargetOnly"]),
                      data.get("effect") or "None")

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
            curse=bool(data.get("curse")),
        )

    tiles = [
        Tile(
            attack=attack(t["attack"]),
            cooldown=t["attack"]["cooldown"],
            charge=t["attack"]["cooldown"] - t["turnsBeforeCharged"],
            in_queue="AttackQueue" in t["where"],
            free_play=t["attack"].get("tileEffect") == "FreePlay",
        )
        for t in row["tiles"]
    ]
    hero = agent(row["hero"])
    hero.action = "Wait"

    # The log gives the queue's order by attack. Match each entry to a tile in the queue. The deck can
    # hold two tiles of the same name, so match on damage as well when possible.
    available = [t for t in tiles if t.in_queue]
    queue_tiles = []
    for queued in hero.queue:
        same_name = [t for t in available if t.attack.name == queued.name]
        match = next((t for t in same_name if t.attack.value == queued.value), same_name[0] if same_name else None)
        if match is None:
            # Queued, but not from the deck the log shows. Track it anyway, so firing still works.
            match = Tile(queued, cooldown=0, charge=0, in_queue=True)
            tiles.append(match)
        else:
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


def unmodeled_content(row):
    """Everything in this position the simulator doesn't fully understand, for the report's warnings."""
    notes = []

    def note(text):
        if text not in notes:
            notes.append(text)

    def check_attack(data):
        if data["name"] not in MODELED and data["name"] != UNKNOWN_TILE:
            note(f"attack {data['name']}")
        if data.get("effect") not in (None, "None", "Curse"):
            note(f"{data['name']} effect {data['effect']}")
        if data.get("tileEffect") not in (None, "None", "FreePlay"):
            note(f"{data['name']} tile effect {data['tileEffect']}")
        if data.get("nonLethal"):
            note(f"{data['name']} is non-lethal")

    def check_status(name, agent):
        for status in ("poison", "ice"):
            if agent.get(status):
                note(f"{name} {status}")

    for tile in row["tiles"]:
        check_attack(tile["attack"])
    hero = row["hero"]
    for data in hero["queue"]:
        check_attack(data)
    check_status("hero", hero)
    for enemy in row["enemies"]:
        for data in enemy["queue"]:
            check_attack(data)
        check_status(enemy["kind"], enemy)
        if enemy.get("elite") not in (None, "None"):
            note(f"elite {enemy['kind']}")
        for trait in enemy.get("traits") or []:
            note(f"{enemy['kind']} trait {trait}")
    for skill in row.get("skills") or []:
        note(f"skill {skill.get('name', skill) if isinstance(skill, dict) else skill}")
    return notes


def can_swap(state, direction):
    """Swap only works in the facing direction, when charged, into an occupied cell."""
    return (
        direction == state.hero.facing
        and state.swap_charge >= state.swap_cooldown
        and state.occupant(state.hero.cell + direction) is not None
    )


def free_hand_tiles(state):
    """Tiles that can join an attack from hand at no cost."""
    return [t for t in state.tiles if t.free_play and t.ready and not t.in_queue]


def fireable_attacks(state):
    """Every attack the hero could fire next, without spending a turn on loading it."""
    return [t.attack for t in state.queue_tiles] + [t.attack for t in free_hand_tiles(state)]


def attack_actions(state):
    """Every way to attack: any queued or Free Play tiles, in any order, up to what the queue holds.

    The queue as it stands comes first, so that when choices score the same, the one needing no
    edits wins.
    """
    def index_of(tile):
        return next(i for i, t in enumerate(state.tiles) if t is tile)

    queued = tuple(index_of(t) for t in state.queue_tiles)
    pool = list(queued) + [index_of(t) for t in free_hand_tiles(state)]
    actions = [Action("Attack")] if queued else []
    for size in range(min(len(pool), QUEUE_CAP), 0, -1):
        for order in itertools.permutations(pool, size):
            if order != queued:
                actions.append(Action("Attack", order=order))
    return actions


def legal_actions(state, allow_swap=True):
    """The actions to consider."""
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
            # A Free Play tile is never worth loading ahead of time: it can join any attack instead.
            if tile.ready and not tile.in_queue and not tile.free_play:
                actions.append(Action("PlayTile", index))
    actions.extend(attack_actions(state))
    return actions


def targets_of(state, attacker, attack):
    """The agents an attack hits right now, nearest first in range order."""
    hits = []
    for offset in attack.range:
        agent = state.occupant(attacker.cell + attacker.facing * offset)
        if agent is not None:
            hits.append(agent)
            if attack.first_target:
                break
    return hits


def run_to_last_free_cell(state, attacker, direction):
    """Moves the attacker as far as it can go. Returns whatever is next, if anything."""
    cell = attacker.cell
    while 0 <= cell + direction < state.cells and state.occupant(cell + direction) is None:
        cell += direction
    attacker.cell = cell
    next_cell = cell + direction
    target = state.occupant(next_cell) if 0 <= next_cell < state.cells else None
    return [target] if target is not None else []


def shadow_dash(state, attacker, attack, direction):
    """Goes through targets at any distance, stopping at the first free cell behind one, hitting all it passed.

    Does nothing if nobody is in range, or if no target has a free cell behind it. The tile still goes
    on cooldown either way.
    """
    if not targets_of(state, attacker, attack):
        return []
    passed = []
    cell = attacker.cell + direction
    while 0 <= cell < state.cells:
        agent = state.occupant(cell)
        if agent is not None:
            passed.append(agent)
            behind = cell + direction
            if 0 <= behind < state.cells and state.occupant(behind) is None:
                attacker.cell = behind
                return passed
        cell += direction
    return []


def attack_hits(state, attacker, attack):
    """Who this attack hits, after moving the attacker if it's a moving attack."""
    if attack.name in CHARGES:
        return run_to_last_free_cell(state, attacker, attacker.facing * CHARGES[attack.name])
    if attack.name in PLAIN_DASHES:
        run_to_last_free_cell(state, attacker, attacker.facing * PLAIN_DASHES[attack.name])
        return []
    if attack.name in SHADOW_DASHES:
        return shadow_dash(state, attacker, attack, attacker.facing * SHADOW_DASHES[attack.name])
    return targets_of(state, attacker, attack)


def apply_attack(state, attacker, attack, outcome):
    if attack.name == UNKNOWN_TILE:
        return
    if attack.name not in MODELED and attack.name not in outcome.unmodeled:
        outcome.unmodeled.append(attack.name)
    hits = attack_hits(state, attacker, attack)
    # A plain dash is used for the move, so hitting nothing isn't a waste.
    if not hits and attacker is state.hero and attack.name not in PLAIN_DASHES:
        outcome.wasted_attacks += 1
    for target in hits:
        # A shield blocks the hit and leaves any curse in place, but the effect still lands.
        if target.shield:
            target.shield = False
        else:
            deal_damage(state, attacker, target, attack.value, outcome)
        # After the hit, so a curse never doubles the attack that applied it.
        if target.alive and attack.effect == "Curse":
            target.curse = True


def deal_damage(state, attacker, target, value, outcome):
    if target.curse and value > 0:
        value *= 2
        target.curse = False
    damage = min(value, target.hp)
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


def fire_hero_queue(state, outcome, order=None):
    """Fires the chosen tiles in order. Any others go back to the hand, still charged."""
    fired = list(state.queue_tiles) if order is None else [state.tiles[i] for i in order]
    for tile in fired:
        apply_attack(state, state.hero, tile.attack, outcome)
        tile.charge = 0
        tile.just_played = True
    outcome.sent_back += sum(not any(t is f for f in fired) for t in state.queue_tiles)
    for tile in state.queue_tiles:
        tile.in_queue = False
    state.hero.queue = []
    state.queue_tiles = []


def hero_action(state, action, outcome):
    hero = state.hero
    swapped = False
    if action.kind == "Attack":
        fire_hero_queue(state, outcome, action.order)
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
