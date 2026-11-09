"""The regular enemies' AI, ported from the game's code, to know what each will telegraph next turn.

At the end of every turn the game has each enemy choose its next action (Enemy.DecideNextAction): one with ice
waits; otherwise its kind's AIPickAction picks one, and a move into a wall or an occupied cell becomes a wait.
`decide` does the same. It returns None where the choice can't be known: a kind not ported (the Kabukai, the
Shielder, the Shogun's Summoners), or one that depends on something the board doesn't show, such as a boss's random
pattern or tile, or a counter older logs lack (mod 0.19.0 logs them).

The kinds share building blocks (Enemy.FaceTarget, MoveTowardsTarget, MoveAwayFromTarget,
MoveTowardsStrikingPosition, IsThreatheningTarget) and differ in order and in which tile each plays. Their target is
the hero (EnemyTargetHelper.GetTarget, with no decoys simulated), but Rei's: an ally in his way. A boss's first
choice (Enemy.FirstTurn) is made at the end of the fight's first turn; regular enemies' are made before any logged
board, and none spawn in the simulation.
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
    "BossSwap": (0, [], True),
    # Iwao's, as logged.
    "EarthImpale": (2, [-2, 2], False),
    "Dash": (0, [], True),
    "CorruptedWaveL2R": (1, list(range(1, 11)), False),
    "CorruptedWaveR2L": (1, list(range(1, 11)), False),
    # The other bosses', as logged: each the same for every boss that plays it.
    "BackCharge": (1, [-r for r in range(1, 11)], True),
    "Barricade": (0, [1], True),
    "DragonPunch": (1, [1], True),
    "Tetsubo": (4, [1], True),
    "BlazingSuisei": (2, [1, 2, 3], True),
    "Bomb": (3, [1], True),
    "Mirror": (0, [], True),
    "OriginOfSymmetry": (0, [], True),
    "BladeOfPatience": (0, [1], True),
    "Shield": (0, [], True),
    "ShadowDash": (1, list(range(1, 11)), True),
    "CopycatMirror": (0, [1], True),
    "Maku": (0, [], True),
    "Sai": (2, [1], True),
    "TwinTessen": (1, [-1, 1], False),
    "CorruptedBarrage": (3, [-1, 1], True),
    "ShadowKama": (3, [2], False),
    "SwapToss": (0, [-1, 1], True),
}
PLAIN_EFFECT = {("Grappler", "GrapplingHook"), ("ShadowDasher", "Charge"), ("Warden", "Summon")}

# The kinds whose choices are ported, each with the tile it plays into an empty queue.
FIRST_TILE = {"Ashigaru": "Katana", "YariMaster": "Spear", "Guardian": "Katana", "TwinTachi": "Swirl",
              "Sniper": "Volley", "Archer": "Arrow", "Charger": "Charge", "Strider": "Katana",
              "Grappler": "GrapplingHook", "Shinobi": None, "Warden": None, "ShadowDasher": "Charge",
              "BlightCharger": "Charge", "Barricade": None, "Summoner": "Summon", "Swapper": "BossSwap",
              "DaisukeBoss": None, "IwaoBoss": None}
# The bosses ported since v3.14, each by its own function below. Into an empty queue they play a random tile, or
# follow a pattern.
BOSSES = ("ReiBoss", "KowaBoss", "StatueBoss", "TwinMainBoss", "TwinSideBoss", "FumikoBoss", "BaruBoss", "IeyasuBoss",
          "HideyoshiBoss", "NobunagaBoss", "SatoBoss", "ShogunPhase1Boss", "ShogunPhase2Boss")
FIRST_TILE.update({kind: None for kind in BOSSES})
SWAPPER_WAIT = 3  # SwapperEnemy.get_NTurnsBetweenAttacks
PORTED = set(FIRST_TILE)


@dataclass
class Choice:
    action: str            # The game's ActionEnum name: Wait, MoveLeft, MoveRight, Attack, PlayTile, FlipLeft, FlipRight.
    tile: str | None = None  # For PlayTile, the tile it will play.


def make_attack(kind, name, elite):
    from rules import UNKNOWN_TILE, Attack
    if name not in TILES:
        # A tile no log has shown an enemy holding yet: its numbers aren't known until it shows.
        return Attack(UNKNOWN_TILE, 0, [])
    value, rng, first = TILES[name]
    effect = "DoubleStrike" if elite == "DoubleStrike" and (kind, name) not in PLAIN_EFFECT else "None"
    return Attack(name, value, list(rng), first, effect)


# The helpers below are the game's Enemy methods, toward the enemy's target: the hero, unless `to` names another
# agent (Rei turns on an ally in his way, ReiBoss.get_Target).
def _target(state, to):
    return state.hero if to is None else to


def _target_dir(state, enemy, to=None):
    return 1 if _target(state, to).cell > enemy.cell else -1


def _facing_target(state, enemy, to=None):
    return enemy.facing == _target_dir(state, enemy, to)


def _face_target(state, enemy, to=None):
    return Choice("FlipLeft" if enemy.facing > 0 else "FlipRight")


def _toward(state, enemy, to=None):
    return Choice("MoveRight" if _target_dir(state, enemy, to) > 0 else "MoveLeft")


def _away(state, enemy, to=None):
    return Choice("MoveLeft" if _target_dir(state, enemy, to) > 0 else "MoveRight")


def _can_move_away(state, enemy, to=None):
    """Enemy.get_CanMoveAwayFromTarget: a free cell the other way."""
    cell = enemy.cell - _target_dir(state, enemy, to)
    return 0 <= cell < state.cells and state.occupant(cell) is None


def _distance(state, enemy, to=None):
    return abs(_target(state, to).cell - enemy.cell)


def _path_free(state, enemy, to=None):
    """Nobody between it and the target (Enemy.IsPathToTargetFree)."""
    low, high = sorted((enemy.cell, _target(state, to).cell))
    return all(state.occupant(c) is None for c in range(low + 1, high))


def _valued(enemy):
    return [a for a in enemy.queue if a.value > 0]


def _threatening(state, enemy, include_without_value=False, to=None):
    """Whether a queued attack has the target among the agents it reaches now (Enemy.IsThreatheningTarget)."""
    from rules import targets_of
    target = _target(state, to)
    for attack in enemy.queue:
        if (attack.value > 0 or include_without_value) and target in targets_of(state, enemy, attack):
            return True
    return False


def _toward_striking_position(state, enemy, to=None):
    """Enemy.MoveTowardsStrikingPosition: closer if out of reach, back if too close, turn round for a backward-only
    queue, otherwise wait."""
    valued = _valued(enemy)
    if not valued or _threatening(state, enemy, to=to):
        return Choice("Wait")
    low = min(1000, min(min(a.range) for a in valued if a.range))
    high = max(0, max(max(a.range) for a in valued if a.range))
    distance = _distance(state, enemy, to)
    if distance < low:
        return _away(state, enemy, to)
    if distance > high:
        return _toward(state, enemy, to)
    if all(all(r < 0 for r in a.range) for a in enemy.queue) and _facing_target(state, enemy, to):
        return Choice("FlipLeft" if enemy.facing > 0 else "FlipRight")
    return Choice("Wait")


def _striking_positions(state, attack, target):
    """Attack.GetStrikingPositions: each cell and facing from which the attack would reach the target, left side
    first, in range order. A first-target attack needs nobody in between."""
    positions = []
    for side in (-1, 1):
        for offset in attack.range:
            cell = target.cell + side * offset
            if not 0 <= cell < state.cells:
                continue
            low, high = sorted((cell, target.cell))
            if attack.first_target and any(state.occupant(c) is not None for c in range(low + 1, high)):
                continue
            # Facing the target, or away from it for a backward attack.
            toward = 1 if target.cell > cell else -1
            positions.append((cell, -toward if offset <= 0 else toward))
    return positions


def _toward_closest_striking_position(state, enemy, positions):
    """Enemy.MoveTowardsClosestStrikingPosition: in one already, face its way or wait; else head for the nearest,
    the first of equals, if the way there is clear, after turning to the hero."""
    for cell, facing in positions:
        if cell == enemy.cell:
            return Choice("Wait") if facing == enemy.facing else _face_target(state, enemy)
    closest = min((cell for cell, _ in positions), key=lambda c: abs(c - enemy.cell))
    low, high = sorted((enemy.cell, closest))
    clear = state.occupant(closest) is None and all(state.occupant(c) is None for c in range(low + 1, high))
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if not clear:
        return Choice("Wait")
    return Choice("MoveRight" if closest > enemy.cell else "MoveLeft")


def _play(tile):
    return Choice("PlayTile", tile)


def _holds(enemy, name):
    return any(a.name == name for a in enemy.queue)


def _iwao(state, enemy, previous):
    """IwaoBoss.AIPickAction: a turn after playing a tile (unless corrupted); with a Dash, its pattern; attack when
    threatening; turn to face the hero; step back after attacking; into an empty queue a random tile (Spear, Earth
    Impale, Summon, and corrupted, Dash and the wave); Swirl after a lone Earth Impale with the hero adjacent; close
    in; fire a Summon."""
    tiles = len(enemy.queue)
    if previous == "PlayTile" and not enemy.corrupted:
        return Choice("Wait")
    if _holds(enemy, "Dash"):
        # IwaoBoss.DashPattern: face the hero, add the Spear a turn after the Dash, then dash and strike whenever
        # nobody is in between. The Dash carries him next to the hero from anywhere.
        if not _facing_target(state, enemy):
            return _face_target(state, enemy)
        if tiles == 1:
            return Choice("Wait") if previous == "PlayTile" else _play("Spear")
        return Choice("Attack") if tiles == 2 and _path_free(state, enemy) else Choice("Wait")
    if _valued(enemy) and _threatening(state, enemy):
        return Choice("Attack")
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if previous == "Attack":
        return _away(state, enemy)
    if tiles == 0:
        return _play(None)
    if tiles == 1 and _holds(enemy, "EarthImpale") and _distance(state, enemy) == 1:
        return _play("Swirl")
    if _valued(enemy) and _path_free(state, enemy):
        return _toward_striking_position(state, enemy)
    return Choice("Attack") if _holds(enemy, "Summon") else Choice("Wait")


def _enemies(state):
    """CombatManager.Enemies: every enemy on the board."""
    return [e for e in state.enemies if e.alive]


def _central(state):
    return (state.cells - 1) // 2


def _wave_tile(state, enemy):
    """BaseCorruptedWaveAttack.GetAppropriateCorruptedWave: the one that ends on the boss's own side."""
    return "CorruptedWaveR2L" if enemy.cell < state.cells // 2 else "CorruptedWaveL2R"


