"""Simulates one combat turn. See research/rules.md for the rules.

Only uses what a player can see: enemies do what they telegraphed this turn, and after that their
actions are unknown, so they're treated as waiting. New enemies and wave spawns aren't predicted.
"""
from __future__ import annotations

import copy
import dataclasses
import itertools
from dataclasses import dataclass, field

QUEUE_CAP = 3
ONE_ENEMY_WAVE_CAP = 6

# Attacks whose behaviour is fully covered by their logged range, damage and first-target flag, plus
# the dashes below. Anything else may do more than the simulator knows, and gets a warning.
MODELED = {"Arrow", "BackCharge", "BackShadowDash", "BackSmokeBomb", "Barricade", "BladeOfPatience", "Bomb",
           "BossSwap", "Charge", "Crossbow",
           "CopycatMirror", "CorruptedBarrage", "Curse", "Dash", "DragonPunch", "EarthImpale", "GrapplingHook", "Katana", "Lightning", "Maku", "Mirror", "OriginOfSymmetry", "Shield",
           "ShieldAllied", "ShadowDash", "ShadowKama", "Shuriken", "Sai", "ScarStrike", "SmokeBomb", "Spear", "Summon", "SwapToss",
           "Swirl", "Tetsubo", "Trap", "TurnAround", "Volley"}

# Skills the solver handles. Most need no modeling because their effects show up in the logged state,
# like a shield, max HP or a shorter Swap cooldown. Damaging Move, Dynamic Boost, Sniper, Two Way Move and Unfriendly Fire
# are simulated.
SNIPER_DISTANCE = 4  # Sniper adds its level to the hero's hits on targets at least this many cells away.
# Combo Curse curses a random enemy on each kill after the first in a turn, by anyone: which one can't be predicted,
# like where a summon lands, so it isn't simulated. Combo Coin and Triple Combo Heal also trigger on combos, and
# aren't simulated or valued either: the player's call is there's no reason to yet. So is Combo Recharge, which
# takes 4 a level off the cooldown of a tile making a kill after the first in a turn (ComboRechargeSkill.OnComboKill),
# and Chilling Combo, which freezes enemies on a combo kill. Reactive Shield is simulated. Shield Retention keeps the
# hero's shield from one fight to the next (ShieldRetentionSkill.PickUp), and Fortress shields it as a fight begins,
# both of which show in the logged state.
UNDERSTOOD_SKILLS = {"BigPockets", "ChillingCombo", "ComboCoin", "ComboCurse", "ComboRecharge", "DamagingMove", "DynamicBoost", "Fortress", "Healthy",
                     "QuickRecovery", "ReactiveShield", "ShieldRetention", "Sniper", "TripleComboHeal", "TwoWayMove",
                     "UnfriendlyFire"}

# A Crossbow alternates: loaded, it hits the first CROSSBOW_TARGETS agents in range and empties; empty, its use
# reloads it to its base damage, hitting nobody (CrossbowAttack.ApplyEffect, Attack, Reload). Its cooldown runs after
# either. Logs before mod 0.16.0 don't give an empty one's base damage, so it's taken as the starting 3.
CROSSBOW_TARGETS = 2
CROSSBOW_DAMAGE = 3
POISON_TURNS = 3  # Applying poison sets this many turns left, and each turn's end deals 1, starting that turn.
POTION_SLOTS = 3  # The most held in any log without Big Pockets, which adds one (BigPocketsSkill.PickUp).
ICE_TURNS = 4  # GameParams.iceEffectTurnsDuration: freezing sets this many turns of ice, counting down each turn's end.
BOMB_FUSE = 2     # Turns a placed bomb waits after the one it's placed on, before it goes off on the next.
BARRICADE_HP = 5
MAX_SHOVE_CREDIT = 3  # A shove counts for at most this many cells: further than that gains little.
SHOCKWAVE_DAMAGE = 1  # Stored in the game's assets, not its code. Seen in logs/run7.
WARDEN_EXPLOSION = 2  # What a dying Warden deals to its cell and both beside it. In the game's code.

# Each hero has one special move, triggered by moving into an occupied cell. Swap is the Wanderer's, Shove the
# Ronin's, Throw the Jujitsuka's and Phase the Shadow's. Any other isn't simulated, so it isn't offered as an action.
SWAP = "SwapSpecialMove"
SHOVE = "PushSpecialMove"
THROW = "ThrowSpecialMove"  # The Jujitsuka's: throws the enemy behind the hero over to the front.
PHASE = "PhaseSpecialMove"  # The Shadow's: passes through the line of agents ahead to the first free cell.
SPECIAL_MOVES = {SWAP, SHOVE, THROW, PHASE}
SPECIAL_LABELS = {SWAP: "swap", SHOVE: "shove", THROW: "throw", PHASE: "phase"}

# Enemy traits that need no warning. Heavy, Explosive (the Warden's) and Dash (the Strider's) are modeled, and the
# others haven't changed any prediction.
UNDERSTOOD_TRAITS = {"Aggro", "Dash", "Explosive", "Heavy", "Quick", "Unfreezable"}

# Elite types that need no warning. Heavy can't be pushed or pulled, Reactive Shield gains a shield when hit, and
# Double Strike gives its attacks the Double Strike effect: all simulated. Quick only changes the enemy's AI, how soon
# it chooses to attack, so what it telegraphs plays out as usual.
KNOWN_ELITES = ("Heavy", "ReactiveShield", "DoubleStrike", "Quick")

# Enemies whose move runs them to the last free cell that way, rather than one cell: StriderEnemy.Move and
# FumikoBoss.Move in the code. The Strider's Dash trait is shown for it.
LEAPERS = {"Strider", "FumikoBoss"}

# Not worth fighting while a boss is alive: it dies with the boss anyway. Decided one by one with the player:
# the Shogun's last statues, and Ieyasu's Swapper, which has 30 HP the game doesn't show against his 40, and
# whose swaps are simulated rather than removed. Other bosses' summons are real threats.
TANKS = {"ShogunSummoner", "Swapper"}

