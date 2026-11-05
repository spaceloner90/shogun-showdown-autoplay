"""Tests the rules against a fight log: from each logged state and the action the hero actually took,
predict the next state and compare it with what the game logged.

New enemies aren't predicted, and neither is what they do next, so spawned enemies and telegraphs
aren't compared.

Usage: python solver/check_predictions.py [log file]
"""
import json
import sys
from collections import Counter
from pathlib import Path

from rules import UNKNOWN_TILE, Action, state_from_log, step

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "research" / "logs" / "first_battle_tiletest.jsonl"


def turns_from_log(rows):
    """Yields (state before acting, action, tile name, next state, whether a wave spawned)."""
    current = None
    before_action = None
    tile = None
    pending = None
    spawned = False
    for row in rows:
        if row["type"] == "state":
            if pending is not None and row["turn"] > pending[1]["turn"]:
                yield (*pending, row, spawned)
                pending = None
                spawned = False
                before_action = None
            if pending is None and before_action is None:
                current = row
        elif row["type"] != "event":
            continue
        elif row["event"] == "combat_start":
            pending, current, before_action, tile = None, None, None, None
            spawned = False
        elif row["event"] == "wave_spawn":
            spawned = True
        elif row["event"] == "hero_tile":
            tile = row["tile"]
            before_action = current
        elif row["event"] == "hero_action" and current is not None:
            pending = (row["action"], before_action or current, tile)
            tile = None


def to_action(state, name, tile_name):
    if name in ("FlipLeft", "FlipRight"):
        return Action("Flip")
    if name != "PlayTile":
        return Action(name)
    index = next(i for i, t in enumerate(state.tiles) if t.attack.name == tile_name and not t.in_queue)
    return Action("PlayTile", index)


def compare(predicted, actual_row, spawned):
    """Lists every difference between the predicted state and the logged one."""
    problems = []

    def check(field, expected, actual):
        if expected != actual:
            problems.append((field, expected, actual))

    hero = actual_row["hero"]
    check("hero cell", predicted.hero.cell, hero["cell"])
    check("hero facing", "Left" if predicted.hero.facing < 0 else "Right", hero["facing"])
    check("hero hp", predicted.hero.hp, hero["hp"])
    check("hero queue", [a.name for a in predicted.hero.queue], [a["name"] for a in hero["queue"]])
    check("swap charge", predicted.swap_charge, hero["special"]["charge"])

    for tile, logged in zip(predicted.tiles, actual_row["tiles"]):
        name = tile.attack.name
        check(f"{name} charge", tile.charge, tile.cooldown - logged["turnsBeforeCharged"])
        check(f"{name} in queue", tile.in_queue, "AttackQueue" in logged["where"])

    wave = actual_row.get("wave")
    if predicted.turns_until_wave is not None and wave and not spawned:
        check("wave countdown", predicted.turns_until_wave, wave["turnsUntilNext"])

    enemies = sorted(actual_row["enemies"], key=lambda e: e["cell"])
    actual_cells = {e["cell"]: e for e in enemies}
    for enemy in predicted.enemies:
        logged = actual_cells.get(enemy.cell)
        if logged is None or logged["kind"] != enemy.kind:
            problems.append(("enemy position", f"{enemy.kind}@{enemy.cell}",
                             [f"{e['kind']}@{e['cell']}" for e in enemies]))
            continue
        check(f"{enemy.kind} hp", enemy.hp, logged["hp"])
        check(f"{enemy.kind} facing", "Left" if enemy.facing < 0 else "Right", logged["facing"])
        expected_queue = [a.name for a in enemy.queue]
        actual_queue = [a["name"] for a in logged["queue"]]
        check(f"{enemy.kind} queue length", len(expected_queue), len(actual_queue))
        for expected, actual in zip(expected_queue, actual_queue):
            if expected != UNKNOWN_TILE:
                check(f"{enemy.kind} queue", expected, actual)
    if not spawned:
        check("enemy count", len(predicted.enemies), len(enemies))
    return problems


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    total = 0
    failed = 0
    fields = Counter()
    actions = Counter()
    for action_name, before, tile_name, after, spawned in turns_from_log(rows):
        if before["room"] == "CampRoom":
            continue
        state = state_from_log(before)
        predicted, _ = step(state, to_action(state, action_name, tile_name))
        problems = compare(predicted, after, spawned)
        total += 1
        actions[action_name] += 1
        if problems:
            failed += 1
            print(f"Turn {before['turn']} {action_name}{' ' + tile_name if tile_name else ''}"
                  f"{' (wave spawned)' if spawned else ''}:")
            for field, expected, actual in problems:
                fields[field] += 1
                print(f"    {field}: predicted {expected}, game had {actual}")
    print(f"\n{total - failed}/{total} turns predicted exactly. Actions covered: {dict(actions)}")
    if fields:
        print("Mismatches by field:", dict(fields))


if __name__ == "__main__":
    main()