def _corruption_active(state):
    """CombatManager.IsEndOfTurnTaskActive<CorruptionAttackCombatTask>: a wave or barrage still sweeping."""
    return any(h.get("heals_boss", True) for h in state.hazards)


def _set_pattern(enemy, pattern):
    """A boss's set_CurrentPattern, keeping the one it replaces as the previous (Baru, the Shogun's second phase)."""
    enemy.prev_pattern = enemy.pattern
    enemy.pattern = pattern


def _first_enemy_between(state, enemy):
    """ReiBoss.ClosestAgentBetweenMeAndHero: the first enemy on the way to the hero."""
    step = 1 if state.hero.cell > enemy.cell else -1
    cell = enemy.cell + step
    while cell != state.hero.cell:
        agent = state.occupant(cell)
        if agent is not None and agent is not state.hero:
            return agent
        cell += step
    return None


def _rei(state, enemy, previous):
    """ReiBoss.AIPickAction. With someone in his way, that one becomes his target, and he punches it."""
    if enemy.first_turn:
        return _play("Summon")
    path_free = _path_free(state, enemy)
    to = None if path_free else _first_enemy_between(state, enemy)
    if not _facing_target(state, enemy, to):
        return _face_target(state, enemy, to)
    if previous == "Attack":
        return _away(state, enemy, to)
    if previous == "PlayTile" and not enemy.corrupted:
        return Choice("Wait")
    if path_free:
        if not enemy.queue:
            return _play(None)
    else:
        if not enemy.queue:
            return _play("DragonPunch")
        if len(enemy.queue) == 1 and not _holds(enemy, "DragonPunch"):
            enemy.queue = []
            return _play("DragonPunch")
    if enemy.queue:
        if len(enemy.queue) == 1 and _holds(enemy, "Charge"):
            return Choice("Wait") if enemy.corrupted and previous == "PlayTile" else _play("DragonPunch")
        if len(enemy.queue) == 1 and _holds(enemy, "BackCharge"):
            return _play("Summon")
        if _holds(enemy, "Summon") or _threatening(state, enemy, to=to):
            return Choice("Attack")
        if _path_free(state, enemy, to):
            return _toward_striking_position(state, enemy, to)
    return Choice("Wait")


