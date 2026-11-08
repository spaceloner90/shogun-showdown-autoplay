"""The regular enemies' AI, ported from the game's code, to know what each will telegraph next turn.

At the end of every turn the game has each enemy choose its next action (Enemy.DecideNextAction): one with ice
waits; otherwise its kind's AIPickAction picks one, and a move into a wall or an occupied cell becomes a wait.
`decide` does the same. It returns None where the choice can't be known: a kind not ported (bosses, the Kabukai,
the Shielder, the Summoner, the Swapper), or one that depends on something the board doesn't show.

The kinds share building blocks (Enemy.FaceTarget, MoveTowardsTarget, MoveAwayFromTarget,
MoveTowardsStrikingPosition, IsThreatheningTarget) and differ in order and in which tile each plays. Their target is
the hero (EnemyTargetHelper.GetTarget, with no decoys simulated). An enemy's first turn is a wait, but every enemy on
a logged board has already had it, and none spawn in the simulation.
"""
from __future__ import annotations

from dataclasses import dataclass

# Each kind's tiles as the logs show them, every one the same across runs. An elite with Double Strike plays them with
# that effect (Enemy.get_AttackEffect); the Grappler's hook and the Shadow Dasher's charge are always plain.
TILES = {
    "Katana": (2, [1], True),
    "Spear": (2, [1, 2], False),
    "Swirl": (2, [-1, 1], False),
    "Arrow": (2, list(range(1, 11)), True),
    "Volley": (2, list(range(1, 11)), True),
    "Charge": (1, list(range(1, 11)), True),
    "GrapplingHook": (1, list(range(1, 11)), True),
    "Shuriken": (1, list(range(1, 11)), True),
    "SmokeBomb": (1, list(range(1, 11)), True),
    "Curse": (0, list(range(1, 11)), True),
    "Summon": (0, [], True),
}
PLAIN_EFFECT = {("Grappler", "GrapplingHook"), ("ShadowDasher", "Charge"), ("Warden", "Summon")}

# The kinds whose choices are ported, each with the tile it plays into an empty queue.
FIRST_TILE = {"Ashigaru": "Katana", "YariMaster": "Spear", "Guardian": "Katana", "TwinTachi": "Swirl",
              "Sniper": "Volley", "Archer": "Arrow", "Charger": "Charge", "Strider": "Katana",
              "Grappler": "GrapplingHook", "Shinobi": None, "Warden": None, "ShadowDasher": "Charge",
              "BlightCharger": "Charge", "Barricade": None}
PORTED = set(FIRST_TILE)


@dataclass
class Choice:
    action: str            # The game's ActionEnum name: Wait, MoveLeft, MoveRight, Attack, PlayTile, FlipLeft, FlipRight.
    tile: str | None = None  # For PlayTile, the tile it will play.


def make_attack(kind, name, elite):
    from rules import Attack
    value, rng, first = TILES[name]
    effect = "DoubleStrike" if elite == "DoubleStrike" and (kind, name) not in PLAIN_EFFECT else "None"
    return Attack(name, value, list(rng), first, effect)


def _target_dir(state, enemy):
    return 1 if state.hero.cell > enemy.cell else -1


def _facing_target(state, enemy):
    return enemy.facing == _target_dir(state, enemy)


def _face_target(state, enemy):
    return Choice("FlipLeft" if enemy.facing > 0 else "FlipRight")


def _toward(state, enemy):
    return Choice("MoveRight" if _target_dir(state, enemy) > 0 else "MoveLeft")


def _away(state, enemy):
    return Choice("MoveLeft" if _target_dir(state, enemy) > 0 else "MoveRight")


def _distance(state, enemy):
    return abs(state.hero.cell - enemy.cell)


def _path_free(state, enemy):
    """Nobody between it and the hero (Enemy.IsPathToTargetFree)."""
    low, high = sorted((enemy.cell, state.hero.cell))
    return all(state.occupant(c) is None for c in range(low + 1, high))