# Attacks that move the attacker. Each value is the direction relative to the attacker's facing.
CHARGES = {"Charge": 1, "BackCharge": -1}  # Run to the last free cell, and hit whatever is next.
PLAIN_DASHES = {"Dash": 1}                 # Run to the last free cell, and hit nothing.
SHADOW_DASHES = {"ShadowDash": 1, "BackShadowDash": -1}  # Land behind a target, hitting all they pass.
SMOKE_BOMBS = {"SmokeBomb", "BackSmokeBomb"}  # Trade places with the first target, then hit it.
# Attacks that move or turn the hero, which raise the game's move-attack event that Dynamic Boost listens for. Only
# when they actually moved or turned it: a Smoke Bomb with nobody to trade places with does nothing.
MOVE_ATTACKS = set(CHARGES) | set(PLAIN_DASHES) | set(SHADOW_DASHES) | SMOKE_BOMBS | {"TurnAround", "Mirror",
                                                                                     "OriginOfSymmetry"}

# An enemy tile being played. Its identity isn't visible until it lands in the queue.
UNKNOWN_TILE = "Unknown"
# A Copycat Mirror's copy of a hero tile, before it shows. Unlike a tile an enemy plays, which is usually its own
# short attack, the copy could be anything in the hero's hand, so no threat is assumed for it: F1 reacts once it
# shows, before the copier can fire it.
UNKNOWN_COPY = "UnknownCopy"


@dataclass
class Attack:
    name: str
    value: int
    range: list[int]
    first_target: bool = False  # Stops at the first agent in range, rather than hitting them all.
    effect: str = "None"  # Curse, Poison, Perfect Strike and Shockwave are modeled.
    target_cell: int | None = None  # For a Volley: the cell it's locked onto, shown as a warning in the game.


@dataclass
class Tile:
    attack: Attack
    cooldown: int
    charge: int
    in_queue: bool = False
    just_played: bool = False
    free_play: bool = False  # Loading this tile doesn't use the turn, so it can join any attack.
    base_value: int | None = None  # What a Crossbow's reload restores: its damage when loaded.

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
    movable: bool = True  # Heavy enemies can't be swapped or pulled.
    poison: int = 0  # Turns of poison left. Each deals 1 at the end of the turn, and a shield blocks it.
    ice: int = 0  # Turns of being frozen left. A frozen enemy doesn't act.
    freezable: bool = True  # Unfreezable enemies can't be frozen.
    inanimate: bool = False  # An object rather than a fighter, such as a Barricade. The game doesn't count it as a kill.
    elite: str = "None"  # The game's elite type. Heavy, Reactive Shield and Double Strike change the rules.

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
    swap_charge: int  # The charge and cooldown of the hero's special move, whichever that is.
    swap_cooldown: int
    turns_until_wave: int | None = None
    last_wave: bool = False
    swap_damage: int = 0  # What a swap deals to the enemy passed through, from Damaging Move.
    friendly_bonus: int = 0  # Extra damage when enemies hit each other, from Unfriendly Fire.
    sniper_bonus: int = 0  # Extra damage on the hero's hits from 4 or more cells away, from Sniper.
    dynamic_bonus: int = 0  # Extra damage on the hero's hits after a move attack this turn, from Dynamic Boost.
    boosted: bool = False  # Whether a move attack has turned Dynamic Boost on this turn.
    reactive_shield: bool = False  # Reactive Shield: taking damage shields the hero.
    two_way_swap: bool = False  # The special move works backward as well, from Two Way Move.
    special: str = SWAP  # The hero's special move.
    # Damage on its way to marked cells: each is {"damage", "groups"}, and the first group of cells strikes
    # this turn. An empty group is a turn of waiting. Corruption heals a boss it lands on, and a bomb's
    # blast doesn't, which it marks with "heals_boss": False.
    hazards: list[dict] = field(default_factory=list)
    # Traps on the ground: {"cell", "damage", "effect"}. Only an enemy moving onto one sets it off.
    traps: list[dict] = field(default_factory=list)
    potions: list[str] = field(default_factory=list)  # The hero's potions, by the game's names.
    potion_slots: int = POTION_SLOTS  # How many potions the hero can hold.
    # Nobunaga's spotlit cells, the only ones where he can be hurt, or None without him. Empty once they've moved
    # within a simulated turn, since where they go is random.
    lit_cells: list[int] | None = None
    nobunaga_hp_last_turn: int | None = None  # His HP at his last turn: the lights move when it has changed.
    fight_won: bool = False  # Set when a boss dies, which ends the fight. See fight_won() for the rest.

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
    # Attacks that fired at nothing. Not scored since v1.14: a fired tile already loses its readiness to its
    # cooldown, and firing changes nothing on the board, so only events that do get summed along a line.
    wasted_attacks: int = 0
    # Queued tiles returned to hand instead of firing. Not scored: a fired tile has to be reloaded too, after its
    # cooldown, so charging only these made F1 fire tiles that changed nothing rather than keep them ready.
    sent_back: int = 0
    shields_broken: int = 0  # Enemy shields removed by the hero.
    tank_damage: int = 0  # Damage by the hero to a tank while its boss is alive, kept out of enemy_damage.
    exact_hits: int = 0  # Hits by the hero that dealt exactly the target's remaining HP.
    shove_cells: int = 0  # Cells the hero shoved enemies worth fighting, up to a few per shove.
    reloads: int = 0  # Crossbows reloaded.
    reloaded: int = 0  # Damage those reloads restored.
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
    # For PlayTile with a full queue: the queued tile to send back to hand first, as an index into state.tiles.
    # Sending one back is a free queue edit, so it's part of the same action.
    replace: int | None = None

    def label(self, state):
        if self.kind == "PlayTile":
            text = f"PlayTile {_tile_name(state, state.tiles[self.tile])}"
            if self.replace is not None:
                text += f" ({_tile_name(state, state.tiles[self.replace])} to hand)"
            return text
        if self.kind == "Attack" and self.order is not None:
            fired = [state.tiles[i] for i in self.order]
            kept = [_tile_name(state, t) for t in state.queue_tiles if not any(t is f for f in fired)]
            text = "Attack " + " > ".join(
                _tile_name(state, t) + ("" if t.in_queue else " (free)") for t in fired)
            return f"{text} ({', '.join(kept)} to hand)" if kept else text
        if self.kind in ("MoveLeft", "MoveRight"):
            direction = -1 if self.kind == "MoveLeft" else 1
            if state.occupant(state.hero.cell + direction) is not None:
                return f"{self.kind} ({SPECIAL_LABELS.get(state.special, 'special')})"
        return self.kind