def _kowa(state, enemy, previous):
    """KowaBoss.AIPickAction: a turn after a tile or an attack; away whenever he can; a Shield unless his last tile
    was one; corrupted and cut off, the wave; else Smoke Bomb; then fire."""
    if previous in ("PlayTile", "Attack"):
        return Choice("Wait")
    if _can_move_away(state, enemy):
        return _away(state, enemy)
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if not enemy.queue:
        if not enemy.shield:
            if enemy.last_tile is None:
                return None  # Enemy.LastTilePlayed, only logged since mod 0.19.0.
            if enemy.last_tile != "Shield":
                return _play("Shield")
        if enemy.corrupted and not _path_free(state, enemy) and not _corruption_active(state):
            return _play(_wave_tile(state, enemy))
        return _play("SmokeBomb")
    if _valued(enemy) and not _threatening(state, enemy):
        return Choice("Wait")
    return Choice("Attack")


STATUE_STANDARD, STATUE_TO_CENTER, STATUE_FROM_CENTER = 1, 2, 3


def _statue(state, enemy, previous):
    """StatueBoss.AIPickAction: three tiles by its pattern, then an extra turn's wait unless corrupted, then fire."""
    if enemy.pattern is None:
        return None
    if enemy.pattern == 0:
        # StatueBoss.PickNextPattern: corrupted and under a third of its HP, it heads for the center.
        if enemy.corrupted and enemy.hp < enemy.max_hp // 3:
            enemy.pattern = STATUE_FROM_CENTER if enemy.cell == _central(state) else STATUE_TO_CENTER
        else:
            enemy.pattern = STATUE_STANDARD
    if previous == "PlayTile" and enemy.pattern == STATUE_STANDARD:
        return Choice("Wait")
    if previous == "Attack":
        return Choice("Wait")
    tiles = len(enemy.queue)
    if tiles == 3:
        wait = enemy.ai_count
        if wait is None:
            # Set at each tile played, so known straight after one; logged since mod 0.19.0.
            wait = 0 if enemy.corrupted else (1 if previous == "PlayTile" else None)
        if wait is None:
            return None
        if wait <= 0:
            enemy.pattern = 0
            return Choice("Attack")
        enemy.ai_count = wait - 1
        return Choice("Wait")
    if tiles < 3:
        enemy.ai_count = 0 if enemy.corrupted else 1
        if enemy.pattern == STATUE_STANDARD:
            return _play(None)
        order = (["OriginOfSymmetry", "Swirl", "TwinTessen"] if enemy.pattern == STATUE_TO_CENTER
                 else ["Arrow", "TurnAround", "Arrow"])
        return _play(order[tiles])
    return Choice("Wait")