def _valued(enemy):
    return [a for a in enemy.queue if a.value > 0]


def _threatening(state, enemy, include_without_value=False):
    """Whether a queued attack has the hero among the agents it reaches now (Enemy.IsThreatheningTarget)."""
    from rules import targets_of
    for attack in enemy.queue:
        if (attack.value > 0 or include_without_value) and state.hero in targets_of(state, enemy, attack):
            return True
    return False


def _toward_striking_position(state, enemy):
    """Enemy.MoveTowardsStrikingPosition: closer if out of reach, back if too close, turn round for a backward-only
    queue, otherwise wait."""
    valued = _valued(enemy)
    if not valued or _threatening(state, enemy):
        return Choice("Wait")
    low = min(1000, min(min(a.range) for a in valued if a.range))
    high = max(0, max(max(a.range) for a in valued if a.range))
    distance = _distance(state, enemy)
    if distance < low:
        return _away(state, enemy)
    if distance > high:
        return _toward(state, enemy)
    if all(all(r < 0 for r in a.range) for a in enemy.queue) and _facing_target(state, enemy):
        return Choice("FlipLeft" if enemy.facing > 0 else "FlipRight")
    return Choice("Wait")


def _play(tile):
    return Choice("PlayTile", tile)


def _pick(state, enemy, previous):
    """The kind's AIPickAction, by `previous`, the action it took this turn. None where it can't be known."""
    kind = enemy.kind
    quick = enemy.elite == "Quick"
    tiles = len(enemy.queue)
    if kind == "Barricade":
        return Choice("Wait")
    if kind == "TwinTachi":
        if previous == "PlayTile" and not quick:
            return Choice("Wait")
        if _valued(enemy) and _threatening(state, enemy):
            return Choice("Attack")
        if previous == "Attack":
            return _away(state, enemy)
        if not _facing_target(state, enemy):
            return _face_target(state, enemy)
        if tiles == 0:
            return _play("Swirl")
        if _valued(enemy) and _path_free(state, enemy):
            return _toward_striking_position(state, enemy)
        return Choice("Wait")
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if kind == "Guardian":
        if previous == "Attack" and _path_free(state, enemy):
            return _toward(state, enemy)
        if previous == "PlayTile":
            if quick and _threatening(state, enemy):
                return Choice("Attack")
            return _toward(state, enemy) if _path_free(state, enemy) else Choice("Wait")
        if _threatening(state, enemy):
            return Choice("Attack")
        if tiles == 0:
            return _play("Katana")
        if _valued(enemy) and _path_free(state, enemy):
            return _toward_striking_position(state, enemy)
        return Choice("Wait")
    if previous == "Attack":
        return Choice("Wait") if kind == "Archer" else _away(state, enemy)
    if kind == "Grappler":
        if previous == "PlayTile" and tiles == 2 and not quick:
            return Choice("Wait")
        if tiles == 0:
            return _play("GrapplingHook")
        if tiles == 1:
            return _play("Katana")
        if tiles == 2:
            if _threatening(state, enemy):
                return Choice("Attack")
            if _path_free(state, enemy):
                return _toward_striking_position(state, enemy)
        return Choice("Wait")
    if kind == "ShadowDasher":
        if tiles == 0:
            return _play("Charge")
        if tiles == 1:
            return _play("Katana")
        if tiles == 2:
            if _threatening(state, enemy):
                return Choice("Attack")
            if _path_free(state, enemy):
                return _toward_striking_position(state, enemy)
        return Choice("Wait")
    if kind == "BlightCharger":
        if tiles == 0:
            return _play("Charge")
        return Choice("Attack") if _valued(enemy) and _threatening(state, enemy) else Choice("Wait")
    if kind == "Shinobi":
        if tiles < 1:
            # It alternates Shuriken and Smoke Bomb (ShinobiEnemy.prevAttack), which the board only shows while one
            # is queued.
            if enemy.last_tile is None:
                return None
            return _play("SmokeBomb" if enemy.last_tile == "Shuriken" else "Shuriken")
        if _valued(enemy):
            if _threatening(state, enemy):
                return Choice("Attack")
            if _path_free(state, enemy):
                return _toward_striking_position(state, enemy)
        return Choice("Wait")
    if previous == "PlayTile" and not quick:
        return Choice("Wait")
    if kind == "Warden":
        if tiles == 0:
            # Curse, then Summon, then Curse again (WardenEnemy.previousAttack).
            if enemy.last_tile is None:
                return None
            return _play("Summon" if enemy.last_tile == "Curse" else "Curse")
        if any(a.name == "Summon" for a in enemy.queue):
            return Choice("Attack")
        if any(a.name == "Curse" for a in enemy.queue):
            if _threatening(state, enemy, include_without_value=True):
                return Choice("Attack")
            if _path_free(state, enemy):
                return _toward_striking_position(state, enemy)
        return Choice("Wait")
    if tiles == 0:
        return _play(FIRST_TILE[kind])
    if kind in ("Sniper",):
        return Choice("Attack") if _valued(enemy) else Choice("Wait")
    if kind in ("Archer", "Charger"):
        return Choice("Attack") if _valued(enemy) and _threatening(state, enemy) else Choice("Wait")
    # Ashigaru, Yari Master, Strider.
    if _valued(enemy):
        if _threatening(state, enemy):
            return Choice("Attack")
        if _path_free(state, enemy):
            return _toward_striking_position(state, enemy)
    return Choice("Wait")