def aim_volleys(enemy, hero):
    for attack in enemy.queue:
        if attack.name == "Volley" and attack.target_cell is None:
            attack.target_cell = hero.cell


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
            movable="Heavy" not in (data.get("traits") or []) and data.get("elite") != "Heavy",
            poison=data.get("poison") or 0,
            ice=data.get("ice") or 0,
            freezable="Unfreezable" not in (data.get("traits") or []),
            inanimate=bool(data.get("inanimate")),
            elite=data.get("elite") or "None",
        )

    tiles = [
        Tile(
            attack=attack(t["attack"]),
            cooldown=t["attack"]["cooldown"],
            charge=t["attack"]["cooldown"] - t["turnsBeforeCharged"],
            in_queue="AttackQueue" in t["where"],
            free_play=t["attack"].get("tileEffect") == "FreePlay",
            base_value=t["attack"].get("baseValue") or t["attack"].get("value") or CROSSBOW_DAMAGE,
        )
        for t in row["tiles"]
    ]
    hero = agent(row["hero"])
    hero.action = "Wait"
    enemies = [agent(e) for e in row["enemies"]]
    # The game locks a Volley onto the hero's cell as the turn it fires begins.
    for enemy in enemies:
        if enemy.action == "Attack":
            aim_volleys(enemy, hero)

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
        enemies=enemies,
        tiles=tiles,
        queue_tiles=queue_tiles,
        swap_charge=special.get("charge", 0),
        swap_cooldown=special.get("cooldown", 4),
        turns_until_wave=wave["turnsUntilNext"] if wave else None,
        last_wave=wave["isLast"] if wave else False,
        swap_damage=next((s["level"] for s in row.get("skills") or []
                          if isinstance(s, dict) and s.get("name") == "DamagingMove"), 0),
        friendly_bonus=next((s["level"] for s in row.get("skills") or []
                             if isinstance(s, dict) and s.get("name") == "UnfriendlyFire"), 0),
        dynamic_bonus=next((s["level"] for s in row.get("skills") or []
                            if isinstance(s, dict) and s.get("name") == "DynamicBoost"), 0),
        sniper_bonus=next((s["level"] for s in row.get("skills") or []
                           if isinstance(s, dict) and s.get("name") == "Sniper"), 0),
        two_way_swap=any(isinstance(s, dict) and s.get("name") == "TwoWayMove" for s in row.get("skills") or []),
        reactive_shield=any(isinstance(s, dict) and s.get("name") == "ReactiveShield" for s in row.get("skills") or []),
        potion_slots=POTION_SLOTS + sum(1 for s in row.get("skills") or []
                                        if isinstance(s, dict) and s.get("name") == "BigPockets"),
        special=special.get("name", SWAP),
        hazards=[dict(h, groups=[list(g) for g in h["groups"]]) for h in row.get("hazards") or []],
        potions=list(row.get("potions") or []),
        lit_cells=row.get("litCells"),
        nobunaga_hp_last_turn=row.get("nobunagaHpLastTurn"),
        traps=[{"cell": t["cell"], "damage": t["damage"], "effect": t.get("effect") or "None"}
               for t in row.get("traps") or []],
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
        if data["name"] != "Summon" and data.get("effect") not in (None, "None", "Curse", "DoubleStrike", "Ice",
                                                                   "PerfectStrike",
                                                                   "Poison", "Shockwave"):
            note(f"{data['name']} effect {data['effect']}")
        if data.get("tileEffect") not in (None, "None", "FreePlay"):
            note(f"{data['name']} tile effect {data['tileEffect']}")
        if data.get("nonLethal"):
            note(f"{data['name']} is non-lethal")

    def check_status(name, agent):
        if agent.get("ice"):
            note(f"{name} ice")

    for tile in row["tiles"]:
        check_attack(tile["attack"])
    hero = row["hero"]
    for data in hero["queue"]:
        check_attack(data)
    check_status("hero", hero)
    special_name = (hero.get("special") or {}).get("name")
    if special_name and special_name not in SPECIAL_MOVES:
        note(f"special move {special_name}")
    for enemy in row["enemies"]:
        for data in enemy["queue"]:
            check_attack(data)
        # A Heavy elite is simulated: it can't be pushed or pulled. Others would warn.
        if enemy.get("elite") not in (None, "None") + KNOWN_ELITES:
            note(f"elite {enemy['kind']}")
        for trait in enemy.get("traits") or []:
            if trait not in UNDERSTOOD_TRAITS:
                note(f"{enemy['kind']} trait {trait}")
    for skill in row.get("skills") or []:
        name = skill.get("name", skill) if isinstance(skill, dict) else skill
        if name not in UNDERSTOOD_SKILLS:
            note(f"skill {name}")
    return notes


def can_use_special(state, direction):
    """A special move needs a charge and a movable occupant, in the facing direction without Two Way Move.

    A shove also needs a cell behind the target, though someone can be standing on it. A throw goes the other way:
    it takes the enemy behind the hero, without Two Way Move, and needs the cell in front of the hero to exist and be
    empty, to land it on (ThrowSpecialMove.Allowed).
    """
    target = state.hero.cell + direction
    occupant = state.occupant(target)
    if state.special == SHOVE and not 0 <= target + direction < state.cells:
        return False
    if state.special == PHASE:
        # Through anyone, movable or not, but only with a free cell past the line before the wall
        # (PhaseSpecialMove.Allowed, PotentialPhaseCell).
        return (
            (direction == state.hero.facing or state.two_way_swap)
            and state.swap_charge >= state.swap_cooldown
            and occupant is not None
            and phase_cell(state, direction) is not None
        )
    if state.special == THROW:
        landing = state.hero.cell - direction
        if not 0 <= landing < state.cells or state.occupant(landing) is not None:
            return False
    allowed_way = -state.hero.facing if state.special == THROW else state.hero.facing
    return (
        state.special in SPECIAL_MOVES
        and (direction == allowed_way or state.two_way_swap)
        and state.swap_charge >= state.swap_cooldown
        and occupant is not None
        and occupant.movable
    )