NO_FREE_PATH_TILES = ("Spear", "MeteorHammer")


def _twin(state, enemy, previous):
    """TwinBaseBoss.AIPickAction: with the way blocked, back off or swap in a Spear; with an ally blocked, flank
    (Dash, Swap Toss); otherwise attack head on."""
    tiles = len(enemy.queue)
    if enemy.first_turn and not enemy.corrupted:
        return Choice("Wait")
    if previous == "Attack":
        return _toward(state, enemy) if _path_free(state, enemy) else Choice("Wait")
    if previous == "PlayTile" and not enemy.corrupted and not (tiles == 1 and _holds(enemy, "Dash")):
        return Choice("Wait")
    if not _path_free(state, enemy):
        if _can_move_away(state, enemy):
            return _away(state, enemy)
        if not any(_holds(enemy, name) for name in NO_FREE_PATH_TILES):
            enemy.queue = []
            return _play("Spear")
        return Choice("Attack") if _threatening(state, enemy) else Choice("Wait")
    if not all(_path_free(state, other) for other in _enemies(state) if other is not enemy):
        if _threatening(state, enemy):
            return Choice("Attack")
        if not _facing_target(state, enemy):
            return _face_target(state, enemy)
        if tiles == 0:
            return _play(None)
        if tiles == 1 and _holds(enemy, "Dash"):
            return _play("SwapToss")
        if _holds(enemy, "Dash") and _holds(enemy, "SwapToss"):
            return Choice("Attack")
        return _toward_striking_position(state, enemy) if _valued(enemy) else Choice("Wait")
    if _threatening(state, enemy):
        return Choice("Attack")
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if not _valued(enemy):
        enemy.queue = []
        return _play(None)
    return _toward_striking_position(state, enemy)


