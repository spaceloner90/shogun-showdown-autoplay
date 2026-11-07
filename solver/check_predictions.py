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

from rules import UNKNOWN_COPY, UNKNOWN_TILE, Action, state_from_log, step

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
            if pending is None:
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
            # A tile play's turn starts from just before the tile moved. After a Free Play tile,
            # any other action starts from the latest state, which already has that tile queued.
            if row["action"] == "PlayTile":
                pending = (row["action"], before_action or current, tile)
            else:
                pending = (row["action"], current, None)
            tile = None
            before_action = None


def to_action(state, name, tile_name, after):
    if name in ("FlipLeft", "FlipRight"):
        return Action("Flip")
    if name != "PlayTile":
        return Action(name)
    # The event only names the tile, and the deck can hold two of the same name. The next state shows
    # which one went into the queue.
    candidates = [i for i, t in enumerate(state.tiles) if t.attack.name == tile_name and not t.in_queue]
    moved = [i for i in candidates if i < len(after["tiles"]) and "AttackQueue" in after["tiles"][i]["where"]]
    return Action("PlayTile", (moved or candidates)[0])


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
    # Compared without order: dragging a tile can pick its slot, and reordering is free anyway.
    check("hero queue", sorted(a.name for a in predicted.hero.queue), sorted(a["name"] for a in hero["queue"]))
    check("swap charge", predicted.swap_charge, hero["special"]["charge"])
    check("hero curse", predicted.hero.curse, bool(hero.get("curse")))
    check("hero shield", predicted.hero.shield, bool(hero.get("shield")))

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
        check(f"{enemy.kind} curse", enemy.curse, bool(logged.get("curse")))
        check(f"{enemy.kind} shield", enemy.shield, bool(logged.get("shield")))
        expected_queue = [a.name for a in enemy.queue]
        actual_queue = [a["name"] for a in logged["queue"]]
        check(f"{enemy.kind} queue length", len(expected_queue), len(actual_queue))
        for expected, actual in zip(expected_queue, actual_queue):
            if expected not in (UNKNOWN_TILE, UNKNOWN_COPY):
                check(f"{enemy.kind} queue", expected, actual)
    if not spawned:
        check("enemy count", len(predicted.enemies), len(enemies))
    return problems


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    total = 0
    failed = 0
    skipped = []
    fields = Counter()
    actions = Counter()
    for action_name, before, tile_name, after, spawned in turns_from_log(rows):
        if before["room"] == "CampRoom":
            continue
        # A turn with no state line leaves nothing to compare this one's result with.
        if after["turn"] != before["turn"] + 1:
            skipped.append(before["turn"])
            continue
        state = state_from_log(before)
        predicted, _ = step(state, to_action(state, action_name, tile_name, after))
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
    if skipped:
        print(f"Skipped, because the next turn has no state line: {skipped}")
    if fields:
        print("Mismatches by field:", dict(fields))


if __name__ == "__main__":
    main()