def move_destination(state, cell, direction, occupied=None):
    """Where a move from `cell` ends, or None if the next cell is a wall or taken (then it's the special move).
    One cell, except for the Shadow, who dashes to the last free cell that way, next to whoever or whatever stops
    it (ShadowHero.PerformMoveAction and Dash: Cell.LastFreeCellInDirection). `occupied`, if given, is the set of
    cells taken, for a hero imagined elsewhere."""
    def taken(c):
        return c in occupied if occupied is not None else state.occupant(c) is not None
    nxt = cell + direction
    if not 0 <= nxt < state.cells or taken(nxt):
        return None
    if state.hero.kind != "Shadow":
        return nxt
    while 0 <= nxt + direction < state.cells and not taken(nxt + direction):
        nxt += direction
    return nxt


def phase_cell(state, direction):
    """Where a Phase lands: the first free cell past the agents in a row from the hero's side, or None at the wall."""
    cell = state.hero.cell + direction
    while 0 <= cell < state.cells:
        if state.occupant(cell) is None:
            return cell
        cell += direction
    return None


def perform_special(state, direction, outcome):
    """The hero's special move on the agent next to it. Only for when can_use_special allows it."""
    hero = state.hero
    target_cell = hero.cell + direction
    occupant = state.occupant(target_cell)
    state.swap_charge = 0
    if state.special == SHOVE:
        # The hero stays put. Damaging Move's hit comes first, so it may leave nobody to shove. The distance
        # earns nothing here, because stepping back makes the same space and keeps the charge.
        if state.swap_damage:
            land_hit(state, hero, occupant, state.swap_damage, outcome)
        if occupant.alive:
            push(state, hero, occupant, direction, outcome, credit_distance=False)
        return
    if state.special == PHASE:
        # The hero passes through and nobody moves. Damaging Move hits the agent it first passed
        # (PhaseSpecialMove.Perform: SpecialMove.ApplyEffectOnTargetAfterPositionCrossing on the hero's old neighbour).
        hero.cell = phase_cell(state, direction)
        if state.swap_damage:
            land_hit(state, hero, occupant, state.swap_damage, outcome)
        return
    if state.special == THROW:
        # Over the hero to the cell on its other side, then pushed on that way as far as it goes, hitting whoever stops
        # it, as a shove does (ThrowSpecialMove.Perform, Agent.Pushed). Damaging Move's hit comes after the crossing.
        occupant.cell = hero.cell - direction
        if state.swap_damage:
            land_hit(state, hero, occupant, state.swap_damage, outcome)
        if occupant.alive:
            push(state, hero, occupant, -direction, outcome, credit_distance=False)
        return
    occupant.cell = hero.cell
    if state.swap_damage:
        land_hit(state, hero, occupant, state.swap_damage, outcome)
    hero.cell = target_cell


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
        if state.occupant(target) is None or (allow_swap and can_use_special(state, direction)):
            actions.append(Action(kind))
    # A Free Play tile is never worth loading ahead of time: it can join any attack instead.
    loadable = [i for i, t in enumerate(state.tiles) if t.ready and not t.in_queue and not t.free_play]
    if len(hero.queue) < QUEUE_CAP:
        actions.extend(Action("PlayTile", index) for index in loadable)
    else:
        # With the queue full, a queued tile can go back to hand for free to make room.
        queued = [i for i, t in enumerate(state.tiles) if any(t is q for q in state.queue_tiles)]
        actions.extend(Action("PlayTile", index, replace=out) for index in loadable for out in queued)
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
    # A Volley lands on its locked cell, on whoever is there, ignoring anyone in between.
    if attack.name == "Volley":
        struck = state.occupant(attack.target_cell) if attack.target_cell is not None else None
        return [struck] if struck is not None else []
    if attack.name in SMOKE_BOMBS:
        targets = targets_of(state, attacker, attack)
        if not targets or not targets[0].movable:
            return []
        attacker.cell, targets[0].cell = targets[0].cell, attacker.cell
        return targets[:1]
    # Shadow Kama strikes only the first agent its range finds: ShadowKamaAttack.ApplyEffect. The Shogun statue's
    # reaches just the cell 2 ahead, past anyone in between.
    if attack.name == "ShadowKama":
        return targets_of(state, attacker, attack)[:1]
    if attack.name == "Crossbow":
        return targets_of(state, attacker, attack)[:CROSSBOW_TARGETS] if attack.value > 0 else []
    # Scar Strike hits every enemy below full health, wherever it is, chosen as the attack begins, so earlier tiles in
    # the volley can add to them (ScarStrikeAttack.Begin). Only the hero can use it.
    if attack.name == "ScarStrike":
        return [e for e in state.enemies if e.alive and e.hp < e.max_hp] if attacker is state.hero else []
    # Sharp Turn turns its user around first, then strikes what's in range in the new direction.
    if attack.name == "TurnAround":
        attacker.facing = -attacker.facing
        return targets_of(state, attacker, attack)
    # Lightning strikes the farthest agent in range ahead, passing over any Thorns enemy to the next farthest.
    if attack.name == "Lightning":
        in_range = [state.occupant(attacker.cell + attacker.facing * offset) for offset in attack.range]
        struck = [a for a in in_range if a is not None and a.kind != "Thorns"]
        return struck[-1:]
    return targets_of(state, attacker, attack)


def is_boss(agent):
    return agent.kind.endswith("Boss")


def is_tank(state, agent):
    """An enemy not worth fighting right now, since it dies with the boss."""
    return agent.kind in TANKS and any(e.alive and is_boss(e) for e in state.enemies)


def swap_toss(state, attacker):
    """Swaps whoever is on the cells directly either side of the attacker, if both cells exist."""
    left_cell, right_cell = attacker.cell - 1, attacker.cell + 1
    if not (0 <= left_cell and right_cell < state.cells):
        return False
    left, right = state.occupant(left_cell), state.occupant(right_cell)
    if (left and not left.movable) or (right and not right.movable):
        return False
    if left:
        left.cell = right_cell
    if right:
        right.cell = left_cell
    return bool(left or right)