FUMIKO_ATTACK, FUMIKO_SUMMON = 1, 2


def _fumiko(state, enemy, previous):
    """FumikoBoss.AIPickAction: summons once her countdown runs out with few about, else attacks; away after an
    attack."""
    if previous == "Attack":
        was_attacking = enemy.pattern == FUMIKO_ATTACK
        enemy.pattern = 0
        if was_attacking:
            return _away(state, enemy)
    if enemy.pattern is None:
        return None
    if enemy.pattern == 0:
        # FumikoBoss.PickNextPattern.
        countdown = enemy.ai_count
        if len(_enemies(state)) <= 2:
            if countdown is None:
                return None  # summonPatternCooldown, logged since mod 0.19.0.
            if countdown <= 0:
                enemy.pattern = FUMIKO_SUMMON
        if enemy.pattern == 0:
            enemy.ai_count = None if countdown is None else countdown - 1
            enemy.pattern = FUMIKO_ATTACK
    if enemy.pattern == FUMIKO_SUMMON:
        enemy.ai_count = 3
        if not _facing_target(state, enemy):
            return _face_target(state, enemy)
        return _play("Summon") if len(enemy.queue) < (3 if enemy.corrupted else 2) else Choice("Attack")
    if _threatening(state, enemy, include_without_value=True):
        return Choice("Attack")
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if previous == "Attack":
        return _away(state, enemy)
    if not enemy.queue:
        return _play(None)
    if _valued(enemy) and _path_free(state, enemy):
        return _toward_striking_position(state, enemy)
    return Choice("Wait")


BARU_OFFENSIVE, BARU_BUILD, BARU_BARRICADED = 1, 2, 3


def _baru(state, enemy, previous):
    """BaruBoss.AIPickAction: after an offensive, build a barricade (punch or back charge, then the Barricade);
    otherwise offensive with the way clear, or barricaded behind it."""
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if enemy.pattern is None:
        return None
    if enemy.pattern == 0:
        if enemy.prev_pattern is None:
            return None  # The previous pattern, logged since mod 0.19.0.
        if enemy.prev_pattern == BARU_OFFENSIVE:
            _set_pattern(enemy, BARU_BUILD)
        else:
            _set_pattern(enemy, BARU_OFFENSIVE if _path_free(state, enemy) else BARU_BARRICADED)
    elif enemy.pattern == BARU_OFFENSIVE and not _path_free(state, enemy):
        enemy.queue = []
        _set_pattern(enemy, BARU_BARRICADED)
    tiles = len(enemy.queue)
    if enemy.pattern == BARU_OFFENSIVE:
        if previous == "PlayTile" and not enemy.corrupted:
            return Choice("Wait")
        if tiles == 0:
            return _play(None)
        if _valued(enemy):
            if _threatening(state, enemy):
                return Choice("Attack")
            if _path_free(state, enemy):
                return _toward_striking_position(state, enemy)
        return Choice("Attack") if _holds(enemy, "Summon") else Choice("Wait")
    if enemy.pattern == BARU_BUILD:
        if tiles == 0:
            behind = enemy.cell - enemy.facing
            return _play("DragonPunch" if not 0 <= behind < state.cells else "BackCharge")
        if tiles == 1:
            return _play("Barricade")
        return Choice("Attack") if tiles == 2 else Choice("Wait")
    if previous == "Attack" or (previous == "PlayTile" and not enemy.corrupted):
        return Choice("Wait")
    if tiles == 0:
        return _play(None)
    return Choice("Attack") if tiles == 1 else Choice("Wait")


