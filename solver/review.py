"""Shows what the evaluator would do at each turn of a fight log, so its choices can be challenged.

Usage: python solver/review.py [--depth N] [--top N] [--terms] [log file]
"""
import argparse
import json
from pathlib import Path

from evaluator import rank_actions
from rules import state_from_log

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "research" / "logs" / "first_battle_tiletest.jsonl"


def board(row):
    """A one-line picture of the grid, using the same notation as the in-game log."""
    cells = ["."] * row["cells"]
    hero = row["hero"]
    cells[hero["cell"]] = ("<" if hero["facing"] == "Left" else "") + "HERO" + (">" if hero["facing"] == "Right" else "")
    for enemy in row["enemies"]:
        left = enemy["facing"] == "Left"
        queue = ",".join(a["name"] for a in enemy["queue"])
        cells[enemy["cell"]] = (
            f"{'<' if left else ''}{enemy['kind']}{'' if left else '>'}"
            f"[{enemy['hp']}hp {enemy['action']}{' q:' + queue if queue else ''}]"
        )
    return "  ".join(f"{i}:{cell}" for i, cell in enumerate(cells))


def last_state_per_turn(rows):
    """Each WaveRoom turn's state as it stood just before the hero acted, with what was actually done."""
    states = {}
    actions = {}
    current = None
    for row in rows:
        if row["type"] == "state" and row["room"] != "CampRoom":
            current = row
            states.setdefault(row["turn"], row)
        elif row["type"] == "event" and row["event"] == "hero_action" and current is not None:
            actions[row["turn"]] = row["action"]
    return [(turn, states[turn], actions.get(turn, "?")) for turn in sorted(states)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", nargs="?", default=DEFAULT_LOG)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--terms", action="store_true", help="show how each score is made up")
    args = parser.parse_args()

    rows = [json.loads(line) for line in Path(args.log).read_text(encoding="utf-8").splitlines()]
    for turn, row, actual in last_state_per_turn(rows):
        state = state_from_log(row)
        hand = [f"{t.attack.name}{'(queued)' if t.in_queue else '' if t.ready else f'({t.cooldown - t.charge}t)'}"
                for t in state.tiles]
        wave = row.get("wave") or {}
        print(f"\nTurn {turn} | HP {row['hero']['hp']} | wave {wave.get('number')}/{wave.get('total')}"
              f" next={wave.get('turnsUntilNext')} | tiles {', '.join(hand)}"
              f" | special {state.swap_charge}/{state.swap_cooldown}")
        print("  " + board(row))
        for line in rank_actions(state, depth=args.depth)[: args.top]:
            print(f"    {line.score:8.1f}  {' -> '.join(line.labels)}")
            if args.terms:
                parts = {k: round(v, 1) for k, v in line.terms.items() if abs(v) > 0.05}
                print(f"              {parts}")
        print(f"    TileTest actually did: {actual}")


if __name__ == "__main__":
    main()