def mirror_cell(cells, cell):
    middle = cells // 2 - (1 if cells % 2 == 0 else 0)
    return cell + 2 * (middle - cell)


def mirror(state, attacker):
    """Moves the attacker to the mirrored cell, trading places with anyone there. Both turn around."""
    start = attacker.cell
    target_cell = mirror_cell(state.cells, start)
    if not 0 <= target_cell < state.cells:
        return False
    occupant = state.occupant(target_cell) if target_cell != start else None
    if occupant is not None and not occupant.movable:
        return False
    attacker.cell = target_cell
    attacker.facing = -attacker.facing
    if occupant is not None:
        occupant.cell = start
        occupant.facing = -occupant.facing
    return True


def origin_of_symmetry(state, attacker):
    """Moves the attacker to the central cell, trading places with anyone there."""
    start = attacker.cell
    center = (state.cells - 1) // 2
    occupant = state.occupant(center) if center != start else None
    if occupant is not None and not occupant.movable:
        return False
    attacker.cell = center
    if occupant is not None:
        occupant.cell = start
    return center != start


def push(state, attacker, target, direction, outcome, credit_distance=True):
    """Pushes the target as far as it goes. If someone stops it, each of them takes a collision hit. A target the push's
    own hit killed still flies, so whoever stops it is still hit."""
    start = target.cell
    behind = run_to_last_free_cell(state, target, direction)
    if credit_distance and attacker is state.hero and target.alive and not is_tank(state, target):
        outcome.shove_cells += min(abs(target.cell - start), MAX_SHOVE_CREDIT)
    if behind:
        land_hit(state, attacker, behind[0], 1, outcome, collision=True)
        if target.alive:
            land_hit(state, attacker, target, 1, outcome, collision=True)


def shockwave(state, attacker, target, outcome):
    """Runs both ways from the target through touching agents, stopping at a gap, a wall or the hero.

    Everyone it reaches is hit, and so is the target, but only if it reached someone.
    """
    chain = []
    for direction in (-1, 1):
        cell = target.cell + direction
        while 0 <= cell < state.cells:
            agent = state.occupant(cell)
            if agent is None or agent is state.hero:
                break
            chain.append(agent)
            cell += direction
    if chain:
        for agent in [target] + chain:
            if agent.alive:
                land_hit(state, attacker, agent, SHOCKWAVE_DAMAGE, outcome, collision=True)


def spawn_barricade(state, attacker):
    """Puts a Barricade on the cell in front of the attacker, if that cell exists and is free."""
    cell = attacker.cell + attacker.facing
    if 0 <= cell < state.cells and state.occupant(cell) is None:
        facing = 1 if state.hero.cell > cell else -1
        state.enemies.append(Agent("Barricade", cell, facing, BARRICADE_HP, BARRICADE_HP, inanimate=True))


def place_bomb(state, attacker, attack):
    """Puts a bomb on the cell in front of the attacker. It blasts that cell and both neighbours."""
    cell = attacker.cell + attacker.facing
    if 0 <= cell < state.cells:
        blast = [c for c in (cell - 1, cell, cell + 1) if 0 <= c < state.cells]
        groups = [[] for _ in range(BOMB_FUSE - 1)] + [blast]
        state.hazards = state.hazards + [{"damage": attack.value, "groups": groups, "heals_boss": False}]


def strike_cell(state, attacker, cell, damage, outcome, heals_boss=True):
    """Damages whoever is on the cell. Corruption heals a boss instead."""
    agent = state.occupant(cell)
    if agent is None:
        return
    if heals_boss and is_boss(agent):
        agent.hp = min(agent.max_hp, agent.hp + damage)
    else:
        land_hit(state, attacker, agent, damage, outcome, collision=True)


def corrupted_barrage(state, attacker, attack, outcome):
    """Strikes the cells beside the attacker now, then one cell further out each turn."""
    origin = attacker.cell
    for cell in (origin - 1, origin + 1):
        strike_cell(state, attacker, cell, attack.value, outcome)
    groups = []
    for distance in range(2, state.cells):
        cells = [c for c in (origin - distance, origin + distance) if 0 <= c < state.cells]
        if cells:
            groups.append(cells)
    if groups:
        state.hazards = state.hazards + [{"damage": attack.value, "groups": groups}]


def strike_hazards(state, outcome, count):
    """The first `count` hazards strike their next group of cells. Any after those were fired this turn."""
    remaining = []
    for hazard in state.hazards[:count]:
        cells, later = hazard["groups"][0], hazard["groups"][1:]
        for cell in cells:
            strike_cell(state, None, cell, hazard["damage"], outcome, hazard.get("heals_boss", True))
        if later:
            remaining.append(dict(hazard, groups=later))
    state.hazards = remaining + state.hazards[count:]


def tick_poison(state, outcome):
    """Each poisoned agent takes 1, starting the turn it was poisoned. It's a hit, so a shield blocks it."""
    for agent in [state.hero] + list(state.enemies):
        if agent.alive and agent.poison > 0:
            land_hit(state, None, agent, 1, outcome)
            agent.poison -= 1


def shield_first_ally(state, attacker, attack):
    """Shields the first ally ahead without one. The hero and shielded allies don't stop it."""
    for offset in attack.range:
        agent = state.occupant(attacker.cell + attacker.facing * offset)
        if agent is None or agent is state.hero or agent.shield or agent.kind == "Thorns":
            continue
        agent.shield = True
        return


def apply_attack(state, attacker, attack, outcome):
    start = (attacker.cell, attacker.facing)
    _apply_attack(state, attacker, attack, outcome)
    # Double Strike plays the whole attack again straight after, targeting afresh: Agent.ExecuteAttacksInQueue.
    if attack.effect == "DoubleStrike" and attacker.alive:
        _apply_attack(state, attacker, attack, outcome)
    # The game raises its move-attack event after the attack's own hits, so Dynamic Boost only helps later ones.
    if attacker is state.hero and attack.name in MOVE_ATTACKS and (attacker.cell, attacker.facing) != start:
        state.boosted = True