IEYASU_BLADE, IEYASU_STEP_BACK, IEYASU_ORIGIN, IEYASU_SUMMON, IEYASU_NAGIBOKU = 1, 2, 3, 4, 5


def _ieyasu(state, enemy, previous):
    """IeyasuBoss.AIPickAction: a random pattern (Blade of Patience, then a step back; Summon; Origin of Symmetry;
    corrupted, Nagiboku), each a fixed few tiles."""
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if enemy.pattern is None:
        return None
    if enemy.pattern == 0:
        # IeyasuBoss.CanDoPattern: with only him and his Swapper left, only Summon can be chosen.
        if len(_enemies(state)) != 2:
            return None
        enemy.pattern = IEYASU_SUMMON
    tiles = len(enemy.queue)
    if enemy.pattern == IEYASU_BLADE:
        if tiles == 0:
            return _play("Dash")
        if tiles == 1:
            return _play("BladeOfPatience")
        return Choice("Attack") if previous != "PlayTile" and _path_free(state, enemy) else Choice("Wait")
    if enemy.pattern == IEYASU_STEP_BACK:
        enemy.pattern = 0
        return _away(state, enemy)
    if enemy.pattern in (IEYASU_SUMMON, IEYASU_ORIGIN):
        if tiles == 0:
            return _play("Summon" if enemy.pattern == IEYASU_SUMMON else "OriginOfSymmetry")
        if previous == "PlayTile" and not enemy.corrupted:
            return Choice("Wait")
        return Choice("Attack")
    if tiles == 0:
        return _play("Nagiboku")
    positions = _striking_positions(state, enemy.queue[0], state.hero)
    if not positions:
        return Choice("Wait")
    if any(cell == enemy.cell and facing == enemy.facing for cell, facing in positions):
        return Choice("Attack")
    return _toward_closest_striking_position(state, enemy, positions)


HIDEYOSHI_PATTERNS = {
    1: ("OriginOfSymmetry", "Swirl", "EarthImpale"),
    2: ("Summon",),
    3: ("BackCharge", "Mirror", "Spear"),
    4: ("Dash", "Bomb", "BackCharge"),
    5: ("Swirl", "Mirror", "Swirl"),
    6: ("wave",),
    7: ("MeteorHammer", "TurnAround", "MeteorHammer"),
    8: ("Curse", "TurnAround", "Curse"),
}


def _hideyoshi(state, enemy, previous):
    """HideyoshiBoss.AIPickAction: a random pattern, each a fixed run of tiles and then the attack, no waits."""
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if not enemy.pattern:
        return None
    order = HIDEYOSHI_PATTERNS[enemy.pattern]
    tiles = len(enemy.queue)
    if tiles < len(order):
        return _play(_wave_tile(state, enemy) if order[tiles] == "wave" else order[tiles])
    if enemy.pattern == 4 and not _path_free(state, enemy):
        return Choice("Wait")
    return Choice("Attack")


def _nobunaga(state, enemy, previous):
    """NobunagaBoss.AIPickAction: fire when anything he holds reaches the hero; face; after an attack, away (closer
    when corrupted); a random tile into an empty queue; close in; fire a Summon."""
    if _threatening(state, enemy, include_without_value=True):
        return Choice("Attack")
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if previous == "Attack":
        if enemy.corrupted:
            return _toward(state, enemy) if _path_free(state, enemy) else Choice("Wait")
        return _away(state, enemy)
    if not enemy.queue:
        return _play(None)
    if _valued(enemy) and _path_free(state, enemy):
        return _toward_striking_position(state, enemy)
    return Choice("Attack") if _holds(enemy, "Summon") else Choice("Wait")