def tile_for(enemy):
    """The tile a ported enemy telegraphing PlayTile will play, from its queue now, or None if unknown."""
    if enemy.kind not in PORTED:
        return None
    tiles = len(enemy.queue)
    if enemy.kind == "Grappler":
        return {0: "GrapplingHook", 1: "Katana"}.get(tiles)
    if enemy.kind == "ShadowDasher":
        return {0: "Charge", 1: "Katana"}.get(tiles)
    if enemy.kind in ("Shinobi", "Warden"):
        if enemy.last_tile is None:
            return None
        if enemy.kind == "Shinobi":
            return "SmokeBomb" if enemy.last_tile == "Shuriken" else "Shuriken"
        return "Summon" if enemy.last_tile == "Curse" else "Curse"
    return FIRST_TILE.get(enemy.kind) if tiles == 0 else None


def guess(state, enemy):
    """For an enemy whose choice can't be known: it attacks if what it holds would hit the hero, else waits. In the
    logs, enemies with AI not ported (bosses mostly) attacked on 165 of 207 turns they could hit the hero, most
    bosses every time, and on 8% of the rest. It's a guess, so it stays marked unknown."""
    from rules import UNKNOWN_COPY, UNKNOWN_TILE
    if enemy.ice > 0 or any(a.name in (UNKNOWN_TILE, UNKNOWN_COPY) for a in enemy.queue):
        return Choice("Wait")
    return Choice("Attack") if _valued(enemy) and _threatening(state, enemy) else Choice("Wait")


def decide(state, enemy, previous):
    """What `enemy` telegraphs for next turn, decided at the end of this one, in which it did `previous`. None when
    that can't be known."""
    if enemy.kind not in PORTED:
        return None
    if enemy.ice > 0:
        return Choice("Wait")
    # A tile it holds that isn't identified leaves its choice unknown too.
    from rules import UNKNOWN_COPY, UNKNOWN_TILE
    if any(a.name in (UNKNOWN_TILE, UNKNOWN_COPY) for a in enemy.queue):
        return None
    choice = _pick(state, enemy, previous)
    if choice is None:
        return None
    # A move needs a free cell that way (Enemy.CanPerformAction).
    if choice.action in ("MoveLeft", "MoveRight"):
        cell = enemy.cell + (-1 if choice.action == "MoveLeft" else 1)
        if not 0 <= cell < state.cells or state.occupant(cell) is not None:
            return Choice("Wait")
    return choice