def _apply_attack(state, attacker, attack, outcome):
    if attack.name in (UNKNOWN_TILE, UNKNOWN_COPY):
        return
    if attack.name not in MODELED and attack.name not in outcome.unmodeled:
        outcome.unmodeled.append(attack.name)
    if attack.name == "Shield":
        attacker.shield = True
        return
    if attack.name == "ShieldAllied":
        shield_first_ally(state, attacker, attack)
        return
    # Where a summon lands is random, so a player can't react to it either. It's ignored on purpose.
    # Copycat Mirror only gives its user a copy of a hero tile, which resolve_enemies keeps track of.
    # Maku, Sato's, ends the act and sets up a new battlefield, which only matters to a deeper search.
    if attack.name in ("Summon", "CopycatMirror", "Maku"):
        return
    if attack.name == "Barricade":
        spawn_barricade(state, attacker)
        return
    if attack.name == "Bomb":
        place_bomb(state, attacker, attack)
        return
    if attack.name == "Trap":
        place_trap(state, attacker, attack, outcome)
        return
    if attack.name == "BossSwap":
        boss_swap(state, attacker)
        return
    if attack.name in ("SwapToss", "Mirror", "OriginOfSymmetry"):
        moves = {"SwapToss": swap_toss, "Mirror": mirror, "OriginOfSymmetry": origin_of_symmetry}
        if not moves[attack.name](state, attacker) and attacker is state.hero:
            outcome.wasted_attacks += 1
        return
    if attack.name == "CorruptedBarrage":
        corrupted_barrage(state, attacker, attack, outcome)
        return
    if attack.name == "Curse":
        # A projectile rather than a hit, so a shield neither stops it nor is used up by it.
        targets = targets_of(state, attacker, attack)
        if targets:
            targets[0].curse = True
        elif attacker is state.hero:
            outcome.wasted_attacks += 1
        return
    start_cell, start_facing = attacker.cell, attacker.facing
    hits = attack_hits(state, attacker, attack)
    # An attack that moved or turned the hero still did something, even if it hit nothing, and so does a reload.
    reload = attack.name == "Crossbow" and attack.value == 0
    if (not hits and attacker is state.hero and attacker.cell == start_cell and attacker.facing == start_facing
            and not reload):
        outcome.wasted_attacks += 1
    for target in hits:
        # A boss killed earlier in this sweep takes everyone else with it.
        if not target.alive:
            continue
        value = attack.value
        # Sai hits twice as hard on an enemy telegraphing an attack this turn: a counter (SaiAttack.ApplyEffect).
        if attack.name == "Sai" and target.action == "Attack":
            value *= 2
        land_hit(state, attacker, target, value, outcome)
        hit_effect(state, attacker, target, attack.effect, outcome)
        # A shield blocks the hook's damage, but not its pull.
        if attack.name == "GrapplingHook" and target.alive and target.movable:
            target.cell = attacker.cell + attacker.facing
        # Dragon Punch pushes its target even when the hit kills it: the body still flies and hits whoever stops it
        # (DragonPunchAttack.PerformAttack has no check, and logs/run9 shows it twice).
        if attack.name == "DragonPunch" and target.movable:
            push(state, attacker, target, attacker.facing, outcome)


def hit_effect(state, attacker, target, effect, outcome):
    """A tile's effect on whoever it hit, after the hit: Attack.ProcessAttackEffects in the game's code."""
    # After the hit, so a curse never doubles the attack that applied it.
    if target.alive and effect == "Curse":
        target.curse = True
    # Sets the turns left rather than adding to them, so poisoning again only refreshes it.
    if target.alive and effect == "Poison":
        target.poison = POISON_TURNS
    # Freezing sets the turns of ice rather than adding to them, and cancels what the enemy telegraphed for this turn:
    # Enemy.ApplyIceStatusCoroutine. Its queue stays. While it has ice it chooses to do nothing, so it loses this turn
    # and the next three. A frozen hero isn't simulated.
    if target.alive and effect == "Ice" and target is not state.hero and target.freezable:
        target.ice = ICE_TURNS
        target.action = "Wait"
    # Each target sets off its own, even one that just died, and a shield on the target doesn't stop it.
    if effect == "Shockwave":
        shockwave(state, attacker, target, outcome)


# Potions the hero can use in a fight, by the game's names, and what each does, read from each one's Effect in the
# game's code. Using one is free and immediate, and only allowed between turns. D6 rerolls every enemy's intention at
# random, so it can't be simulated.
SIMULATED_POTIONS = {"Edamame", "Shield", "MassIce", "RainOfMirrors", "MassPoison", "MassCurse", "CoolUp"}
EDAMAME_HEAL = 3  # HealSmallPotion.heal
OPPOSITE_ACTIONS = {"MoveLeft": "MoveRight", "MoveRight": "MoveLeft", "FlipLeft": "FlipRight", "FlipRight": "FlipLeft"}


def apply_potion(state, name):
    """A copy of the board after using this potion, which is gone from the hero's potions."""
    state = copy.deepcopy(state)
    state.potions.remove(name)
    hero = state.hero
    enemies = [e for e in state.enemies if e.alive]
    if name == "Edamame":
        hero.hp = min(hero.max_hp, hero.hp + EDAMAME_HEAL)
    elif name == "Shield":
        hero.shield = True
    elif name == "MassIce":
        # Freezes every enemy that can be frozen, cancelling what each telegraphed: FreezeTimePotion.
        for enemy in enemies:
            if enemy.freezable:
                enemy.ice = ICE_TURNS
                enemy.action = "Wait"
    elif name == "RainOfMirrors":
        # Turns every movable enemy around and reverses its telegraphed move or flip: RainOfMirrorsEffect.
        for enemy in enemies:
            if enemy.movable:
                enemy.facing = -enemy.facing
                enemy.action = OPPOSITE_ACTIONS.get(enemy.action, enemy.action)
    elif name == "MassPoison":
        for enemy in enemies:
            enemy.poison = POISON_TURNS
    elif name == "MassCurse":
        for enemy in enemies:
            enemy.curse = True
    elif name == "CoolUp":
        # Every tile and the special move fully recharged: TilesManager.RechargeCooldownForDeck.
        for tile in state.tiles:
            tile.charge = tile.cooldown
        state.swap_charge = state.swap_cooldown
    else:
        raise ValueError(f"potion {name} isn't simulated")
    return state