def _sato(state, enemy, previous):
    """SatoBoss.AIPickAction: Copycat Mirror, then the copies from a striking position; once he has attacked in an
    act (before the fifth), Maku ends it."""
    if enemy.first_turn:
        return Choice("Wait")
    if enemy.ai_act is None or enemy.ai_flag is None:
        return None  # iAct and alreadyAttackedInThisAct, logged since mod 0.19.0.
    if enemy.ai_act < 5 and enemy.ai_flag:
        if not _facing_target(state, enemy):
            return _face_target(state, enemy)
        if previous == "Attack":
            return _away(state, enemy)
        if not _holds(enemy, "Maku"):
            enemy.queue = []
            return _play("Maku")
        return Choice("Attack")
    if not enemy.queue or _holds(enemy, "CopycatMirror"):
        if not enemy.queue:
            if not _facing_target(state, enemy):
                return _face_target(state, enemy)
            if previous == "Attack":
                return _away(state, enemy)
            return _play("CopycatMirror")
        # SatoBoss.get_CopyableTiles: the hero's hand, but for a few kinds he won't copy (not decoded), so any.
        if any(not t.in_queue for t in state.tiles):
            return Choice("Attack")
        if not _facing_target(state, enemy):
            return _face_target(state, enemy)
        return _away(state, enemy)
    if previous == "Attack":
        return Choice("Wait")
    if not enemy.queue[0].range:
        enemy.ai_flag = True
        return Choice("Attack")
    positions = [p for attack in enemy.queue for p in _striking_positions(state, attack, state.hero)]
    if not positions:
        return Choice("Wait")
    if any(cell == enemy.cell and facing == enemy.facing for cell, facing in positions):
        enemy.ai_flag = True
        return Choice("Attack")
    return _toward_closest_striking_position(state, enemy, positions)


def _shogun_one(state, enemy, previous):
    """ShogunPhase1Boss.AIPickAction: face; away after an attack; a random tile; the Spear after a lone Charge;
    then attack when threatening or close in."""
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if previous == "Attack":
        return _away(state, enemy)
    if not enemy.queue:
        return _play(None)
    if len(enemy.queue) == 1 and _holds(enemy, "Charge"):
        return _play("Spear")
    if _valued(enemy):
        if _threatening(state, enemy):
            return Choice("Attack")
        return _toward_striking_position(state, enemy) if _path_free(state, enemy) else Choice("Wait")
    return Choice("Attack")


SHOGUN_CHARGE, SHOGUN_BACK_CHARGE, SHOGUN_BARRAGE, SHOGUN_SHURIKEN, SHOGUN_ORIGIN = 1, 2, 3, 4, 5


def _shogun_two(state, enemy, previous):
    """ShogunPhase2Boss.AIPickAction: random patterns, never the same twice running, Origin of Symmetry always
    after the Shuriken; each a tile or two and then the attack."""
    if enemy.first_turn:
        return Choice("Wait")
    if not _facing_target(state, enemy):
        return _face_target(state, enemy)
    if enemy.pattern is None:
        return None
    if enemy.pattern == 0:
        if enemy.prev_pattern != SHOGUN_SHURIKEN:
            return None
        _set_pattern(enemy, SHOGUN_ORIGIN)
    tiles = len(enemy.queue)
    pattern = enemy.pattern
    if pattern == SHOGUN_CHARGE and tiles < 2:
        return _play(("Charge", "Swirl")[tiles])
    if pattern == SHOGUN_BACK_CHARGE and tiles < 2:
        return _play(("BackCharge", "Mirror")[tiles])
    if pattern == SHOGUN_BARRAGE:
        if tiles == 0:
            return _play("OriginOfSymmetry" if enemy.cell != _central(state) else "CorruptedBarrage")
        if tiles == 1 and _holds(enemy, "OriginOfSymmetry"):
            return _play("CorruptedBarrage")
    if pattern in (SHOGUN_SHURIKEN, SHOGUN_ORIGIN) and tiles == 0:
        return _play("Shuriken" if pattern == SHOGUN_SHURIKEN else "OriginOfSymmetry")
    _set_pattern(enemy, SHOGUN_SHURIKEN if pattern == SHOGUN_BACK_CHARGE else 0)
    return Choice("Attack")


BOSS_AI = {"ReiBoss": _rei, "KowaBoss": _kowa, "StatueBoss": _statue, "TwinMainBoss": _twin, "TwinSideBoss": _twin,
           "FumikoBoss": _fumiko, "BaruBoss": _baru, "IeyasuBoss": _ieyasu, "HideyoshiBoss": _hideyoshi,
           "NobunagaBoss": _nobunaga, "SatoBoss": _sato, "ShogunPhase1Boss": _shogun_one,
           "ShogunPhase2Boss": _shogun_two}


def after_attack(enemy):
    """What a boss does once its attack has gone off (PostAttackEvents): Baru and Hideyoshi start a new pattern, Ieyasu
    steps back after his Blade of Patience."""
    if enemy.kind == "BaruBoss" and enemy.pattern is not None:
        _set_pattern(enemy, 0)
    elif enemy.kind == "HideyoshiBoss" and enemy.pattern is not None:
        enemy.pattern = 0
    elif enemy.kind == "IeyasuBoss" and enemy.pattern is not None:
        enemy.pattern = IEYASU_STEP_BACK if enemy.pattern == IEYASU_BLADE else 0


def _pick(state, enemy, previous):
    """The kind's AIPickAction, by `previous`, the action it took this turn. None where it can't be known."""
    kind = enemy.kind
    quick = enemy.elite == "Quick"
    tiles = len(enemy.queue)
    if kind == "Barricade":
        return Choice("Wait")
    if kind == "Summoner":
        # SummonerEnemy.AIPickAction: waits out its countdown, a turn after attacking or playing a tile, then plays
        # Summon and fires it, which starts the countdown again. The countdown is only known since mod 0.17.0.
        if enemy.ai_wait is None:
            return None
        if enemy.ai_wait > 0:
            enemy.ai_wait -= 1
            return Choice("Wait")
        if previous in ("Attack", "PlayTile"):
            return Choice("Wait")
        if tiles == 0:
            return _play("Summon")
        if any(a.name == "Summon" for a in enemy.queue):
            if enemy.ai_wait_full is None:
                return None
            enemy.ai_wait = enemy.ai_wait_full
            return Choice("Attack")
        return Choice("Wait")
    if kind == "DaisukeBoss":
        # DaisukeBoss.AIPickAction: turn to face the hero first; step back after attacking; a turn after playing a
        # tile (unless corrupted); into an empty queue a random tile; after a lone Charge, the Katana; then attack
        # when threatening, or close in. Corrupted, he never plays the Katana straight after a tile.
        if not _facing_target(state, enemy):
            return _face_target(state, enemy)
        if previous == "Attack":
            return _away(state, enemy)
        if previous == "PlayTile" and not enemy.corrupted:
            return Choice("Wait")
        if tiles == 0:
            return _play(None)
        if tiles == 1 and enemy.queue[0].name == "Charge":
            return Choice("Wait") if enemy.corrupted and previous == "PlayTile" else _play("Katana")
        if _valued(enemy):
            if _threatening(state, enemy):
                return Choice("Attack")
            if _path_free(state, enemy):
                return _toward_striking_position(state, enemy)
        return Choice("Attack") if any(a.name == "Summon" for a in enemy.queue) else Choice("Wait")
    if kind == "IwaoBoss":
        return _iwao(state, enemy, previous)
    if kind in BOSS_AI:
        return BOSS_AI[kind](state, enemy, previous)
    if kind == "Swapper":
        # SwapperEnemy.AIPickAction: a turn after playing its tile, then fires it, then waits 3 turns, then plays it.
        if enemy.ai_wait is None:
            return None
        if previous == "PlayTile":
            return Choice("Wait")
        if tiles > 0:
            enemy.ai_wait = SWAPPER_WAIT
            return Choice("Attack")
        if enemy.ai_wait > 0:
            enemy.ai_wait -= 1
            return Choice("Wait")
        return _play("BossSwap")
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
    if enemy.kind == "DaisukeBoss":
        return "Katana" if tiles == 1 and enemy.queue[0].name == "Charge" else None
    if enemy.kind == "IwaoBoss":
        # A second tile is the Spear after a Dash, or Swirl after Earth Impale; into an empty queue, random.
        if tiles == 1:
            return {"Dash": "Spear", "EarthImpale": "Swirl"}.get(enemy.queue[0].name)
        return None
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