def boss_swap(state, attacker):
    """Trades places with the boss, wherever each is, and neither turns. BossSwapAttack in the game's code, the
    Swapper's, which keeps putting Ieyasu in front of or behind it."""
    boss = next((e for e in state.enemies if e.alive and is_boss(e) and e is not attacker), None)
    if boss is not None:
        attacker.cell, boss.cell = boss.cell, attacker.cell


def place_trap(state, attacker, attack, outcome):
    """Puts a trap on the cell in front of the attacker, if that cell exists, whoever is on it. TrapAttack in the
    game's code. It's thrown there and only armed once it lands, so an enemy already on the cell doesn't set it off:
    an enemy has to move onto it. That's inferred from how the game's triggers work, not stated in its code."""
    cell = attacker.cell + attacker.facing
    if 0 <= cell < state.cells:
        state.traps = state.traps + [{"cell": cell, "damage": attack.value, "effect": attack.effect}]
    elif attacker is state.hero:
        outcome.wasted_attacks += 1


def enemy_cells(state):
    """Where each enemy is, to tell afterward who moved onto a trap."""
    return {id(e): e.cell for e in state.enemies if e.alive}


def spring_traps(state, outcome, before):
    """Sets off each trap an enemy has moved onto since `before`, once, for its damage and effect. Trap in the game's
    code: only enemies set one off, so the hero can stand on its own. The hit has no attacker, but it's the hero's
    doing, so it counts as the hero's. Moving through a trap's cell without stopping there isn't simulated."""
    for trap in list(state.traps):
        enemy = state.occupant(trap["cell"])
        if enemy is None or enemy is state.hero or before.get(id(enemy)) == trap["cell"]:
            continue
        state.traps = [t for t in state.traps if t is not trap]
        land_hit(state, state.hero, enemy, trap["damage"], outcome, collision=True)
        hit_effect(state, state.hero, enemy, trap["effect"], outcome)


def armored(state, agent):
    """Whether Nobunaga's armor stops a hit on him: anywhere but a spotlit cell (NobunagaBoss.ReceiveAttack)."""
    return agent.kind == "NobunagaBoss" and state.lit_cells is not None and agent.cell not in state.lit_cells


def relocate_lights(state, nobunaga):
    """At the end of each turn, his spotlights move if his HP has dropped since the last, to random cells other than
    the ones lit and his own (NobunagaBoss.ProcessTurn, which the room runs after the agents' end of turn). Where is
    unknown, so none counts as lit from then on."""
    if state.lit_cells is None or not nobunaga.alive:
        return
    last = state.nobunaga_hp_last_turn
    if last is not None and nobunaga.hp < last:
        state.lit_cells = []
    state.nobunaga_hp_last_turn = nobunaga.hp


def land_hit(state, attacker, target, value, outcome, collision=False):
    # Nobunaga's armor stops the whole hit off a spotlit cell, shield and curse included, but a tile's effect still
    # lands afterward, as for a shield: Attack.HitTarget applies effects whatever ReceiveAttack did.
    if armored(state, target):
        return
    # A shield blocks the hit and leaves any curse in place. A tile's effect still lands afterward.
    if target.shield:
        target.shield = False
        if attacker is state.hero and not is_tank(state, target):
            outcome.shields_broken += 1
    else:
        hp_before = target.hp
        deal_damage(state, attacker, target, value, outcome, collision)
        # A Reactive Shield elite that had no shield, took damage and lived gains one: Enemy.ReceiveAttack.
        if target.elite == "ReactiveShield" and target.alive and target.hp < hp_before:
            target.shield = True


def end_of_boss(state, by_hero, outcome):
    """When a boss dies, everyone else in the room dies with it, and the fight is won.

    Each one counts as a kill by whoever killed the boss, with its HP as damage, the same as killing it outright,
    except a tank, which was only ever worth anything as part of the boss, and anything inanimate, like a Barricade,
    which isn't a fighter."""
    for enemy in state.enemies:
        if enemy.alive and not is_boss(enemy) and enemy.kind not in TANKS and not enemy.inanimate:
            if by_hero:
                outcome.enemy_damage += enemy.hp
            else:
                outcome.friendly_damage += enemy.hp
            outcome.kills += 1
        enemy.hp = 0
    state.fight_won = True


def fight_won(state):
    """Whether the fight is over and won: a boss is dead, or every enemy of the last wave, or of a room without
    waves."""
    if state.fight_won:
        return True
    return not any(e.alive for e in state.enemies) and (state.turns_until_wave is None or state.last_wave)


def deal_damage(state, attacker, target, value, outcome, collision=False):
    enemy_on_enemy = attacker is not None and attacker is not state.hero and target is not state.hero
    if enemy_on_enemy and not collision:
        value += state.friendly_bonus
    # Measured when the hit lands, so a Smoke Bomb's trade of places doesn't change it, and a Charge lands adjacent.
    if attacker is state.hero and not collision and abs(attacker.cell - target.cell) >= SNIPER_DISTANCE:
        value += state.sniper_bonus
    if attacker is state.hero and not collision and state.boosted:
        value += state.dynamic_bonus
    if target.curse and value > 0:
        value *= 2
        target.curse = False
    if attacker is state.hero and value == target.hp:
        outcome.exact_hits += 1
    damage = min(value, target.hp)
    tank = is_tank(state, target)
    target.hp -= damage
    if target is state.hero:
        outcome.hp_lost += damage
        # Reactive Shield shields the hero once it takes damage and lives, if it has no shield
        # (ReactiveShieldSkill.UponHeroTookDamage). Any damage: a hit, a collision or a poison tick.
        if state.reactive_shield and damage > 0 and target.alive:
            target.shield = True
    elif tank:
        if attacker is state.hero:
            outcome.tank_damage += damage
    elif attacker is state.hero:
        outcome.enemy_damage += damage
        if not target.alive:
            outcome.kills += 1
    else:
        # An enemy hitting an ally still removes HP from the room.
        outcome.friendly_damage += damage
        if not target.alive:
            outcome.kills += 1
    # Damage to the Side twin also comes off the Main twin, the real HP pool.
    if target.kind == "TwinSideBoss":
        main = next((e for e in state.enemies if e.kind == "TwinMainBoss" and e.alive), None)
        if main is not None:
            main.hp = max(0, main.hp - damage)
            if not main.alive:
                outcome.kills += 1
                end_of_boss(state, attacker is state.hero, outcome)
    elif is_boss(target) and not target.alive:
        end_of_boss(state, attacker is state.hero, outcome)
    if damage and not target.alive and target.kind == "Warden":
        explode(state, target, outcome)


def explode(state, warden, outcome):
    """A Warden that dies hits its own cell and both beside it for 2, the hero included, as its own hit.

    By the code it doesn't if it dies before its first decision, but any Warden on the board has made one. Each
    Warden this kills explodes in turn."""
    for cell in (warden.cell - 1, warden.cell, warden.cell + 1):
        agent = state.occupant(cell) if 0 <= cell < state.cells else None
        if agent is not None:
            land_hit(state, warden, agent, WARDEN_EXPLOSION, outcome)


def fire_crossbow(tile, outcome):
    """After a Crossbow fires: a shot empties it, and a reload loads it back to its base damage. A new attack rather
    than a change to this one, which copies of the board share."""
    if tile.attack.name != "Crossbow":
        return
    if tile.attack.value > 0:
        tile.attack = dataclasses.replace(tile.attack, value=0)
    else:
        tile.attack = dataclasses.replace(tile.attack, value=tile.base_value or CROSSBOW_DAMAGE)
        outcome.reloads += 1
        outcome.reloaded += tile.attack.value


def fire_hero_queue(state, outcome, order=None):
    """Fires the chosen tiles in order. Any others go back to the hand, still charged."""
    fired = list(state.queue_tiles) if order is None else [state.tiles[i] for i in order]
    for tile in fired:
        exact_before = outcome.exact_hits
        before = enemy_cells(state)
        apply_attack(state, state.hero, tile.attack, outcome)
        spring_traps(state, outcome, before)
        fire_crossbow(tile, outcome)
        tile.charge = 0
        tile.just_played = True
        # Perfect Strike: an exact kill recharges the tile straight away.
        if tile.attack.effect == "PerfectStrike" and outcome.exact_hits > exact_before:
            tile.charge = tile.cooldown
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
        if action.replace is not None:
            out = state.tiles[action.replace]
            position = next(i for i, t in enumerate(state.queue_tiles) if t is out)
            out.in_queue = False
            del state.queue_tiles[position]
            del hero.queue[position]
            outcome.sent_back += 1
        tile = state.tiles[action.tile]
        tile.in_queue = True
        hero.queue.append(tile.attack)
        state.queue_tiles.append(tile)
    elif action.kind in ("MoveLeft", "MoveRight"):
        direction = -1 if action.kind == "MoveLeft" else 1
        target = hero.cell + direction
        if state.occupant(target) is not None:
            before = enemy_cells(state)
            perform_special(state, direction, outcome)
            spring_traps(state, outcome, before)
            swapped = True
        else:
            hero.cell = move_destination(state, hero.cell, direction)
    return swapped


def enemy_move(state, enemy):
    """Moves an enemy one cell, also moving an enemy ahead that's about to go the same way. A leaper runs to the
    last free cell instead, after whoever first blocks it, if that one is going the same way."""
    if enemy.moved:
        return
    direction = enemy.move_dir
    target = enemy.cell + direction
    enemy.moved = True
    if enemy.kind in LEAPERS:
        cell = target
        while 0 <= cell < state.cells and state.occupant(cell) is None:
            cell += direction
        blocker = state.occupant(cell) if 0 <= cell < state.cells else None
        if blocker is not None and blocker is not state.hero and not blocker.moved and blocker.move_dir == direction:
            enemy_move(state, blocker)
        run_to_last_free_cell(state, enemy, direction)
        return
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
            before = enemy_cells(state)
            enemy_move(state, enemy)
            spring_traps(state, outcome, before)
    for enemy in enemies:
        if enemy.alive and enemy.action == "Attack" and state.hero.alive:
            for attack in list(enemy.queue):
                if enemy.alive:
                    before = enemy_cells(state)
                    apply_attack(state, enemy, attack, outcome)
                    spring_traps(state, outcome, before)
            # A Copycat Mirror leaves a copy of a hero tile in the queue, and which one isn't known yet.
            copies = sum(a.name == "CopycatMirror" for a in enemy.queue)
            enemy.queue = [Attack(UNKNOWN_COPY, 0, []) for _ in range(copies)]
    for enemy in enemies:
        if enemy.alive and enemy.action == "PlayTile":
            enemy.queue.append(Attack(UNKNOWN_TILE, 0, []))


def end_turn(state, swapped):
    state.boosted = False
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
        enemy.ice = max(0, enemy.ice - 1)
        # Blade of Patience hits 1 harder for each turn it waits in the queue. Any here was there all this turn,
        # since a tile played this turn isn't identified yet.
        enemy.queue = [Attack(a.name, a.value + 1, a.range, a.first_target, a.effect, a.target_cell)
                       if a.name == "BladeOfPatience" else a for a in enemy.queue]
        enemy.action = "Wait"  # What it does next isn't known until the game shows it.
        # A loaded Volley will lock onto wherever the hero ends this turn, leaving a turn to step off.
        aim_volleys(enemy, state.hero)


def step(state, action):
    """Returns the state after one full turn, and what happened. The input isn't changed."""
    next_state = copy.deepcopy(state)
    outcome = Outcome()
    swapped = hero_action(next_state, action, outcome)
    already_on_the_way = len(next_state.hazards)
    resolve_enemies(next_state, outcome)
    tick_poison(next_state, outcome)
    strike_hazards(next_state, outcome, already_on_the_way)
    # Last of all, from the room's turn: after every agent's end of turn, so a poison tick still sees the old lights
    # (CombatManager.ProcessTurn calls Room.ProcessTurn after Agent.EndOfTurn).
    for enemy in list(next_state.enemies):
        if enemy.kind == "NobunagaBoss":
            relocate_lights(next_state, enemy)
    end_turn(next_state, swapped)
    return next_state, outcome
